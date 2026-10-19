"""Pasos 4 a 6: del zip verificado a los Parquet del día, con controles, y copia a Drive."""
import re
import shutil
import sys
import zipfile
from datetime import date

import duckdb

from ingesta import config
from ingesta.descarga import TEMP_DIR

PROVINCIAS = {  # nombre (sin tildes, en minúscula) -> código ISO 3166-2
    "salta": "AR-A", "buenos aires": "AR-B", "ciudad autonoma de buenos aires": "AR-C", "caba": "AR-C",
    "capital federal": "AR-C", "san luis": "AR-D", "entre rios": "AR-E", "la rioja": "AR-F",
    "santiago del estero": "AR-G", "chaco": "AR-H", "san juan": "AR-J", "catamarca": "AR-K",
    "la pampa": "AR-L", "mendoza": "AR-M", "misiones": "AR-N", "formosa": "AR-P", "neuquen": "AR-Q",
    "rio negro": "AR-R", "santa fe": "AR-S", "tucuman": "AR-T", "chubut": "AR-U",
    "tierra del fuego": "AR-V", "corrientes": "AR-W", "cordoba": "AR-X", "jujuy": "AR-Y", "santa cruz": "AR-Z",
}


def extraer_comercios(ruta_zip, fecha, destino):
    """Extrae los CSV de los 7 comercios a destino/comercio_N/. Falla si falta alguno."""
    destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta_zip) as externo:
        for c in config.COMERCIOS:
            patron = rf"{fecha}/sepa_\d+_comercio-sepa-{c}_{fecha}_[\d-]+\.zip"
            nombres = [n for n in externo.namelist() if re.fullmatch(patron, n)]
            if len(nombres) != 1:
                raise ValueError(f"Comercio {c}: esperaba 1 zip interno y encontré {len(nombres)}")
            interno_tmp = destino / f"comercio_{c}.zip"
            with externo.open(nombres[0]) as origen, open(interno_tmp, "wb") as f:
                shutil.copyfileobj(origen, f)
            with zipfile.ZipFile(interno_tmp) as interno:
                for csv in ("comercio.csv", "sucursales.csv", "productos.csv"):
                    candidatos = [n for n in interno.namelist() if n.endswith(csv)]
                    if len(candidatos) != 1:
                        raise ValueError(f"Comercio {c}: no encontré {csv}")
                    (destino / f"comercio_{c}").mkdir(exist_ok=True)
                    with interno.open(candidatos[0]) as origen, open(destino / f"comercio_{c}" / csv, "wb") as f:
                        shutil.copyfileobj(origen, f)
            interno_tmp.unlink()


def leer_csv(rutas):
    """Expresión de DuckDB que lee varios CSV del SEPA como texto, sin morir por el pie."""
    lista = [r.as_posix() for r in rutas]
    return (f"read_csv({lista}, delim='|', header=true, all_varchar=true, "
            f"null_padding=true, union_by_name=true)")


def procesar_fecha(fecha):
    """Genera los Parquet de una fecha en la copia local y devuelve los controles del día."""
    ruta_zip = TEMP_DIR / f"sepa_{fecha.isoformat()}.zip"
    extraidos = TEMP_DIR / f"extraido_{fecha.isoformat()}"
    salida = config.PARQUET_LOCAL_DIR / f"fecha={fecha.isoformat()}"
    salida.mkdir(parents=True, exist_ok=True)
    extraer_comercios(ruta_zip, fecha.isoformat(), extraidos)
    archivos = lambda nombre: [extraidos / f"comercio_{c}" / nombre for c in config.COMERCIOS]
    numero = r"regexp_full_match(id_comercio, '\d+')"

    con = duckdb.connect()
    con.execute("CREATE TABLE prov_map(nombre VARCHAR, iso VARCHAR)")
    con.executemany("INSERT INTO prov_map VALUES (?, ?)", list(PROVINCIAS.items()))

    con.execute(f"CREATE TABLE productos_crudo AS SELECT * FROM {leer_csv(archivos('productos.csv'))}")
    con.execute(f"CREATE TABLE sucursales_crudo AS SELECT * FROM {leer_csv(archivos('sucursales.csv'))}")
    con.execute(f"CREATE TABLE comercios_crudo AS SELECT * FROM {leer_csv(archivos('comercio.csv'))}")

    con.execute(f"""
        COPY (
            SELECT DATE '{fecha}' AS fecha, id_comercio, id_bandera, id_sucursal, id_producto,
                   TRY_CAST(productos_precio_lista AS DECIMAL(12,2))            AS precio_lista,
                   TRY_CAST(productos_precio_referencia AS DECIMAL(12,2))       AS precio_referencia,
                   TRY_CAST(productos_cantidad_referencia AS DECIMAL(12,2))     AS cantidad_referencia,
                   productos_unidad_medida_referencia                          AS unidad_referencia,
                   TRY_CAST(productos_precio_unitario_promo1 AS DECIMAL(12,2))  AS precio_promo1,
                   productos_leyenda_promo1                                    AS leyenda_promo1,
                   TRY_CAST(productos_precio_unitario_promo2 AS DECIMAL(12,2))  AS precio_promo2,
                   productos_leyenda_promo2                                    AS leyenda_promo2
            FROM productos_crudo WHERE {numero}
        ) TO '{(salida / "precios.parquet").as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    con.execute(f"""
        COPY (
            SELECT DATE '{fecha}' AS fecha, id_comercio, id_producto,
                   any_value(productos_ean)                         AS productos_ean,
                   any_value(productos_descripcion)                 AS descripcion,
                   any_value(productos_marca)                       AS marca,
                   any_value(productos_cantidad_presentacion)       AS cantidad_presentacion,
                   any_value(productos_unidad_medida_presentacion)  AS unidad_presentacion
            FROM productos_crudo WHERE {numero}
            GROUP BY id_comercio, id_producto
        ) TO '{(salida / "productos.parquet").as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    con.execute(f"""
        COPY (
            SELECT DATE '{fecha}' AS fecha, s.* EXCLUDE (sucursales_provincia),
                   s.sucursales_provincia AS provincia_original,
                   CASE WHEN regexp_full_match(upper(trim(s.sucursales_provincia)), 'AR-[A-Z]')
                        THEN upper(trim(s.sucursales_provincia)) ELSE m.iso END AS provincia
            FROM sucursales_crudo s
            LEFT JOIN prov_map m ON m.nombre = lower(strip_accents(trim(s.sucursales_provincia)))
            WHERE regexp_full_match(s.id_comercio, '\\d+')
        ) TO '{(salida / "sucursales.parquet").as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    con.execute(f"""
        COPY (SELECT DATE '{fecha}' AS fecha, * FROM comercios_crudo WHERE {numero})
        TO '{(salida / "comercios.parquet").as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)

    precios, sucursales = (salida / "precios.parquet").as_posix(), (salida / "sucursales.parquet").as_posix()
    por_comercio = con.execute(f"""
        SELECT p.id_comercio, count(*) AS filas,
               count(DISTINCT (p.id_bandera, p.id_sucursal)) AS sucursales_con_precios,
               count(*) FILTER (WHERE p.precio_lista IS NULL) AS sin_precio_lista,
               count(*) FILTER (WHERE s.id_sucursal IS NULL) AS filas_sin_sucursal
        FROM '{precios}' p
        LEFT JOIN '{sucursales}' s USING (id_comercio, id_bandera, id_sucursal)
        GROUP BY p.id_comercio ORDER BY filas DESC
    """)
    columnas = [d[0] for d in por_comercio.description]
    por_comercio = [dict(zip(columnas, fila)) for fila in por_comercio.fetchall()]
    controles = {
        "fecha": fecha.isoformat(),
        "filas": sum(c["filas"] for c in por_comercio),
        "pies_descartados": con.execute(f"SELECT count(*) FROM productos_crudo WHERE NOT {numero} OR id_comercio IS NULL").fetchone()[0],
        "claves_repetidas": con.execute(f"""SELECT count(*) - count(DISTINCT (id_comercio, id_bandera, id_sucursal, id_producto))
                                            FROM '{precios}'""").fetchone()[0],
        "sucursales_sin_provincia": con.execute(f"SELECT count(*) FROM '{sucursales}' WHERE provincia IS NULL").fetchone()[0],
        "por_comercio": por_comercio,
    }
    con.close()
    faltan = set(map(str, config.COMERCIOS)) - {c["id_comercio"] for c in por_comercio}
    if faltan:
        raise ValueError(f"Comercios sin filas de precios: {sorted(faltan)}")
    shutil.rmtree(extraidos)
    return controles


def copiar_a_drive(fecha):
    """Copia la carpeta de la fecha a Drive: primero a .tmp y al final la renombra."""
    if not config.DRIVE_DIR.exists():
        raise FileNotFoundError(f"No encuentro la carpeta de Drive: {config.DRIVE_DIR}. ¿Está abierto Google Drive?")
    origen = config.PARQUET_LOCAL_DIR / f"fecha={fecha.isoformat()}"
    final = config.PARQUET_DIR / f"fecha={fecha.isoformat()}"
    temporal = final.with_name(final.name + ".tmp")
    if temporal.exists():
        shutil.rmtree(temporal)
    shutil.copytree(origen, temporal)
    if final.exists():
        shutil.rmtree(final)  # reprocesar una fecha la reemplaza, no la duplica
    temporal.rename(final)
    return final


def mostrar(controles):
    print(f"\n=== {controles['fecha']}: {controles['filas']:,} filas de precios ===")
    print(f"{'comercio':>8} {'filas':>11} {'sucursales':>11} {'sin_precio':>11} {'sin_sucursal':>13}")
    for c in controles["por_comercio"]:
        print(f"{c['id_comercio']:>8} {c['filas']:>11,} {c['sucursales_con_precios']:>11,} "
              f"{c['sin_precio_lista']:>11,} {c['filas_sin_sucursal']:>13,}")
    for clave in ("pies_descartados", "claves_repetidas", "sucursales_sin_provincia"):
        print(f"{clave}: {controles[clave]:,}")


if __name__ == "__main__":
    # Uso: python -m ingesta.procesar AAAA-MM-DD   (el zip tiene que estar en la carpeta temp)
    fecha = date.fromisoformat(sys.argv[1])
    mostrar(procesar_fecha(fecha))
    print(f"\nCopiado a Drive: {copiar_a_drive(fecha)}")