"""Busca un producto por palabras de su descripción y muestra, cadena por cadena, con qué EAN lo
informa, cuántos días aparece, en cuántas sucursales y a qué precio (mediana de la última fecha).

Sirve para responder "¿de verdad esta cadena no lo vende, o lo informa con otro código o
le faltó un día?".

Uso: python -m scripts.buscar_producto LAVANDINA AYUDIN
     (busca productos cuya descripción + marca contenga TODAS las palabras; sin tildes ni mayúsculas)
     python -m scripts.buscar_producto 7790895000997
     (busca un EAN exacto, con o sin ceros a la izquierda)
"""
import sys

import duckdb

from ingesta import config

if len(sys.argv) < 2:
    sys.exit("Uso: python -m scripts.buscar_producto PALABRA [PALABRA ...]")
palabras = [p.upper() for p in sys.argv[1:]]
# Muchas cadenas ponen la marca solo en la columna marca, no en la descripción: se busca en las dos
texto = "upper(strip_accents(coalesce(descripcion, '') || ' ' || coalesce(marca, '')))"
if len(palabras) == 1 and palabras[0].isdigit():
    condicion = "ltrim(id_producto, '0') = ltrim(?, '0')"
else:
    condicion = " AND ".join(f"{texto} LIKE '%' || strip_accents(?) || '%'" for _ in palabras)

base = config.PARQUET_LOCAL_DIR.as_posix()
MAX_POR_CADENA = 8
con = duckdb.connect()
total_fechas, ultima = con.execute(
    f"SELECT count(DISTINCT fecha), max(fecha) FROM read_parquet('{base}/fecha=*/productos.parquet')").fetchone()

filas = con.execute(f"""
    WITH productos AS (
        SELECT id_comercio, id_producto, any_value(descripcion) AS descripcion, any_value(marca) AS marca
        FROM read_parquet('{base}/fecha=*/productos.parquet')
        WHERE {condicion}
        GROUP BY id_comercio, id_producto
    ),
    precios AS (
        SELECT p.fecha, p.id_comercio, p.id_producto, p.id_bandera, p.id_sucursal, p.precio_lista
        FROM read_parquet('{base}/fecha=*/precios.parquet') p
        JOIN (SELECT DISTINCT id_comercio, id_producto FROM productos) x USING (id_comercio, id_producto)
        WHERE p.precio_lista IS NOT NULL
    )
    SELECT pr.id_comercio, pr.id_producto, any_value(d.descripcion || ' [' || coalesce(d.marca, '') || ']') AS descripcion,
           count(DISTINCT pr.fecha) AS dias,
           count(DISTINCT (pr.id_bandera, pr.id_sucursal)) FILTER (WHERE pr.fecha = DATE '{ultima}') AS sucursales,
           median(pr.precio_lista) FILTER (WHERE pr.fecha = DATE '{ultima}') AS mediana
    FROM precios pr JOIN productos d USING (id_comercio, id_producto)
    GROUP BY pr.id_comercio, pr.id_producto
    ORDER BY pr.id_comercio, sucursales DESC
""", palabras).fetchall()

print(f"Búsqueda: {' + '.join(palabras)} | fechas analizadas: {total_fechas} | última: {ultima}\n")
print(f"{'comercio':>8}  {'EAN / código':<15}{'días':>6}{'sucursales':>12}{'mediana':>12}  descripción")
for comercio in [str(c) for c in config.COMERCIOS]:
    propias = [f for f in filas if f[0] == comercio]
    if not propias:
        print(f"{comercio:>8}  {'(ninguno)':<15}")
        continue
    for _, codigo, descripcion, dias, sucursales, mediana in propias[:MAX_POR_CADENA]:
        precio = f"{mediana:,.0f}" if mediana is not None else "-"
        print(f"{comercio:>8}  {codigo:<15}{dias:>4}/{total_fechas}{sucursales:>12,}{precio:>12}  {descripcion[:70]}")
    if len(propias) > MAX_POR_CADENA:
        print(f"{'':>8}  ... y {len(propias) - MAX_POR_CADENA} productos más")