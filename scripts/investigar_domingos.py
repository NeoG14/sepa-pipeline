"""Investiga los cambios de "ida y vuelta" del domingo: ¿son ofertas reales o efecto de muestra?

La cadena 13 informa desde 96 sucursales los domingos y desde 156 el resto de la semana, y muchas
medianas cambian el domingo y vuelven el lunes. Para separar las dos explicaciones:
1) Nombres de las cadenas, desde el Parquet de comercios.
2) Para las líneas (producto y provincia) que hicieron ida y vuelta un domingo, la mediana de las
   MISMAS sucursales que informan ese domingo, el sábado, el domingo y el lunes. Si con las mismas
   sucursales no cambia, el pico es efecto de muestra; si cambia, es un cambio de precio real.
3) Promociones de esas sucursales el sábado y el domingo, y las leyendas más comunes del domingo.

Uso: python -m scripts.investigar_domingos [cadena] [domingo]   (por defecto: 13 2026-10-18)
"""
import sys
from datetime import date, timedelta

import duckdb

from ingesta import config

cadena = sys.argv[1] if len(sys.argv) > 1 else "13"
domingo = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 10, 18)
sabado, lunes = domingo - timedelta(days=1), domingo + timedelta(days=1)
base = config.PARQUET_LOCAL_DIR.as_posix()
archivos = lambda tabla: "[" + ", ".join(f"'{base}/fecha={f}/{tabla}.parquet'" for f in (sabado, domingo, lunes)) + "]"

con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)

print("1) Cadenas")
con.sql(f"SELECT * EXCLUDE (fecha) FROM read_parquet('{base}/fecha={lunes}/comercios.parquet') ORDER BY 1, 2").show(max_width=250)

con.execute(f"""
    CREATE TEMP TABLE p AS
    SELECT p.fecha, p.id_bandera, p.id_sucursal, s.provincia, p.id_producto,
           p.precio_lista, p.precio_promo1, p.leyenda_promo1
    FROM read_parquet({archivos('precios')}) p
    JOIN read_parquet({archivos('sucursales')}) s
      ON s.fecha = p.fecha AND s.id_comercio = p.id_comercio
     AND s.id_bandera = p.id_bandera AND s.id_sucursal = p.id_sucursal
    WHERE p.id_comercio = '{cadena}' AND s.provincia IS NOT NULL
      AND coalesce(s.sucursales_tipo, '') <> 'Web' AND p.precio_lista IS NOT NULL
""")
con.execute(f"CREATE TEMP TABLE del_domingo AS SELECT DISTINCT id_bandera, id_sucursal FROM p WHERE fecha = DATE '{domingo}'")

# Líneas con ida y vuelta ese domingo: la mediana cambia el domingo y el lunes vuelve a la del sábado
con.execute(f"""
    CREATE TEMP TABLE picos AS
    WITH m AS (
        SELECT id_producto, provincia, fecha, median(precio_lista) AS mediana FROM p GROUP BY ALL)
    SELECT s.id_producto, s.provincia
    FROM m s JOIN m d USING (id_producto, provincia) JOIN m l USING (id_producto, provincia)
    WHERE s.fecha = DATE '{sabado}' AND d.fecha = DATE '{domingo}' AND l.fecha = DATE '{lunes}'
      AND d.mediana <> s.mediana AND l.mediana = s.mediana
""")

print(f"\n2) Cadena {cadena}: líneas con ida y vuelta el {domingo}, medidas con las mismas sucursales del domingo")
print(con.sql(f"""
    WITH mismas AS (
        SELECT p.id_producto, p.provincia, p.fecha, median(p.precio_lista) AS mediana
        FROM p JOIN del_domingo USING (id_bandera, id_sucursal)
        JOIN picos USING (id_producto, provincia)
        GROUP BY ALL),
    pivote AS (
        SELECT id_producto, provincia,
               any_value(mediana) FILTER (WHERE fecha = DATE '{sabado}')  AS sabado,
               any_value(mediana) FILTER (WHERE fecha = DATE '{domingo}') AS domingo,
               any_value(mediana) FILTER (WHERE fecha = DATE '{lunes}')   AS lunes
        FROM mismas GROUP BY ALL)
    SELECT count(*)                                              AS lineas_con_pico,
           count(*) FILTER (WHERE sabado = domingo)              AS mismas_sucursales_sin_cambio,
           count(*) FILTER (WHERE domingo < sabado)              AS mismas_sucursales_bajan,
           count(*) FILTER (WHERE domingo > sabado)              AS mismas_sucursales_suben
    FROM pivote
"""))

print(f"3) Promociones de las sucursales que informan el domingo")
print(con.sql(f"""
    SELECT fecha, dayname(fecha) AS dia, count(*) AS precios,
           count(*) FILTER (WHERE precio_promo1 IS NOT NULL) AS con_promo,
           round(100.0 * count(*) FILTER (WHERE precio_promo1 IS NOT NULL) / count(*), 1) AS porcentaje
    FROM p JOIN del_domingo USING (id_bandera, id_sucursal)
    GROUP BY fecha ORDER BY fecha
"""))
print(f"Leyendas de promo más comunes el {domingo}")
print(con.sql(f"""
    SELECT leyenda_promo1, count(*) AS precios FROM p
    WHERE fecha = DATE '{domingo}' AND leyenda_promo1 IS NOT NULL
    GROUP BY 1 ORDER BY 2 DESC LIMIT 8
"""))