"""Extrae los CSV de UN zip interno de SEPA a una carpeta de destino."""
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

externo, interno, destino = sys.argv[1], sys.argv[2], Path(sys.argv[3])
destino.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(externo) as z, tempfile.TemporaryDirectory() as tmp:
    ruta_tmp = Path(tmp) / "interno.zip"
    with z.open(interno) as origen, open(ruta_tmp, "wb") as salida:
        shutil.copyfileobj(origen, salida)
    with zipfile.ZipFile(ruta_tmp) as zi:
        for info in zi.infolist():
            if info.is_dir():
                continue
            nombre = Path(info.filename).name  # evita rutas raras dentro del zip
            with zi.open(info) as f, open(destino / nombre, "wb") as salida:
                shutil.copyfileobj(f, salida)
            print(f"extraído: {nombre} ({info.file_size / 1e6:.2f} MB)")