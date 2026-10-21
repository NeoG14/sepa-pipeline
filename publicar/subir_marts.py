"""Sube los marts terminados de la base local a MotherDuck, a la base `sepa_nube`.

dbt corre en la PC sobre la base local. A MotherDuck solo llega una copia de las tablas que usa el
sitio, para que GitHub Actions las lea y publique. Cada corrida reemplaza las tablas enteras: así
la copia nunca queda a medias ni mezclada con datos viejos. Después compara las filas de cada tabla
en la nube contra la base local.

La base local se adjunta con el nombre `sepa` y en solo lectura: las vistas de dbt (como
fct_precios_historial) buscan sus tablas en "sepa", y con otro nombre fallan. Por eso la base de la
nube se llama distinto.

El token se lee de la variable de entorno motherduck_token: nunca va en el código.

Uso: python -m publicar.subir_marts [tabla ...]   (sin tablas, sube todas)
"""
import logging
import os
import sys
import time

import duckdb

from ingesta import config

BASE_NUBE = "sepa_nube"
TABLAS = ["dim_productos", "fct_precios_historial", "fct_canasta_nacional", "fct_canasta_provincia", "canasta",
          "fct_cobertura"]
log = logging.getLogger("ingesta")


def subir(tablas=TABLAS):
    """Copia las tablas a MotherDuck. Devuelve True si todas quedaron con las mismas filas que en la PC."""
    if not os.environ.get("motherduck_token"):
        log.error("Falta la variable de entorno motherduck_token: no se suben los marts")
        return False
    base_local = (config.DATOS_DIR / "sepa.duckdb").as_posix()
    inicio = time.monotonic()
    con = duckdb.connect("md:")
    try:
        con.execute(f"CREATE DATABASE IF NOT EXISTS {BASE_NUBE}")
        con.execute(f"ATTACH '{base_local}' AS sepa (READ_ONLY)")
        todo_ok = True
        for tabla in tablas:
            t0 = time.monotonic()
            con.execute(f"CREATE OR REPLACE TABLE {BASE_NUBE}.main.{tabla} AS SELECT * FROM sepa.main.{tabla}")
            local = con.execute(f"SELECT count(*) FROM sepa.main.{tabla}").fetchone()[0]
            nube = con.execute(f"SELECT count(*) FROM {BASE_NUBE}.main.{tabla}").fetchone()[0]
            ok = local == nube
            todo_ok &= ok
            (log.info if ok else log.error)(
                f"MotherDuck {tabla}: {nube:,} filas (local {local:,}) en {time.monotonic() - t0:,.1f} s")
    finally:
        con.close()
    log.info(f"Subida a MotherDuck {'OK' if todo_ok else 'CON DIFERENCIAS'} en {time.monotonic() - inicio:,.0f} s")
    return todo_ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(0 if subir(sys.argv[1:] or TABLAS) else 1)