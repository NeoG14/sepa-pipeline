"""Mide cuántos productos podría comparar una canasta armada provincia por provincia.

Hoy la canasta provincial usa los productos de la lista fija de 31 que tienen todas las cadenas de
la provincia (de 19 a 31). Este script mide, con los precios del último día de int_precios_dia:

1. Por provincia: cuántas cadenas hay, cuántos productos (códigos de barras) tienen TODAS y cuántos
   tienen al menos 2. Lo primero es el tamaño de una canasta "máxima" por provincia.
2. Para una provincia: el ranking de cadenas con un índice de precios relativo. Por cada producto
   que venden 2 cadenas o más, el precio de cada cadena se divide por la mediana de ese producto en
   la provincia; después se promedia por cadena (media geométrica). No exige que todas tengan el
   producto y un producto caro no pesa más que uno barato. Se compara con el ranking de la canasta.

Lee la base local en solo lectura. Uso: python -m scripts.medir_canasta_provincial [--provincia AR-B] [--fecha 2026-10-21]
"""
import argparse

import duckdb

from ingesta import config
from publicar.exportar_json import CLAVE


def main():
    argumentos = argparse.ArgumentParser(description="Mide canastas por provincia")
    argumentos.add_argument("--provincia", default="AR-B")
    argumentos.add_argument("--fecha", help="por defecto, el último día de int_precios_dia")
    a = argumentos.parse_args()

    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    fecha = a.fecha or con.execute("SELECT max(fecha) FROM int_precios_dia").fetchone()[0]
    # Solo códigos de barras (la clave sin guion): los códigos internos nunca se comparten
    con.execute(f"""
        CREATE TEMP TABLE hoy AS
        SELECT provincia, id_comercio, {CLAVE} AS clave, precio_lista_mediana::DOUBLE AS precio
        FROM int_precios_dia
        WHERE fecha = '{fecha}' AND provincia IS NOT NULL AND precio_lista_mediana > 0
    """)
    con.execute("DELETE FROM hoy WHERE clave LIKE '%-%'")
    con.execute("""
        CREATE TEMP TABLE por_producto AS
        SELECT provincia, clave, count(DISTINCT id_comercio) AS cadenas, median(precio) AS mediana
        FROM hoy GROUP BY ALL
    """)

    print(f"Precios del {fecha} (solo códigos de barras)\n")
    print(f"{'provincia':<10}{'cadenas':>8}{'en todas':>10}{'en 2 o más':>12}")
    filas = con.execute("""
        WITH cadenas AS (SELECT provincia, count(DISTINCT id_comercio) AS n FROM hoy GROUP BY ALL)
        SELECT c.provincia, c.n,
               count(*) FILTER (WHERE p.cadenas = c.n),
               count(*) FILTER (WHERE p.cadenas >= 2)
        FROM cadenas c JOIN por_producto p USING (provincia)
        GROUP BY ALL ORDER BY c.n DESC, c.provincia
    """).fetchall()
    for provincia, n, todas, dos in filas:
        print(f"{provincia:<10}{n:>8}{todas:>10,}{dos:>12,}")

    print(f"\nRanking en {a.provincia}: índice relativo (productos en 2 cadenas o más) vs. canasta actual")
    indice = con.execute("""
        SELECT h.id_comercio, count(*) AS productos,
               (exp(avg(ln(h.precio / p.mediana))) - 1) * 100 AS sobre_mediana
        FROM hoy h JOIN por_producto p USING (provincia, clave)
        WHERE h.provincia = ? AND p.cadenas >= 2
        GROUP BY ALL ORDER BY sobre_mediana
    """, [a.provincia]).fetchall()
    canasta = dict(con.execute("""
        SELECT id_comercio, puesto FROM fct_canasta_provincia
        WHERE provincia = ? AND fecha = ?
    """, [a.provincia, fecha]).fetchall())
    nombres = dict(con.execute("SELECT id_comercio, nombre FROM cadenas").fetchall())
    print(f"{'puesto':<8}{'cadena':<22}{'productos':>10}{'vs. mediana':>13}{'puesto canasta':>16}")
    for puesto, (cadena, productos, pct) in enumerate(indice, 1):
        print(f"{puesto:<8}{nombres.get(cadena, cadena):<22}{productos:>10,}{pct:>+12.1f}%{canasta.get(cadena, '-'):>16}")

    # Los mismos productos en todas las cadenas de la provincia, medidos de dos formas: con el índice
    # relativo (cada producto pesa igual) y con la suma de precios (pesan más los caros, como la
    # canasta actual). Si los dos rankings difieren, los productos caros están decidiendo la suma.
    todas = con.execute("""
        WITH n AS (SELECT count(DISTINCT id_comercio) AS n FROM hoy WHERE provincia = ?)
        SELECT h.id_comercio, count(*) AS productos,
               (exp(avg(ln(h.precio / p.mediana))) - 1) * 100 AS sobre_mediana,
               sum(h.precio) AS suma
        FROM hoy h JOIN por_producto p USING (provincia, clave), n
        WHERE h.provincia = ? AND p.cadenas = n.n
        GROUP BY ALL ORDER BY sobre_mediana
    """, [a.provincia, a.provincia]).fetchall()
    if todas:
        minima = min(f[3] for f in todas)
        print(f"\nLos {todas[0][1]:,} productos que tienen todas las cadenas de {a.provincia}: índice vs. suma de precios")
        print(f"{'puesto':<8}{'cadena':<22}{'vs. mediana':>13}{'suma':>16}{'suma vs. más barata':>21}{'puesto suma':>13}")
        puesto_suma = {c: i for i, (c, *_) in enumerate(sorted(todas, key=lambda f: f[3]), 1)}
        for puesto, (cadena, productos, pct, suma) in enumerate(todas, 1):
            print(f"{puesto:<8}{nombres.get(cadena, cadena):<22}{pct:>+12.1f}%{suma:>16,.0f}"
                  f"{(suma / minima - 1) * 100:>+20.1f}%{puesto_suma[cadena]:>13}")
    con.close()


if __name__ == "__main__":
    main()
