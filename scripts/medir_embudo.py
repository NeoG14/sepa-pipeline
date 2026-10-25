"""Del dato crudo del día a lo que usan las métricas: cuántos registros quedan en cada paso y por qué se descartan. Solo lee.

Pasos, para el último día (todo el país y la provincia elegida):
 1. Precios crudos: una fila por sucursal y producto, como los informan las cadenas.
 2. Con precio de lista, en una sucursal física y con provincia reconocida (lo que entra a int_precios_dia).
 3. Filas agregadas: una por cadena, producto y provincia (la mediana entre sucursales). Cada fila del paso 3 resume
    muchas del paso 2: ninguna se pierde, se promedian.
 4. Con código de barras comparable entre cadenas (los códigos internos "comercio-código" no se comparan).
 5. Representativas: la cadena informa el producto en al menos el 5 % de sus sucursales de la provincia.
 6. Usadas en el índice de cada cadena: están en el paso 5 hoy y ayer, y su cambio no es un error de carga
    (menos de la mitad o más del doble).
 7. Para comparar con otras cadenas (el ranking): el producto lo tienen TODAS las cadenas de la provincia.

Uso: python -m scripts.medir_embudo [--provincia AR-B]
"""
import argparse

import duckdb

from ingesta import config


def main():
    a = argparse.ArgumentParser(description="Embudo de datos del último día")
    a.add_argument("--provincia", default="AR-B")
    a = a.parse_args()
    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    parquet = (config.PARQUET_LOCAL_DIR / "fecha=*" / "{}.parquet").as_posix()
    fecha = con.execute("SELECT max(fecha) FROM int_precios_dia").fetchone()[0]
    ayer = con.execute("SELECT max(fecha) FROM int_precios_dia WHERE fecha < ?", [fecha]).fetchone()[0]
    print(f"Día {fecha} (el anterior con datos: {ayer}); provincia {a.provincia}\n")

    crudos = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE x.precio_lista IS NOT NULL AND s.provincia IS NOT NULL
                                           AND coalesce(s.sucursales_tipo, '') <> 'Web'),
               count(*) FILTER (WHERE x.precio_lista IS NULL), count(*) FILTER (WHERE s.provincia IS NULL),
               count(*) FILTER (WHERE coalesce(s.sucursales_tipo, '') = 'Web'),
               count(*) FILTER (WHERE s.provincia = ?),
               count(*) FILTER (WHERE s.provincia = ? AND x.precio_lista IS NOT NULL AND coalesce(s.sucursales_tipo, '') <> 'Web')
        FROM read_parquet('{parquet.format('precios')}', hive_partitioning = true) x
        LEFT JOIN read_parquet('{parquet.format('sucursales')}', hive_partitioning = true) s
          ON s.fecha = x.fecha AND s.id_comercio = x.id_comercio AND s.id_bandera = x.id_bandera AND s.id_sucursal = x.id_sucursal
        WHERE x.fecha = ?""", [a.provincia, a.provincia, fecha]).fetchone()
    total, validos, sin_lista, sin_prov, web, total_p, validos_p = crudos

    agregadas = con.execute("SELECT count(*), count(*) FILTER (WHERE provincia = ?) FROM int_precios_dia WHERE fecha = ?",
                            [a.provincia, fecha]).fetchone()
    con.execute("""CREATE TEMP TABLE hoy AS
        SELECT provincia, id_comercio, clave, representativo FROM int_canasta_provincia_precios
        WHERE fecha = ? AND precio > 0""", [fecha])
    ean = con.execute("SELECT count(*), count(*) FILTER (WHERE provincia = ?), count(*) FILTER (WHERE representativo), "
                      "count(*) FILTER (WHERE representativo AND provincia = ?) FROM hoy", [a.provincia, a.provincia]).fetchone()
    indice = con.execute("SELECT sum(productos), sum(productos) FILTER (WHERE provincia = ?), sum(descartados) "
                         "FROM fct_indice_cadena WHERE fecha = ?", [a.provincia, fecha]).fetchone()
    ranking = con.execute("SELECT count(*) FROM fct_canasta_provincia_productos WHERE provincia = ? AND fecha = ?",
                          [a.provincia, fecha]).fetchone()[0]
    cadenas_p = con.execute("SELECT count(DISTINCT id_comercio) FROM hoy WHERE provincia = ?", [a.provincia]).fetchone()[0]

    def fila(n, texto, pais, prov, anterior=None):
        resto = f"{pais / anterior:>8.1%} del paso anterior" if anterior else ""
        print(f"{n}. {texto:<62}{pais:>14,}{prov:>14,}  {resto}")

    print(f"   {'':<62}{'todo el país':>14}{a.provincia:>14}")
    fila(1, "Precios crudos (sucursal × producto)", total, total_p)
    fila(2, "Con lista, sucursal física y provincia", validos, validos_p, total)
    fila(3, "Filas agregadas (cadena × producto × provincia)", agregadas[0], agregadas[1], validos)
    fila(4, "Con código de barras comparable", ean[0], ean[1], agregadas[0])
    fila(5, "Representativas (≥ 5 % de las sucursales)", ean[2], ean[3], ean[0])
    fila(6, "Usadas en el índice de cada cadena (hoy y ayer, sin errores)", indice[0] or 0, indice[1] or 0, ean[2])
    fila(7, f"Para el ranking: productos de las {cadenas_p} cadenas, × {cadenas_p}", ranking * cadenas_p, ranking * cadenas_p)
    print(f"\n   Descartados en el paso 2: {sin_lista:,} sin precio de lista, {sin_prov:,} sin provincia reconocida, {web:,} de sucursales web "
          f"(una fila puede caer en varios).")
    print(f"   Descartados por error de carga en el índice: {indice[2] or 0:,}.")
    con.close()


if __name__ == "__main__":
    main()
