"""Mide qué productos comparables (EAN) podrían formar la canasta: en cuántas cadenas,
provincias y días aparecen. Usa las fechas ya procesadas en la copia local.

Un código es comparable si, sin los ceros de la izquierda, tiene 8 dígitos o más y no es
un código de 13 dígitos que empieza con 2 (esos suelen ser internos o de peso variable).

Uso: python -m scripts.medir_canasta
"""
import duckdb

from ingesta import config

base = config.PARQUET_LOCAL_DIR.as_posix()
con = duckdb.connect()

con.execute(f"""
    CREATE TABLE presencia AS
    SELECT DISTINCT ltrim(p.id_producto, '0') AS ean, p.id_comercio, s.provincia, p.fecha
    FROM read_parquet('{base}/fecha=*/precios.parquet') p
    JOIN read_parquet('{base}/fecha=*/sucursales.parquet') s
      ON s.fecha = p.fecha AND s.id_comercio = p.id_comercio
     AND s.id_bandera = p.id_bandera AND s.id_sucursal = p.id_sucursal
    WHERE s.provincia IS NOT NULL AND coalesce(s.sucursales_tipo, '') <> 'Web'
      AND p.precio_lista IS NOT NULL
      AND regexp_full_match(p.id_producto, '\\d+')
      AND length(ltrim(p.id_producto, '0')) >= 8
      AND NOT (length(p.id_producto) = 13 AND p.id_producto LIKE '2%')
""")
total_fechas = con.execute("SELECT count(DISTINCT fecha) FROM presencia").fetchone()[0]
total_comercios = con.execute("SELECT count(DISTINCT id_comercio) FROM presencia").fetchone()[0]

# Por EAN y cadena: en cuántos días y provincias aparece
con.execute("""
    CREATE TABLE por_cadena AS
    SELECT ean, id_comercio, count(DISTINCT fecha) AS dias, count(DISTINCT provincia) AS provincias
    FROM presencia GROUP BY ean, id_comercio
""")
# Por EAN: en cuántas cadenas está, en cuántas está TODOS los días, y en cuántas provincias
con.execute(f"""
    CREATE TABLE cobertura AS
    SELECT pc.ean,
           count(*)                                      AS cadenas,
           count(*) FILTER (WHERE pc.dias = {total_fechas}) AS cadenas_todos_los_dias,
           any_value(pr.provincias)                      AS provincias
    FROM por_cadena pc
    JOIN (SELECT ean, count(DISTINCT provincia) AS provincias FROM presencia GROUP BY ean) pr USING (ean)
    GROUP BY pc.ean
""")

print(f"Fechas analizadas: {total_fechas} | comercios: {total_comercios}")
print(f"EAN comparables vistos: {con.execute('SELECT count(*) FROM cobertura').fetchone()[0]:,}\n")

print("EAN según en cuántas cadenas aparecen TODOS los días analizados:")
print(f"{'cadenas':>8}{'EAN (exactamente)':>20}{'EAN (al menos)':>17}")
acumulado = 0
for k in range(total_comercios, 0, -1):
    n = con.execute(f"SELECT count(*) FROM cobertura WHERE cadenas_todos_los_dias = {k}").fetchone()[0]
    acumulado += n
    print(f"{k:>8}{n:>20,}{acumulado:>17,}")

print("\nDe los que están en al menos 6 cadenas todos los días, cuántos llegan a N provincias:")
for minimo in (24, 20, 15, 10):
    n = con.execute(f"""SELECT count(*) FROM cobertura
                        WHERE cadenas_todos_los_dias >= 6 AND provincias >= {minimo}""").fetchone()[0]
    print(f"  {minimo:>2} provincias o más: {n:,}")

print("\nQué cadena falta en los EAN que están en exactamente 6 cadenas todos los días:")
for comercio, n in con.execute(f"""
        WITH seis AS (SELECT ean FROM cobertura WHERE cadenas_todos_los_dias = 6),
             comercios AS (SELECT DISTINCT id_comercio FROM presencia)
        SELECT c.id_comercio, count(*) FROM seis s CROSS JOIN comercios c
        WHERE NOT EXISTS (SELECT 1 FROM por_cadena pc WHERE pc.ean = s.ean
                          AND pc.id_comercio = c.id_comercio AND pc.dias = {total_fechas})
        GROUP BY 1 ORDER BY 2 DESC""").fetchall():
    print(f"  comercio {comercio:>3}: falta en {n:,}")

print("\n30 candidatos con más cobertura (para mirar qué tipo de productos son):")
for ean, cadenas, provincias, descripcion in con.execute(f"""
        WITH nombres AS (
            SELECT ltrim(id_producto, '0') AS ean, mode(descripcion) AS descripcion
            FROM read_parquet('{base}/fecha=*/productos.parquet') GROUP BY 1
        )
        SELECT c.ean, c.cadenas_todos_los_dias, c.provincias, n.descripcion
        FROM cobertura c LEFT JOIN nombres n USING (ean)
        ORDER BY c.cadenas_todos_los_dias DESC, c.provincias DESC, c.ean
        LIMIT 30""").fetchall():
    print(f"  {ean:>14}  {cadenas} cadenas  {provincias:>2} prov.  {descripcion}")