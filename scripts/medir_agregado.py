"""Mide el agregado candidato: filas por día y cuánto cambia según qué columnas siga el historial.

Calcula, para cada fecha procesada, el agregado por producto x comercio x provincia (sin sucursales
web ni sin provincia) con todas las columnas candidatas. Después compara cada fecha con la anterior
disponible y cuenta qué porcentaje de las claves cambia si el historial sigue cada conjunto de columnas.

Uso: python -m scripts.medir_agregado
"""
import duckdb

from ingesta import config

base = config.PARQUET_LOCAL_DIR.as_posix()
con = duckdb.connect()

# Control previo: si una sucursal aparece dos veces, el JOIN duplica precios y la mediana miente
repetidas = con.execute(f"""
    SELECT count(*) - count(DISTINCT (fecha, id_comercio, id_bandera, id_sucursal))
    FROM read_parquet('{base}/fecha=*/sucursales.parquet')
""").fetchone()[0]
print(f"Sucursales repetidas (tiene que dar 0): {repetidas:,}\n")

con.execute(f"""
    CREATE TABLE agregado AS
    SELECT p.fecha, p.id_comercio, p.id_producto, s.provincia,
           count(*)                                          AS sucursales,
           median(p.precio_lista)                            AS precio_lista_mediana,
           min(p.precio_lista)                               AS precio_lista_min,
           max(p.precio_lista)                               AS precio_lista_max,
           count(*) FILTER (WHERE p.precio_promo1 IS NOT NULL) AS sucursales_promo1,
           median(p.precio_promo1)                           AS precio_promo1_mediana,
           count(*) FILTER (WHERE p.precio_promo2 IS NOT NULL) AS sucursales_promo2,
           median(p.precio_promo2)                           AS precio_promo2_mediana
    FROM read_parquet('{base}/fecha=*/precios.parquet') p
    JOIN read_parquet('{base}/fecha=*/sucursales.parquet') s
      ON s.fecha = p.fecha AND s.id_comercio = p.id_comercio
     AND s.id_bandera = p.id_bandera AND s.id_sucursal = p.id_sucursal
    WHERE s.provincia IS NOT NULL AND coalesce(s.sucursales_tipo, '') <> 'Web'
      AND p.precio_lista IS NOT NULL
    GROUP BY ALL
""")

# Cada conjunto agrega columnas al anterior: así se ve cuánto suma cada una
CONJUNTOS = {
    "A mediana": ["precio_lista_mediana"],
    "B +min/max": ["precio_lista_min", "precio_lista_max"],
    "D +promo1": ["sucursales_promo1", "precio_promo1_mediana"],
    "E +promo2": ["sucursales_promo2", "precio_promo2_mediana"],
    "C +sucursales": ["sucursales"],
}
condiciones, acumuladas = [], []
for nombre, columnas in CONJUNTOS.items():
    acumuladas += columnas
    distinto = " OR ".join(f"a.{c} IS DISTINCT FROM b.{c}" for c in acumuladas)
    condiciones.append(f"count(*) FILTER (WHERE {distinto})")

filas = con.execute(f"""
    WITH fechas AS (
        SELECT fecha, lag(fecha) OVER (ORDER BY fecha) AS anterior
        FROM (SELECT DISTINCT fecha FROM agregado)
    )
    SELECT a.fecha, f.anterior,
           (SELECT count(*) FROM agregado x WHERE x.fecha = a.fecha) AS claves,
           count(*) AS emparejadas,
           {", ".join(condiciones)}
    FROM agregado a
    JOIN fechas f ON f.fecha = a.fecha
    JOIN agregado b ON b.fecha = f.anterior AND b.id_comercio = a.id_comercio
                   AND b.id_producto = a.id_producto AND b.provincia = a.provincia
    GROUP BY a.fecha, f.anterior ORDER BY a.fecha
""").fetchall()

print(f"{'fecha':<12}{'contra':<12}{'claves':>11}{'emparejadas':>13}" + "".join(f"{n:>15}" for n in CONJUNTOS))
totales = [0] * len(CONJUNTOS)
total_emparejadas = 0
for fecha, anterior, claves, emparejadas, *cambios in filas:
    total_emparejadas += emparejadas
    totales = [t + c for t, c in zip(totales, cambios)]
    print(f"{fecha.isoformat():<12}{anterior.isoformat():<12}{claves:>11,}{emparejadas:>13,}"
          + "".join(f"{c / emparejadas:>15.2%}" for c in cambios))
print(f"{'total':<24}{'':>11}{total_emparejadas:>13,}" + "".join(f"{t / total_emparejadas:>15.2%}" for t in totales))

print("\nFilas del agregado por fecha:")
for fecha, claves in con.execute("SELECT fecha, count(*) FROM agregado GROUP BY 1 ORDER BY 1").fetchall():
    print(f"  {fecha}: {claves:,}")