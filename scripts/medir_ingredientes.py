"""Qué productos entran en cada ingrediente envasado (seeds/ingredientes.csv) y cuánto cuesta el kilo o el litro
en cada cadena de una provincia. Sirve para revisar las reglas antes de armar la seed (clasificar_ingredientes.py).

Un producto entra en un ingrediente si su rubro es el del ingrediente (vacío = cualquier rubro), su nombre
cumple `incluye` y no cumple `excluye` (regex sobre el nombre en mayúsculas y sin tildes), y su tamaño
está entre `tam_min` y `tam_max` (envases de uso doméstico: así no cuenta el paquete de 3 litros ni un tamaño
mal cargado). El tamaño sale de los campos de presentación de SEPA; si no sirven, o si dicen algo distinto
del nombre ("PAQ 500 GRM", "900 cm3"), vale el nombre. Cencosud, por ejemplo, informa 0,0005 kg para un
paquete de 500 g.
Solo cuentan los precios de una cadena informados en al menos el 5 % de sus sucursales de la provincia.

No usa DeepSeek ni cambia la base. Uso:
  python -m scripts.medir_ingredientes --provincia AR-B
  python -m scripts.medir_ingredientes --provincia AR-B --ingrediente Arroz --todos   (lista todos los que entran)
"""
import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from statistics import median

import duckdb

from ingesta import config
from publicar.exportar_json import CLAVE

RAIZ = Path(__file__).resolve().parents[1]
# unidad de presentación de SEPA -> (unidad del ingrediente, factor)
UNIDADES = {"gr": ("kg", 0.001), "grs": ("kg", 0.001), "grm": ("kg", 0.001), "g": ("kg", 0.001),
            "kg": ("kg", 1), "kgs": ("kg", 1), "kgm": ("kg", 1),
            "ml": ("l", 0.001), "cc": ("l", 0.001), "cm3": ("l", 0.001),
            "lt": ("l", 1), "lts": ("l", 1), "ltr": ("l", 1), "l": ("l", 1)}
# tamaño escrito en el nombre: "500 GRM", "1.5 LTR", "900 CM3"
TAMANO_EN_NOMBRE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(KGS?|KGM|KILOS?|GRS?|GRM|G|LTS?|LTR|LITROS?|L|CC|CM3|ML)\b")
ALIAS = {"kilo": "kg", "kilos": "kg", "litro": "l", "litros": "l"}


def normalizar(texto):
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").upper().strip()


def leer_ingredientes():
    ingredientes = list(csv.DictReader((RAIZ / "seeds" / "ingredientes.csv").open(encoding="utf-8")))
    for i in ingredientes:
        i["incluye_re"] = re.compile(i["incluye"])
        i["excluye_re"] = re.compile(i["excluye"]) if i["excluye"] else None
        i["tam_min"], i["tam_max"] = float(i["tam_min"]), float(i["tam_max"])
    return ingredientes


def tamano_de_campos(cantidad, unidad, unidad_ingrediente):
    """Tamaño que informa la cadena en los campos de presentación, en kg o l (None si no sirve)."""
    conversion = UNIDADES.get((unidad or "").strip(". ").lower())
    if cantidad and conversion and conversion[0] == unidad_ingrediente:
        try:
            return float(str(cantidad).replace(",", ".")) * conversion[1]
        except ValueError:
            return None
    return None


def tamano_de_nombre(nombre_normalizado, unidad_ingrediente):
    """Tamaño escrito en el nombre ("PAQ 500 GRM"), en kg o l. Si hay varios, el último."""
    ultimo = None
    for m in TAMANO_EN_NOMBRE.finditer(nombre_normalizado):
        u = ALIAS.get(m.group(2).lower(), m.group(2).lower())
        conversion = UNIDADES.get(u)
        if conversion and conversion[0] == unidad_ingrediente:
            ultimo = float(m.group(1).replace(",", ".")) * conversion[1]
    return ultimo


def evaluar(ing, nombre, rubro, cantidad, unidad):
    """-> (estado, tamaño, desacuerdo). Estado: 'entra', 'no' (no es ese ingrediente), 'sin_tamano' o
    'fuera_de_rango'. desacuerdo = (tamaño de los campos, tamaño del nombre) si dicen cosas distintas."""
    if ing["rubro"] and rubro != ing["rubro"]:
        return "no", None, None
    n = normalizar(nombre)
    if not ing["incluye_re"].search(n) or (ing["excluye_re"] and ing["excluye_re"].search(n)):
        return "no", None, None
    en_campos, en_nombre = tamano_de_campos(cantidad, unidad, ing["unidad"]), tamano_de_nombre(n, ing["unidad"])
    desacuerdo = None
    if en_campos and en_nombre and abs(en_campos - en_nombre) > 0.05 * en_nombre:
        desacuerdo = (en_campos, en_nombre)   # se cree el nombre
        tamano = en_nombre
    else:
        tamano = en_campos or en_nombre
    if not tamano:
        return "sin_tamano", None, None
    if not ing["tam_min"] <= tamano <= ing["tam_max"]:
        return "fuera_de_rango", tamano, desacuerdo
    return "entra", tamano, desacuerdo


def main():
    a = argparse.ArgumentParser(description="Productos y precios de cada ingrediente envasado")
    a.add_argument("--provincia", default="AR-B")
    a.add_argument("--ingrediente", help="solo este ingrediente")
    a.add_argument("--todos", action="store_true", help="lista todos los productos que entran, no solo los 3 más baratos")
    a = a.parse_args()

    ingredientes = leer_ingredientes()
    if a.ingrediente:
        ingredientes = [i for i in ingredientes if i["ingrediente"] == a.ingrediente]
    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    fecha = con.execute("SELECT max(fecha) FROM int_precios_dia WHERE provincia = ?", [a.provincia]).fetchone()[0]
    carpeta = config.DATOS_DIR / "parquet" / f"fecha={fecha.isoformat()}"
    if not carpeta.exists():
        carpeta = sorted((config.DATOS_DIR / "parquet").glob("fecha=*"))[-1]
    filas = con.execute(f"""
        WITH tam AS (
            SELECT id_comercio, id_producto, any_value(cantidad_presentacion) AS cantidad,
                   lower(trim(any_value(unidad_presentacion))) AS unidad
            FROM read_parquet('{(carpeta / "productos.parquet").as_posix()}')
            GROUP BY ALL)
        SELECT p.id_comercio, d.nombre, d.rubro, p.precio_lista_mediana, t.cantidad, t.unidad
        FROM int_precios_dia p
        JOIN int_cobertura_dia c ON c.fecha = p.fecha AND c.id_comercio = p.id_comercio AND c.provincia = p.provincia
        JOIN dim_productos d ON d.clave = ({CLAVE.replace('id_producto', 'p.id_producto').replace('id_comercio', 'p.id_comercio')})
        LEFT JOIN tam t ON t.id_comercio = p.id_comercio AND t.id_producto = p.id_producto
        WHERE p.fecha = ? AND p.provincia = ? AND p.sucursales >= 0.05 * c.sucursales
    """, [fecha, a.provincia]).fetchall()
    cadenas = dict(con.execute("SELECT id_comercio, nombre FROM cadenas").fetchall())
    con.close()
    print(f"Provincia {a.provincia}, día {fecha}; tamaños de {carpeta.name}; {len(filas):,} precios de productos\n")

    resumen = {}
    for ing in ingredientes:
        por_cadena = defaultdict(list)
        cuenta = defaultdict(int)
        desacuerdos = defaultdict(list)
        for id_comercio, nombre, rubro, precio, cantidad, unidad in filas:
            estado, tamano, desacuerdo = evaluar(ing, nombre, rubro, cantidad, unidad)
            cuenta[estado] += 1
            if desacuerdo:
                desacuerdos[id_comercio].append((nombre, *desacuerdo))
            if estado == "entra":
                por_cadena[id_comercio].append((float(precio) / tamano, float(precio), tamano, nombre))
        resumen[ing["ingrediente"]] = {c: min(l)[0] for c, l in por_cadena.items()}
        print(f"== {ing['ingrediente']} (por {ing['unidad']}; envases de {ing['tam_min']:g} a {ing['tam_max']:g} {ing['unidad']})")
        print(f"   sin tamaño que se pueda leer: {cuenta['sin_tamano']}; fuera del rango de tamaños: {cuenta['fuera_de_rango']}")
        for id_comercio, l in sorted(desacuerdos.items(), key=lambda x: int(x[0])):
            print(f"   {cadenas.get(id_comercio, id_comercio)}: {len(l)} con tamaño distinto en los campos y en el nombre "
                  f"(vale el del nombre); ej.: " + "; ".join(f"{n[:40]} (campos {c:g}, nombre {m:g})" for n, c, m in l[:2]))
        todos = [x[0] for l in por_cadena.values() for x in l]
        if not todos:
            print("   ningún producto\n")
            continue
        print(f"   {len(todos)} productos; mediana de la provincia $ {median(todos):,.0f} por {ing['unidad']}")
        for id_comercio in sorted(por_cadena, key=int):
            l = sorted(por_cadena[id_comercio])
            print(f"   {cadenas.get(id_comercio, id_comercio):<20} {len(l):>3} productos  mínimo $ {l[0][0]:>9,.0f}  "
                  f"mediana $ {median(x[0] for x in l):>9,.0f}")
            for unitario, precio, tamano, nombre in (l if a.todos else l[:3]):
                print(f"        $ {unitario:>9,.0f}  ($ {precio:,.0f} x {tamano:g} {ing['unidad']})  {nombre}")
        print()

    # el precio que usaría el modelo de recetas: el mínimo de cada cadena
    ids = sorted({c for r in resumen.values() for c in r}, key=int)
    print("Mínimo de cada cadena (lo que usaría el modelo de recetas), $ por kg o litro")
    print(f"{'ingrediente':<28}" + "".join(f"{cadenas.get(c, c):>20}" for c in ids))
    for nombre, r in resumen.items():
        print(f"{nombre:<28}" + "".join(f"{r[c]:>20,.0f}" if c in r else f"{'—':>20}" for c in ids))


if __name__ == "__main__":
    main()
