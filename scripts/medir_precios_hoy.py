"""Mide cuánto pesaría un archivo por provincia con el precio más bajo de hoy de cada producto.

Lee los JSON de historia ya exportados (sitio/datos/historia) y, para cada provincia, arma
{clave: [precio_mas_bajo, cadenas]}, donde cadenas es un número que marca qué cadenas tienen ese
precio (un bit por cadena). Solo cuentan las cadenas que siguen vendiendo el producto (vistas en
los últimos 7 días). Uso: python -m scripts.medir_precios_hoy
"""
import gzip
import json
from pathlib import Path

DATOS = Path(__file__).resolve().parents[1] / "sitio" / "datos"
BIT = {"2": 1, "9": 2, "10": 4, "11": 8, "12": 16, "13": 32, "15": 64}

meta = json.loads((DATOS / "meta.json").read_text(encoding="utf-8"))
hoy = meta["dia_dato"]
por_provincia = {}
for archivo in sorted((DATOS / "historia").glob("*.json")):
    for clave, provincias in json.loads(archivo.read_text(encoding="utf-8")).items():
        for provincia, cadenas in provincias.items():
            vigentes = {c: l["p"][-1][1] for c, l in cadenas.items() if hoy - l["u"] <= 7}
            if not vigentes:
                continue
            minimo = min(vigentes.values())
            mascara = sum(BIT.get(c, 0) for c, precio in vigentes.items() if precio == minimo)
            por_provincia.setdefault(provincia, {})[clave] = [minimo, mascara]

total = total_gz = 0
for provincia, productos in sorted(por_provincia.items(), key=lambda x: -len(x[1])):
    texto = json.dumps(productos, separators=(",", ":")).encode()
    total += len(texto)
    total_gz += len(gzip.compress(texto))
    print(f"{provincia}: {len(productos):>6,} productos | {len(texto) / 1024:>7,.0f} KB | "
          f"{len(gzip.compress(texto)) / 1024:>5,.0f} KB comprimido")
print(f"\nTodas: {total / 1024 / 1024:,.1f} MB | {total_gz / 1024 / 1024:,.1f} MB comprimido")