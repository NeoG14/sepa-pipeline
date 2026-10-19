"""Simula el historial de cambios (SCD tipo 2) de los agregados con las fechas ya procesadas.

Para cada fecha calcula la mediana del precio de lista por producto x comercio x provincia
(sin sucursales web ni sin provincia) y cuenta cuántas filas escribiría un snapshot por día
con dos reglas: ignorar las ausencias o cerrar el registro cuando una clave falta.

Uso: python -m scripts.simular_historial
"""
import duckdb

from ingesta import config

base = config.PARQUET_LOCAL_DIR.as_posix()
con = duckdb.connect()

con.execute(f"""
    CREATE TABLE agregados AS
    SELECT p.fecha, p.id_comercio, p.id_producto, s.provincia,
           median(p.precio_lista) AS mediana, count(*) AS sucursales
    FROM read_parquet('{base}/fecha=*/precios.parquet') p
    JOIN read_parquet('{base}/fecha=*/sucursales.parquet') s
      ON s.fecha = p.fecha AND s.id_comercio = p.id_comercio
     AND s.id_bandera = p.id_bandera AND s.id_sucursal = p.id_sucursal
    WHERE s.provincia IS NOT NULL AND coalesce(s.sucursales_tipo, '') <> 'Web'
      AND p.precio_lista IS NOT NULL
    GROUP BY ALL
""")
con.execute("""
    CREATE TABLE fechas AS
    SELECT fecha, row_number() OVER (ORDER BY fecha) AS n FROM (SELECT DISTINCT fecha FROM agregados)
""")
con.execute("""
    CREATE TABLE comparado AS
    SELECT a.*, f.n,
           lag(a.mediana) OVER w AS mediana_anterior,
           lag(f.n)       OVER w AS n_anterior
    FROM agregados a JOIN fechas f USING (fecha)
    WINDOW w AS (PARTITION BY a.id_comercio, a.id_producto, a.provincia ORDER BY f.n)
""")

resumen = con.execute("""
    SELECT fecha,
           count(*) AS claves,
           count(*) FILTER (WHERE mediana_anterior IS NULL) AS nuevas,
           count(*) FILTER (WHERE mediana_anterior IS NOT NULL AND mediana <> mediana_anterior) AS cambios,
           count(*) FILTER (WHERE n_anterior < n - 1) AS reaparecen,
           count(*) FILTER (WHERE n_anterior < n - 1 AND mediana = mediana_anterior) AS reaparecen_mismo_precio
    FROM comparado GROUP BY fecha ORDER BY fecha
""").fetchall()

ausentes = dict(con.execute("""
    WITH presentes AS (SELECT DISTINCT id_comercio, id_producto, provincia, n FROM comparado)
    SELECT f.fecha, count(*) FROM presentes p JOIN fechas f ON f.n = p.n + 1
    WHERE NOT EXISTS (SELECT 1 FROM presentes q WHERE q.id_comercio = p.id_comercio
                      AND q.id_producto = p.id_producto AND q.provincia = p.provincia AND q.n = p.n + 1)
    GROUP BY f.fecha
""").fetchall())

print(f"{'fecha':<12}{'claves':>11}{'nuevas':>10}{'cambios':>10}{'faltan':>9}{'vuelven':>9}"
      f"{'ignorar':>10}{'cerrar':>10}{'% ignorar':>11}{'% cerrar':>10}")
total_ign = total_cer = 0
for i, (fecha, claves, nuevas, cambios, reaparecen, reap_igual) in enumerate(resumen):
    ignorar = nuevas + cambios                 # filas nuevas en el historial
    cerrar = nuevas + cambios + reap_igual     # además reabre las que volvieron con el mismo precio
    if i > 0:
        total_ign += ignorar; total_cer += cerrar
    print(f"{fecha.isoformat():<12}{claves:>11,}{nuevas:>10,}{cambios:>10,}{ausentes.get(fecha, 0):>9,}{reaparecen:>9,}"
          f"{ignorar:>10,}{cerrar:>10,}{ignorar / claves:>10.2%}{cerrar / claves:>10.2%}")
print(f"\nEscrituras después de la carga inicial: ignorar {total_ign:,} | cerrar {total_cer:,} "
      f"(cerrar además actualiza {sum(ausentes.values()):,} filas para marcarlas como cerradas)")

print("\nCambios del último día por comercio (para ver el efecto de los domingos):")
ultimo = resumen[-1][0]
for c, claves, cambios in con.execute(f"""
        SELECT id_comercio, count(*), count(*) FILTER (WHERE mediana_anterior IS NOT NULL AND mediana <> mediana_anterior)
        FROM comparado WHERE fecha = DATE '{ultimo}' GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  comercio {c:>3}: {claves:>9,} claves | {cambios:>8,} cambios ({cambios / claves:.2%})")