"""Mide qué pasaría con la comparación si se exige que cada cadena informe el producto en un mínimo
de sus sucursales de la provincia.

Motivo (21/10): Cencosud informaba los bizcochos Don Satur en 2 sucursales de Buenos Aires a $ 300,
cuando las demás cadenas cobraban ~$ 1.500 (y Cencosud tiene cientos de sucursales ahí). La mediana
de 2 sucursales no representa a la cadena.

Para cada umbral (porcentaje de las sucursales de la cadena en la provincia ese día, de
int_cobertura_dia) muestra: cuántos pares cadena-producto quedan afuera y cuántos productos tendría
la comparación de cada provincia (los que tienen todas las cadenas, contando solo los pares que pasan).

Lee la base local en solo lectura.
Uso: python -m scripts.medir_cobertura_producto [--provincia AR-B]
"""
import argparse

import duckdb

from ingesta import config
from publicar.exportar_json import CLAVE

UMBRALES = [0, 0.02, 0.05, 0.10, 0.20]


def main():
    argumentos = argparse.ArgumentParser(description="Mide un mínimo de sucursales por producto")
    argumentos.add_argument("--provincia", default="AR-B")
    a = argumentos.parse_args()

    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    fecha = con.execute("SELECT max(fecha) FROM int_precios_dia").fetchone()[0]
    con.execute(f"""
        CREATE TEMP TABLE pares AS
        SELECT p.provincia, p.id_comercio, {CLAVE} AS clave, sum(p.sucursales) AS sucursales,
               max(c.sucursales) AS de_la_cadena
        FROM int_precios_dia p
        JOIN int_cobertura_dia c USING (fecha, id_comercio, provincia)
        WHERE p.fecha = '{fecha}' AND p.provincia IS NOT NULL
        GROUP BY ALL
    """)
    con.execute("DELETE FROM pares WHERE clave LIKE '%-%'")
    print(f"Precios del {fecha}, solo códigos de barras\n")

    print(f"{'umbral':>7}{'pares afuera':>14}{'% de pares':>12}{'comparación ' + a.provincia:>20}{'total país':>12}")
    for umbral in UMBRALES:
        afuera, total, prov, pais = con.execute(f"""
            WITH pasan AS (SELECT * FROM pares WHERE sucursales >= {umbral} * de_la_cadena),
            cadenas AS (SELECT provincia, count(DISTINCT id_comercio) AS n FROM pares GROUP BY ALL),
            comunes AS (
                SELECT p.provincia, p.clave FROM pasan p JOIN cadenas c USING (provincia)
                GROUP BY p.provincia, p.clave, c.n HAVING count(*) = c.n)
            SELECT (SELECT count(*) FROM pares) - (SELECT count(*) FROM pasan), (SELECT count(*) FROM pares),
                   (SELECT count(*) FROM comunes WHERE provincia = '{a.provincia}'), (SELECT count(*) FROM comunes)
        """).fetchone()
        print(f"{umbral:>6.0%}{afuera:>14,}{afuera / total:>11.1%}{prov:>20,}{pais:>12,}")

    print(f"\nEn {a.provincia}, pares por debajo del 10 % por cadena (sucursales de la cadena ese día):")
    for cadena, de_la_cadena, debajo, total in con.execute("""
        SELECT coalesce(c.nombre, p.id_comercio), max(p.de_la_cadena),
               count(*) FILTER (WHERE p.sucursales < 0.10 * p.de_la_cadena), count(*)
        FROM pares p LEFT JOIN cadenas c USING (id_comercio)
        WHERE p.provincia = ? GROUP BY ALL ORDER BY 3 DESC
    """, [a.provincia]).fetchall():
        print(f"  {cadena:<20}{de_la_cadena:>6,} sucursales  {debajo:>7,} de {total:,} productos ({debajo / total:.1%})")
    con.close()


if __name__ == "__main__":
    main()
