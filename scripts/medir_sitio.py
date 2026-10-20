"""Mide cuánto pesaría publicar en el sitio (GitHub Pages, máximo 1 GB) un buscador con TODOS
los productos y la historia de precios de cada uno.

Mide tres cosas con las fechas ya procesadas:
1) El índice de búsqueda: un producto por fila (nombre, marca, en cuántas cadenas está y el texto
   de búsqueda con las descripciones de todas las cadenas). El navegador lo descarga una vez.
2) La historia: un archivo por producto con la mediana nacional del precio de lista en cada
   cadena. Solo se guardan los días en que el precio cambia, así que el tamaño depende del ritmo
   de cambios: se mide en las fechas que hay y se proyecta a un año. Para comparar, también cuenta
   cuántos puntos tendría la historia por cadena y provincia.
3) Los nombres: la descripción más común contra la más larga, en la canasta y en una muestra.

Un producto es su EAN si el código es comparable (la misma regla de siempre). Si no lo es, es el
código interno de esa cadena ("comercio-código") y aparece solo en esa cadena.

Uso: python -m scripts.medir_sitio
"""
import csv
import gzip
import json
from pathlib import Path

import duckdb

from ingesta import config

base = config.PARQUET_LOCAL_DIR.as_posix()
SEMILLA = Path(__file__).resolve().parents[1] / "seeds" / "canasta.csv"
LIMITE_PAGES_MB = 1024


def clave(col, comercio="id_comercio"):
    """El EAN sin ceros si el código es comparable; si no, 'comercio-código'."""
    return f"""CASE WHEN regexp_full_match({col}, '\\d+') AND length(ltrim({col}, '0')) >= 8
                    AND NOT (length({col}) = 13 AND {col} LIKE '2%')
               THEN ltrim({col}, '0') ELSE {comercio} || '-' || {col} END"""


def mb(n_bytes):
    return n_bytes / 1024 / 1024


con = duckdb.connect()
fechas = [f for (f,) in con.execute(
    f"SELECT DISTINCT fecha FROM read_parquet('{base}/fecha=*/precios.parquet') ORDER BY fecha").fetchall()]
ultima, total_fechas = fechas[-1], len(fechas)
print(f"Fechas analizadas: {total_fechas} | última: {ultima}\n")

# ---------------------------------------------------------------- 1) índice de búsqueda
con.execute(f"""
    CREATE TABLE productos AS
    SELECT {clave('id_producto')} AS clave, id_comercio, descripcion, marca
    FROM read_parquet('{base}/fecha={ultima}/productos.parquet')
""")
con.execute("""
    CREATE TABLE indice AS
    SELECT clave,
           NOT contains(clave, '-')                     AS es_ean,
           mode(descripcion)                            AS nombre_comun,
           arg_max(descripcion, length(descripcion))    AS nombre_largo,
           mode(marca)                                  AS marca,
           count(DISTINCT id_comercio)                  AS cadenas,
           string_agg(DISTINCT upper(strip_accents(coalesce(descripcion, '') || ' ' || coalesce(marca, ''))), ' ')
                                                        AS texto
    FROM productos GROUP BY clave
""")
total, eans, internos = con.execute(
    "SELECT count(*), count(*) FILTER (WHERE es_ean), count(*) FILTER (WHERE NOT es_ean) FROM indice").fetchone()
# Formato compacto: una lista por producto [clave, nombre, marca, cadenas, texto de búsqueda]
filas = con.execute("SELECT clave, nombre_largo, marca, cadenas, texto FROM indice").fetchall()
indice_json = json.dumps([list(f) for f in filas], ensure_ascii=False, separators=(",", ":")).encode()
print("1) Índice de búsqueda (un archivo, lo descarga el navegador una vez)")
print(f"   productos: {total:,}  (con EAN: {eans:,} | códigos internos de una cadena: {internos:,})")
print(f"   tamaño: {mb(len(indice_json)):.1f} MB sin comprimir | "
      f"{mb(len(gzip.compress(indice_json))):.1f} MB comprimido (lo que viaja por la red)")
print("   cuántas cadenas tiene cada producto:")
for cadenas, n in con.execute("SELECT cadenas, count(*) FROM indice GROUP BY 1 ORDER BY 1 DESC").fetchall():
    print(f"     {cadenas} cadena(s): {n:,}")

# ---------------------------------------------------------------- 2) historia
# Precios de sucursales físicas (vista: se lee de los Parquet en cada consulta, no se copia en memoria)
con.execute(f"""
    CREATE VIEW precios AS
    SELECT p.fecha, {clave('p.id_producto', 'p.id_comercio')} AS clave, p.id_comercio, s.provincia, p.precio_lista
    FROM read_parquet('{base}/fecha=*/precios.parquet') p
    LEFT JOIN read_parquet('{base}/fecha=*/sucursales.parquet') s
      ON s.fecha = p.fecha AND s.id_comercio = p.id_comercio
     AND s.id_bandera = p.id_bandera AND s.id_sucursal = p.id_sucursal
    WHERE coalesce(s.sucursales_tipo, '') <> 'Web' AND p.precio_lista IS NOT NULL
""")


def puntos(grano):
    """Cuenta los puntos de una historia que guarda solo los cambios de la mediana.
    Devuelve (puntos el primer día, puntos por día después: nuevos + cambios, total)."""
    con.execute(f"""
        CREATE OR REPLACE TABLE serie AS
        WITH m AS (SELECT fecha, {grano}, median(precio_lista) AS mediana FROM precios GROUP BY ALL)
        SELECT *, lag(mediana) OVER (PARTITION BY {grano} ORDER BY fecha) AS anterior FROM m
    """)
    con.execute("CREATE OR REPLACE TABLE cambios AS SELECT * FROM serie WHERE anterior IS NULL OR mediana <> anterior")
    primer_dia = con.execute(f"SELECT count(*) FROM cambios WHERE fecha = DATE '{fechas[0]}'").fetchone()[0]
    despues = con.execute(f"SELECT count(*) FROM cambios WHERE fecha > DATE '{fechas[0]}'").fetchone()[0]
    claves = con.execute(f"SELECT count(*) FROM (SELECT DISTINCT {grano} FROM serie)").fetchone()[0]
    return primer_dia, despues / max(total_fechas - 1, 1), claves


inicio_nac, por_dia_nac, series_nac = puntos("clave, id_comercio")
# Archivos reales por producto con las fechas que hay: {"cadena": [[AAAAMMDD, precio], ...]}
historia = {}
for c, comercio, fecha, mediana in con.execute(
        "SELECT clave, id_comercio, fecha, mediana FROM cambios ORDER BY clave, id_comercio, fecha").fetchall():
    historia.setdefault(c, {}).setdefault(comercio, []).append([int(fecha.strftime("%Y%m%d")), round(float(mediana), 2)])
crudo = comprimido = 0
for serie_producto in historia.values():
    texto = json.dumps(serie_producto, separators=(",", ":")).encode()
    crudo += len(texto)
    comprimido += len(gzip.compress(texto))
puntos_ahora = inicio_nac + por_dia_nac * (total_fechas - 1)
bytes_por_punto = crudo / puntos_ahora
anio_puntos = inicio_nac + por_dia_nac * 364
anio_mb = mb(anio_puntos * bytes_por_punto)

print("\n2) Historia: un archivo por producto, solo los días en que cambia la mediana")
print(f"   archivos (productos con precio): {len(historia):,} | series producto x cadena: {series_nac:,}")
print(f"   puntos: {inicio_nac:,} el primer día + {por_dia_nac:,.0f} por día después "
      f"({por_dia_nac / series_nac:.2%} de las series cambia o aparece cada día)")
print(f"   con {total_fechas} fechas: {mb(crudo):.1f} MB sin comprimir | {mb(comprimido):.1f} MB comprimido "
      f"| {bytes_por_punto:.1f} bytes por punto")
print(f"   proyección a un año: {anio_puntos:,.0f} puntos -> unos {anio_mb:,.0f} MB sin comprimir "
      f"({anio_mb / LIMITE_PAGES_MB:.0%} del límite de 1 GB de Pages)")

inicio_prov, por_dia_prov, series_prov = puntos("clave, id_comercio, provincia")
anio_prov = inicio_prov + por_dia_prov * 364
print("\n   Para comparar, la misma historia por cadena Y provincia (mismos bytes por punto):")
print(f"   series: {series_prov:,} | puntos: {inicio_prov:,} el primer día + {por_dia_prov:,.0f} por día")
print(f"   proyección a un año: {anio_prov:,.0f} puntos -> unos {mb(anio_prov * bytes_por_punto):,.0f} MB "
      f"({mb(anio_prov * bytes_por_punto) / LIMITE_PAGES_MB:.0%} del límite)")

# ---------------------------------------------------------------- 3) nombres
print("\n3) Nombre para mostrar: la descripción más común contra la más larga")
with open(SEMILLA, encoding="utf-8") as f:
    canasta = [p["ean"].lstrip("0") for p in csv.DictReader(f)]
con.execute("CREATE TABLE canasta(clave VARCHAR)")
con.executemany("INSERT INTO canasta VALUES (?)", [(e,) for e in canasta])
consulta = """SELECT nombre_comun, nombre_largo, marca, cadenas FROM indice {filtro}"""
print("   Canasta:")
for comun, largo, marca, cadenas in con.execute(
        consulta.format(filtro="WHERE clave IN (SELECT clave FROM canasta) ORDER BY nombre_largo")).fetchall():
    print(f"     más común: {str(comun)[:38]:<38} | más larga: {largo}  [{marca}]")
print("   Muestra al azar de productos en 3 cadenas o más:")
con.execute("SELECT setseed(0.42)")
for comun, largo, marca, cadenas in con.execute(
        consulta.format(filtro="WHERE cadenas >= 3 ORDER BY random() LIMIT 12")).fetchall():
    print(f"     más común: {str(comun)[:38]:<38} | más larga: {largo}  [{marca}]")