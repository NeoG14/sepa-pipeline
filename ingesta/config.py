import os
from pathlib import Path

URL_CATALOGO = "https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios"
USER_AGENT = "sepa-pipeline-portfolio/0.1 (github.com/NeoG14/sepa-pipeline)"

COMERCIOS = [15, 10, 11, 9, 12, 2, 13]

DATOS_DIR = Path(os.environ.get("SEPA_DATOS_DIR", Path.home() / "sepa-datos"))

DRIVE_DIR = Path(os.environ.get("SEPA_DRIVE_DIR", DATOS_DIR / "drive-prueba"))

PARQUET_DIR = DRIVE_DIR / "parquet"

PARQUET_LOCAL_DIR = DATOS_DIR / "parquet"