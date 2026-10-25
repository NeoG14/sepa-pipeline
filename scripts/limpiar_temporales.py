"""Borra de la base local las tablas temporales que dbt deja cuando una corrida se corta (terminan en __dbt_tmp
más un número). Solo borra las que están vacías: si alguna tiene filas, la deja y avisa.

Sin argumentos solo lista lo que borraría. Con --borrar las borra. Cerrá antes cualquier dbt o consulta abierta
sobre sepa.duckdb. Uso, desde la carpeta del proyecto:
    python -m scripts.limpiar_temporales
    python -m scripts.limpiar_temporales --borrar
"""
import sys

import duckdb

from ingesta import config


def main():
    borrar = "--borrar" in sys.argv[1:]
    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=not borrar)
    nombres = [n for (n,) in con.execute(
        "select table_name from information_schema.tables "
        "where table_schema = 'main' and table_type = 'BASE TABLE' and regexp_matches(table_name, '__dbt_tmp\\d+$') "
        "order by table_name").fetchall()]
    if not nombres:
        print("No hay tablas temporales de dbt.")
        return
    for nombre in nombres:
        filas = con.execute(f'select count(*) from main."{nombre}"').fetchone()[0]
        if filas:
            print(f"{nombre}: tiene {filas:,} filas, no se toca")
        elif borrar:
            con.execute(f'drop table main."{nombre}"')
            print(f"{nombre}: vacía, borrada")
        else:
            print(f"{nombre}: vacía, se borraría con --borrar")
    con.close()


if __name__ == "__main__":
    main()
