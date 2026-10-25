"""Lista las columnas de todo lo que guarda el proyecto: las tablas y vistas de la base local (sepa.duckdb)
y los Parquet crudos de la ingesta (el último día).

Solo lee: no cambia nada. Uso, desde la carpeta del proyecto:
    python -m scripts.ver_columnas
"""
from ingesta import config

import duckdb


def main():
    base = config.DATOS_DIR / "sepa.duckdb"
    con = duckdb.connect(base.as_posix(), read_only=True)
    print(f"=== Base local: {base}")
    objetos = con.execute(
        "select table_name, table_type from information_schema.tables where table_schema = 'main' order by table_name"
    ).fetchall()
    for nombre, tipo in objetos:
        filas = con.execute(f'select count(*) from main."{nombre}"').fetchone()[0] if tipo != "VIEW" else None
        detalle = "vista" if tipo == "VIEW" else f"tabla, {filas:,} filas"
        print(f"\n{nombre}  ({detalle})")
        columnas = con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema = 'main' and table_name = ? order by ordinal_position", [nombre]
        ).fetchall()
        for columna, tipo_dato in columnas:
            print(f"    {columna:<32} {tipo_dato}")
    con.close()

    carpetas = sorted(config.PARQUET_LOCAL_DIR.glob("fecha=*"))
    print(f"\n=== Parquet crudos de la ingesta: {len(carpetas)} días guardados")
    if not carpetas:
        return
    ultima = carpetas[-1]
    con = duckdb.connect()
    for tabla in ("precios", "productos", "sucursales", "comercios"):
        archivo = ultima / f"{tabla}.parquet"
        filas = con.execute("select count(*) from read_parquet(?, hive_partitioning = false)", [archivo.as_posix()]).fetchone()[0]
        print(f"\n{tabla}  ({ultima.name}, {filas:,} filas)")
        for columna, tipo_dato, *_ in con.execute("describe select * from read_parquet(?, hive_partitioning = false)", [archivo.as_posix()]).fetchall():
            print(f"    {columna:<40} {tipo_dato}")


if __name__ == "__main__":
    main()
