"""Verifica la canasta de seeds/canasta.csv contra las fechas ya procesadas.

Para cada producto controla que esté en las 7 cadenas (todos los días salvo como mucho
MAX_DIAS_FALTANTES), qué fechas le faltan a cada cadena, en cuántas provincias está,
y que la descripción de los datos coincida con el nombre que le pusimos. Después calcula el
total de la canasta por cadena en la última fecha (suma de las medianas nacionales del precio
de lista) y marca los productos cuyo precio varía mucho entre cadenas (posible error de unidad).

Uso: python -m scripts.verificar_canasta
"""
import csv
from pathlib import Path

import duckdb

from ingesta import config

base = config.PARQUET_LOCAL_DIR.as_posix()
SEMILLA = Path(__file__).resolve().parents[1] / "seeds" / "canasta.csv"
COMERCIOS = [str(c) for c in config.COMERCIOS]
MAX_DIAS_FALTANTES = 1  # mismo criterio que scripts/candidatos_canasta.py

with open(SEMILLA, encoding="utf-8") as f:
    canasta = list(csv.DictReader(f))
con = duckdb.connect()
con.execute("CREATE TABLE canasta(ean VARCHAR, rubro VARCHAR, nombre VARCHAR)")
con.executemany("INSERT INTO canasta VALUES (?, ?, ?)",
                [(p["ean"].lstrip("0"), p["rubro"], p["nombre"]) for p in canasta])
print(f"Productos en la canasta: {len(canasta)} (EAN distintos: "
      f"{con.execute('SELECT count(DISTINCT ean) FROM canasta').fetchone()[0]})\n")

# Precios de los productos de la canasta, solo sucursales físicas con provincia
con.execute(f"""
    CREATE TABLE precios AS
    SELECT p.fecha, ltrim(p.id_producto, '0') AS ean, p.id_comercio, s.provincia, p.precio_lista
    FROM read_parquet('{base}/fecha=*/precios.parquet') p
    JOIN read_parquet('{base}/fecha=*/sucursales.parquet') s
      ON s.fecha = p.fecha AND s.id_comercio = p.id_comercio
     AND s.id_bandera = p.id_bandera AND s.id_sucursal = p.id_sucursal
    WHERE s.provincia IS NOT NULL AND coalesce(s.sucursales_tipo, '') <> 'Web'
      AND p.precio_lista IS NOT NULL
      AND ltrim(p.id_producto, '0') IN (SELECT ean FROM canasta)
""")
total_fechas, ultima = con.execute("SELECT count(DISTINCT fecha), max(fecha) FROM precios").fetchone()

print(f"1) Presencia ({total_fechas} fechas analizadas; cuenta una cadena si le faltan "
      f"{MAX_DIAS_FALTANTES} día(s) o menos)")
print(f"{'nombre':<52}{'cadenas':>9}{'prov.':>7}  detalle")
for nombre, cadenas, provincias, detalle in con.execute(f"""
        WITH fechas AS (SELECT DISTINCT fecha FROM precios),
        presentes AS (SELECT DISTINCT ean, id_comercio, fecha FROM precios),
        pares AS (SELECT c.ean, x.id_comercio FROM canasta c CROSS JOIN (SELECT unnest(?) AS id_comercio) x),
        faltantes AS (
            SELECT pa.ean, pa.id_comercio, count(*) AS dias_faltantes,
                   string_agg(strftime(f.fecha, '%d/%m'), ' ' ORDER BY f.fecha) AS fechas_faltantes
            FROM pares pa CROSS JOIN fechas f
            ANTI JOIN presentes pr ON pr.ean = pa.ean AND pr.id_comercio = pa.id_comercio AND pr.fecha = f.fecha
            GROUP BY ALL
        )
        SELECT c.nombre,
               {len(COMERCIOS)} - count(fa.id_comercio) FILTER (WHERE fa.dias_faltantes > {MAX_DIAS_FALTANTES}),
               (SELECT count(DISTINCT provincia) FROM precios x WHERE x.ean = c.ean),
               string_agg(CASE WHEN fa.dias_faltantes = {total_fechas} THEN fa.id_comercio || ': no está'
                               WHEN fa.dias_faltantes > 3 THEN fa.id_comercio || ': faltan ' || fa.dias_faltantes || ' días'
                               ELSE fa.id_comercio || ': falta ' || fa.fechas_faltantes END, ' | ')
        FROM canasta c LEFT JOIN faltantes fa USING (ean)
        GROUP BY c.nombre, c.ean ORDER BY 2, c.nombre
        """, [COMERCIOS]).fetchall():
    print(f"{nombre[:51]:<52}{cadenas:>7}/{len(COMERCIOS)}{provincias:>7}  {detalle or ''}")

print("\n2) Nombre de la canasta contra la descripción más común en los datos (revisar a ojo)")
for nombre, descripcion in con.execute(f"""
        SELECT c.nombre, mode(d.descripcion)
        FROM canasta c
        LEFT JOIN read_parquet('{base}/fecha={ultima}/productos.parquet') d
          ON ltrim(d.id_producto, '0') = c.ean
        GROUP BY c.nombre ORDER BY c.nombre
        """).fetchall():
    print(f"  {nombre[:50]:<50} <- {descripcion}")

print(f"\n3) Total de la canasta por cadena el {ultima} (mediana nacional de cada producto)")
filas = con.execute(f"""
    WITH medianas AS (
        SELECT id_comercio, ean, median(precio_lista) AS mediana
        FROM precios WHERE fecha = DATE '{ultima}' GROUP BY ALL
    )
    SELECT id_comercio, count(*) AS productos, sum(mediana) AS total
    FROM medianas GROUP BY id_comercio ORDER BY total
""").fetchall()
for comercio, productos, total in filas:
    aviso = "" if productos == len(canasta) else f"  <- le faltan {len(canasta) - productos} productos"
    print(f"  comercio {comercio:>3}: {productos:>2} productos | total ${total:>12,.2f}{aviso}")

print("\n4) Productos cuyo precio varía más del doble entre cadenas (revisar unidad o presentación)")
hay = False
for nombre, minimo, maximo in con.execute(f"""
        WITH medianas AS (
            SELECT ean, id_comercio, median(precio_lista) AS mediana
            FROM precios WHERE fecha = DATE '{ultima}' GROUP BY ALL
        )
        SELECT c.nombre, min(m.mediana), max(m.mediana)
        FROM medianas m JOIN canasta c USING (ean)
        GROUP BY c.nombre HAVING max(m.mediana) > 2 * min(m.mediana)
        ORDER BY max(m.mediana) / min(m.mediana) DESC
        """).fetchall():
    hay = True
    print(f"  {nombre[:50]:<50} ${minimo:>10,.2f} a ${maximo:>10,.2f}")
if not hay:
    print("  ninguno")