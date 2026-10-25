"""Mide si alcanza con los productos de la comparación para un ranking por grupo. Solo lee.

La comparación de cada provincia (fct_canasta_provincia_productos, último día) tiene los productos que
venden TODAS las cadenas de la provincia. Para calcular un índice por grupo hacen falta suficientes
productos en cada grupo. Este script cuenta, por provincia y grupo, cuántos productos hay, y cuántos
de la comparación no tienen rubro.

Uso: python -m scripts.medir_grupos_comparacion [--minimo 30]
"""
import argparse

import duckdb

from ingesta import config


def main():
    argumentos = argparse.ArgumentParser(description="Productos de la comparación por provincia y grupo")
    argumentos.add_argument("--minimo", type=int, default=30, help="productos mínimos para publicar un grupo")
    a = argumentos.parse_args()

    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    con.execute("""
        CREATE TEMP TABLE comparacion AS
        SELECT c.provincia, c.clave, coalesce(d.grupo, '(sin clasificar)') AS grupo,
               coalesce(d.rubro, '(sin clasificar)') AS rubro
        FROM fct_canasta_provincia_productos c
        LEFT JOIN dim_productos d USING (clave)
        WHERE (c.provincia, c.fecha) IN (
            SELECT provincia, max(fecha) FROM fct_canasta_provincia_productos GROUP BY provincia)""")

    total, sin = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE grupo = '(sin clasificar)') FROM comparacion").fetchone()
    print(f"Productos de la comparación (suma de provincias): {total:,}; sin rubro: {sin:,} ({sin / total:.1%})")
    print(f"Provincias con comparación: {con.execute('SELECT count(DISTINCT provincia) FROM comparacion').fetchone()[0]}\n")

    print(f"Por grupo, sobre las provincias (mínimo para publicar = {a.minimo} productos):")
    print(f"{'grupo':<26}{'provincias':>11}{'con >= mín.':>13}{'mediana':>9}{'mín.':>6}{'máx.':>6}")
    for grupo, n, ok, mediana, minimo, maximo in con.execute(f"""
        WITH por AS (SELECT grupo, provincia, count(*) AS n FROM comparacion GROUP BY 1, 2)
        SELECT grupo, count(*), count(*) FILTER (WHERE n >= {a.minimo}), median(n)::INT, min(n), max(n)
        FROM por GROUP BY grupo ORDER BY 4 DESC""").fetchall():
        print(f"{grupo:<26}{n:>11}{ok:>13}{mediana:>9}{minimo:>6}{maximo:>6}")

    print("\nRubros de la comparación en la provincia con más productos (los 15 mayores):")
    provincia = con.execute(
        "SELECT provincia FROM comparacion GROUP BY 1 ORDER BY count(*) DESC LIMIT 1").fetchone()[0]
    print(f"provincia: {provincia}")
    for grupo, rubro, n in con.execute("""
        SELECT grupo, rubro, count(*) FROM comparacion WHERE provincia = ? GROUP BY 1, 2
        ORDER BY 3 DESC LIMIT 15""", [provincia]).fetchall():
        print(f"  {n:>5}  {grupo} / {rubro}")
    con.close()


if __name__ == "__main__":
    main()
