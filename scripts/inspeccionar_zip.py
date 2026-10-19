"""Inspecciona un zip de SEPA sin extraerlo."""
import sys
import zipfile

ruta = sys.argv[1]
with zipfile.ZipFile(ruta) as z:
    infos = z.infolist()
    print(f"Entradas en el zip externo: {len(infos)}")
    comprimido = sum(i.compress_size for i in infos)
    descomprimido = sum(i.file_size for i in infos)
    print(f"Comprimido: {comprimido / 1e6:.1f} MB | Descomprimido: {descomprimido / 1e6:.1f} MB")
    extensiones = {}
    for i in infos:
        ext = i.filename.rsplit(".", 1)[-1].lower() if "." in i.filename else "(sin extensión)"
        extensiones[ext] = extensiones.get(ext, 0) + 1
    print("Por extensión:", extensiones)
    print("Primeras 10 entradas:")
    for i in infos[:10]:
        print(f"  {i.filename}  ({i.file_size / 1e6:.2f} MB)")