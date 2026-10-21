"""Mide cuánto ocuparía publicar la historia de precios por provincia (opción B del sitio).

Arma los archivos tal como se publicarían: ~1.000 JSON, y en cada uno, por producto, provincia y
cadena, la lista de cambios [día, precio]. El archivo de cada producto sale de un hash fijo de
la clave (crc32), así el mismo producto cae siempre en el mismo archivo. El día es la cantidad de
días desde la primera fecha (números chicos ocupan menos que fechas). Mide los bytes reales y
proyecta a un año con el ritmo de cambios de las fechas que hay.

El gráfico del sitio muestra solo la mediana del precio de lista, así que también mide cuánto se
ahorra al juntar los cambios en los que la mediana no se movió (el historial guarda un cambio cuando
se mueve cualquiera de sus 7 columnas).

La clave del producto es la misma regla de siempre (macro clave_producto de dbt).
Lee la base local en solo lectura. Uso: python -m scripts.medir_historia_provincial
"""
import gzip
import json
import zlib
from collections import defaultdict

import duckdb

from ingesta import config

ARCHIVOS = 1000
LIMITE_PAGES_MB = 1024

con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
con.execute("""
    CREATE TEMP TABLE h AS
    SELECT CASE WHEN regexp_full_match(id_producto, '\\d+') AND length(ltrim(id_producto, '0')) >= 8
                     AND NOT (length(id_producto) = 13 AND id_producto LIKE '2%')
                THEN ltrim(id_producto, '0') ELSE id_comercio || '-' || id_producto END AS clave,
           provincia, id_comercio, fecha_desde, precio_lista_mediana AS precio
    FROM fct_precios_historial
""")
con.execute("""
    CREATE TEMP TABLE m AS
    SELECT * EXCLUDE (anterior) FROM (
        SELECT *, lag(precio) OVER (PARTITION BY clave, provincia, id_comercio ORDER BY fecha_desde) AS anterior
        FROM h)
    WHERE anterior IS NULL OR anterior <> precio
""")
primera, ultima, fechas = con.execute(
    "SELECT min(fecha), max(fecha), count(DISTINCT fecha) FROM int_precios_dia").fetchone()
primera_historial = con.execute("SELECT min(fecha_desde) FROM h").fetchone()[0]


def medir(tabla):
    filas = con.execute(f"""
        SELECT clave, provincia, id_comercio, date_diff('day', DATE '{primera_historial}', fecha_desde) AS dia, precio
        FROM {tabla} ORDER BY clave, provincia, id_comercio, fecha_desde
    """).fetchall()
    grupos = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    for clave, provincia, comercio, dia, precio in filas:
        p = float(precio)
        grupos[zlib.crc32(clave.encode()) % ARCHIVOS][clave][provincia][comercio].append([dia, int(p) if p.is_integer() else p])
    crudo = comprimido = 0
    for productos in grupos.values():
        texto = json.dumps(productos, separators=(",", ":")).encode()
        crudo += len(texto)
        comprimido += len(gzip.compress(texto))
    iniciales = con.execute(f"SELECT count(*) FROM {tabla} WHERE fecha_desde = DATE '{primera_historial}'").fetchone()[0]
    return len(filas), iniciales, crudo, comprimido


print(f"Fechas en el historial: desde {primera_historial} | agregado: {fechas} fechas de {primera} a {ultima}\n")
for etiqueta, tabla in (("todas las versiones del historial", "h"), ("solo cuando cambia la mediana", "m")):
    puntos, iniciales, crudo, comprimido = medir(tabla)
    dias_despues = max(fechas - 1, 1)
    por_dia = (puntos - iniciales) / dias_despues
    bytes_por_punto = crudo / puntos
    anio = (iniciales + por_dia * 365) * bytes_por_punto / 1024 / 1024
    print(f"{etiqueta}:")
    print(f"  puntos: {puntos:,} (primer día {iniciales:,}; después {por_dia:,.0f} por día)")
    print(f"  tamaño hoy: {crudo / 1024 / 1024:,.1f} MB sin comprimir | {comprimido / 1024 / 1024:,.1f} MB comprimido "
          f"| {bytes_por_punto:,.1f} bytes por punto")
    print(f"  proyección a un año: {anio:,.0f} MB ({anio / LIMITE_PAGES_MB:.0%} del límite de Pages)\n")