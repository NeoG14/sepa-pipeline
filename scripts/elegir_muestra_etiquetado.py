"""Elige los 600 productos que se etiquetan a mano (paso 4 del plan de categorización) y arma el
archivo que lee la página de etiquetado.

Población: productos que se vendieron en los últimos días que guarda int_precios_dia (21 por
defecto), así cada uno tiene un precio para mostrar y la muestra se parece al catálogo que ve
el sitio. Tres estratos:

  comparables     código de barras, vendido por 2 cadenas o más          350
  una cadena      código de barras, vendido por una sola cadena          150
  pesables        código de balanza (13 dígitos que empiezan con 2)      100

Quedan afuera los códigos internos que no son de balanza: no tienen estrato en el plan.

Dentro de cada estrato se mezcla con una semilla fija y la primera mitad va a desarrollo y la
segunda a prueba. De los 600 se marcan 50 para repetir en la ronda de consistencia,
proporcionales a cada estrato (29, 13 y 8). La columna orden mezcla los tres estratos: es el
orden en que la página muestra los productos.

La muestra se guarda UNA vez en etiquetado/muestra.csv. Si el archivo ya existe no se vuelve a
elegir (cada día entran productos nuevos y la muestra cambiaría); solo se regenera
etiquetado/productos.json con las descripciones. --rehacer elige de nuevo, y solo tiene sentido
antes de empezar a etiquetar.

productos.json NO trae el rubro que proponen las reglas, a propósito: ver la guía de etiquetado.

Lee la base local en solo lectura.
Uso: python -m scripts.elegir_muestra_etiquetado [--semilla 42] [--rehacer]
"""
import argparse
import csv
import json
import random
from datetime import datetime
from pathlib import Path

import duckdb

from ingesta import config

RAIZ_REPO = Path(__file__).resolve().parents[1]
CARPETA = RAIZ_REPO / "etiquetado"
MUESTRA = CARPETA / "muestra.csv"
PRODUCTOS = CARPETA / "productos.json"
RUBROS = RAIZ_REPO / "seeds" / "rubros.csv"

# estrato: (productos, de ellos para repetir en la ronda de consistencia)
ESTRATOS = {"comparables": (350, 29), "una cadena": (150, 13), "pesables": (100, 8)}

POBLACION = """
    WITH vendidos AS (
        SELECT DISTINCT m.clave
        FROM int_precios_dia p JOIN claves m USING (id_comercio, id_producto))
    SELECT d.clave,
           CASE WHEN d.es_ean AND d.cadenas >= 2 THEN 'comparables'
                WHEN d.es_ean THEN 'una cadena'
                WHEN regexp_full_match(split_part(d.clave, '-', 2), '2\\d{12}') THEN 'pesables'
           END AS estrato
    FROM dim_productos d JOIN vendidos USING (clave)
"""


def elegir(con, semilla):
    """Devuelve las filas de muestra.csv: clave, estrato, conjunto, repetir, orden."""
    poblacion = {estrato: [] for estrato in ESTRATOS}
    afuera = 0
    for clave, estrato in con.execute(POBLACION).fetchall():
        if estrato is None:
            afuera += 1
        else:
            poblacion[estrato].append(clave)

    print("Población (vendidos en la ventana de int_precios_dia):")
    for estrato, claves in poblacion.items():
        print(f"  {estrato:<14}{len(claves):>9,}")
    print(f"  {'afuera':<14}{afuera:>9,}   (códigos internos que no son de balanza)\n")

    azar = random.Random(semilla)
    filas = []
    for estrato, (cuantos, repetir) in ESTRATOS.items():
        # Ordenar antes de mezclar: con la misma población y la misma semilla sale lo mismo
        claves = sorted(poblacion[estrato])
        if len(claves) < cuantos:
            raise SystemExit(f"{estrato}: hay {len(claves)} productos y hacen falta {cuantos}")
        elegidos = azar.sample(claves, cuantos)
        para_repetir = set(azar.sample(elegidos, repetir))
        for i, clave in enumerate(elegidos):
            filas.append({"clave": clave, "estrato": estrato,
                          "conjunto": "desarrollo" if i < cuantos // 2 else "prueba",
                          "repetir": "si" if clave in para_repetir else "no"})
    orden = list(range(1, len(filas) + 1))
    azar.shuffle(orden)
    for fila, n in zip(filas, orden):
        fila["orden"] = n
    return sorted(filas, key=lambda f: f["orden"])


def productos_para_la_pagina(con, filas):
    """Lo que la página muestra de cada producto. Sin el rubro de las reglas."""
    con.execute("CREATE TEMP TABLE muestra(clave VARCHAR)")
    con.executemany("INSERT INTO muestra VALUES (?)", [(f["clave"],) for f in filas])
    # Precio de cada cadena: la mediana entre provincias del último día en que lo vendió
    descripciones = {}
    for clave, cadena, descripcion, marca, precio in con.execute("""
        WITH descripciones AS (
            SELECT s.clave, s.id_comercio,
                   arg_max(s.descripcion, s.fecha) AS descripcion,
                   arg_max(s.marca, s.fecha) AS marca
            FROM stg_productos s JOIN muestra USING (clave)
            GROUP BY ALL),
        precios AS (
            SELECT m.clave, p.id_comercio, p.fecha, median(p.precio_lista_mediana) AS precio
            FROM int_precios_dia p
            JOIN claves m USING (id_comercio, id_producto)
            JOIN muestra USING (clave)
            GROUP BY m.clave, p.id_comercio, p.fecha
            QUALIFY p.fecha = max(p.fecha) OVER (PARTITION BY m.clave, p.id_comercio))
        SELECT d.clave, coalesce(c.nombre, d.id_comercio::VARCHAR), d.descripcion, d.marca,
               round(p.precio, 2)::DOUBLE
        FROM descripciones d
        LEFT JOIN precios p USING (clave, id_comercio)
        LEFT JOIN cadenas c USING (id_comercio)
        ORDER BY d.clave, 2
    """).fetchall():
        descripciones.setdefault(clave, []).append(
            {"cadena": cadena, "descripcion": descripcion, "marca": marca, "precio": precio})

    datos = {clave: (nombre, marca, cadenas) for clave, nombre, marca, cadenas in con.execute(
        "SELECT clave, nombre, marca, cadenas FROM dim_productos JOIN muestra USING (clave)").fetchall()}

    productos = []
    for f in filas:
        nombre, marca, cadenas = datos[f["clave"]]
        precios = sorted(d["precio"] for d in descripciones[f["clave"]] if d["precio"] is not None)
        mediana = None
        if precios:
            medio = len(precios) // 2
            mediana = precios[medio] if len(precios) % 2 else round((precios[medio - 1] + precios[medio]) / 2, 2)
        productos.append({
            "clave": f["clave"], "orden": int(f["orden"]), "estrato": f["estrato"],
            "repetir": f["repetir"] == "si", "nombre": nombre, "marca": marca, "cadenas": cadenas,
            "pesable": f["estrato"] == "pesables", "precio_mediano": mediana,
            "descripciones": descripciones[f["clave"]],
        })
    # El conjunto (desarrollo o prueba) no va a la página: etiquetar sin saberlo evita tratar
    # distinto a los de prueba
    return productos


def main():
    argumentos = argparse.ArgumentParser(description="Muestra para etiquetar a mano")
    argumentos.add_argument("--semilla", type=int, default=42)
    argumentos.add_argument("--rehacer", action="store_true", help="volver a elegir la muestra")
    a = argumentos.parse_args()

    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    con.execute("CREATE TEMP TABLE claves AS SELECT DISTINCT id_comercio, id_producto, clave FROM stg_productos")
    CARPETA.mkdir(exist_ok=True)

    if MUESTRA.exists() and not a.rehacer:
        with open(MUESTRA, encoding="utf-8", newline="") as archivo:
            filas = list(csv.DictReader(archivo))
        print(f"{MUESTRA.name} ya existe: se usa tal cual ({len(filas)} productos). --rehacer elige de nuevo.\n")
    else:
        filas = elegir(con, a.semilla)
        with open(MUESTRA, "w", encoding="utf-8", newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=["clave", "estrato", "conjunto", "repetir", "orden"])
            escritor.writeheader()
            escritor.writerows(filas)
        print(f"Muestra elegida con semilla {a.semilla} y guardada en {MUESTRA.relative_to(RAIZ_REPO)}\n")

    productos = productos_para_la_pagina(con, filas)
    con.close()

    with open(RUBROS, encoding="utf-8", newline="") as archivo:
        rubros = [{"grupo": r["grupo"], "rubro": r["rubro"], "descripcion": r["descripcion"]}
                  for r in csv.DictReader(archivo)]
    PRODUCTOS.write_text(json.dumps({
        "generado": datetime.now().isoformat(timespec="seconds"),
        "rubros": rubros,
        "productos": productos,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{PRODUCTOS.relative_to(RAIZ_REPO)}: {len(productos)} productos, {len(rubros)} rubros, "
          f"{PRODUCTOS.stat().st_size / 1024:,.0f} KB\n")

    # Verificación
    print(f"{'estrato':<14}{'desarrollo':>12}{'prueba':>9}{'repetir':>9}")
    for estrato in ESTRATOS:
        de = [f for f in filas if f["estrato"] == estrato]
        print(f"{estrato:<14}{sum(f['conjunto'] == 'desarrollo' for f in de):>12}"
              f"{sum(f['conjunto'] == 'prueba' for f in de):>9}{sum(f['repetir'] == 'si' for f in de):>9}")
    claves = [f["clave"] for f in filas]
    print(f"\nclaves repetidas: {len(claves) - len(set(claves))}")
    print(f"sin descripción: {sum(not p['descripciones'] for p in productos)}")
    print(f"sin precio: {sum(p['precio_mediano'] is None for p in productos)}")
    print(f"orden de 1 a {len(filas)} sin huecos: {sorted(int(f['orden']) for f in filas) == list(range(1, len(filas) + 1))}")

    print("\nLos primeros 8 en el orden de la página:")
    for p in productos[:8]:
        cadenas = ", ".join(d["cadena"] for d in p["descripciones"])
        print(f"  {p['orden']:>3}  {p['estrato']:<12}{p['nombre'][:45]:<47}{cadenas}")


if __name__ == "__main__":
    main()
