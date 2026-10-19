"""Mira dentro de un zip interno de SEPA: archivos, tamaños y primeros bytes."""
import shutil
import sys
import tempfile
import zipfile

externo, interno = sys.argv[1], sys.argv[2]

with zipfile.ZipFile(externo) as z, tempfile.TemporaryDirectory() as tmp:
    ruta_tmp = f"{tmp}/interno.zip"
    with z.open(interno) as origen, open(ruta_tmp, "wb") as destino:
        shutil.copyfileobj(origen, destino)
    with zipfile.ZipFile(ruta_tmp) as zi:
        for i in zi.infolist():
            print(f"{i.filename}  comprimido {i.compress_size / 1e6:.2f} MB  "
                  f"descomprimido {i.file_size / 1e6:.2f} MB")
        print()
        for i in zi.infolist():
            with zi.open(i) as f:
                print(f"--- {i.filename}: primeros 400 bytes ---")
                print(repr(f.read(400)))
                print()