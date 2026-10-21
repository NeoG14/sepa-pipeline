"""Muestra lo que el sitio va a leer de hoy/<provincia>.json para los productos que coinciden con un texto.

Sirve para controlar a mano el exportador: busca en indice.json (sin importar tildes ni mayúsculas,
todas las palabras tienen que estar en el nombre o la marca) y muestra la fila tal cual está en el
JSON y traducida: el precio de cada cadena y los cambios de los últimos días.

Uso: python scripts/ver_hoy.py "dulce de leche serenisima" [--provincia AR-B] [--datos sitio/datos]
"""
import argparse
import json
import unicodedata
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]


def normalizar(texto):
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def main():
    argumentos = argparse.ArgumentParser(description="Muestra filas de hoy/<provincia>.json")
    argumentos.add_argument("texto")
    argumentos.add_argument("--provincia", default="AR-B")
    argumentos.add_argument("--datos", type=Path, default=RAIZ_REPO / "sitio" / "datos")
    argumentos.add_argument("--max", type=int, default=10, help="cuántos productos mostrar como máximo")
    a = argumentos.parse_args()

    leer = lambda nombre: json.loads((a.datos / nombre).read_text(encoding="utf-8"))
    meta, indice = leer("meta.json"), leer("indice.json")
    hoy = leer(f"hoy/{a.provincia}.json")
    orden = meta["orden_cadenas"]
    nombres = {c: datos["nombre"] for c, datos in meta["cadenas"].items()}
    print(f"Fecha del dato: {meta['fecha_dato']} | provincia {a.provincia} | orden de las cadenas: "
          + ", ".join(f"{i}={nombres.get(c, c)}" for i, c in enumerate(orden)))

    palabras = normalizar(a.texto).split()
    encontrados = [fila for fila in indice
                   if all(p in normalizar(f"{fila[1]} {fila[2] or ''}") for p in palabras)]
    con_precio = [fila for fila in encontrados if fila[0] in hoy]
    print(f"{len(encontrados)} productos coinciden; {len(con_precio)} tienen precio hoy en {a.provincia}")

    for clave, nombre, marca, presentacion, *_ in con_precio[:a.max]:
        fila = hoy[clave]
        precios, cambios = (fila[:-1], fila[-1]) if isinstance(fila[-1], list) else (fila, [])
        print(f"\n{nombre} | {marca} | {presentacion} | clave {clave}")
        print("  en el JSON:", json.dumps(fila, separators=(",", ":")))
        for c, p in zip(orden, precios):
            if p:
                print(f"  {nombres.get(c, c):<22}{p:>10,}")
        for posicion, hace, anterior in cambios:
            cadena = nombres.get(orden[posicion], orden[posicion])
            print(f"  cambio: {cadena} hace {hace} días; antes costaba {anterior:,}")


if __name__ == "__main__":
    main()
