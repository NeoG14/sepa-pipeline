"""Arma las etiquetas débiles para entrenar el modelo de rubros (paso 6 del plan de categorización).

Etiquetar miles de productos a mano no es viable, así que el modelo aprende también de productos
que las reglas clasifican sin dudas: cada descripción del producto, una por cadena, cae en el
MISMO rubro. Un producto con una sola descripción (una cadena o pesable) entra si esa descripción
tiene regla. Los 600 de la muestra etiquetada quedan afuera siempre: los de desarrollo entran al
entrenamiento con su etiqueta hecha a mano (en entrenar_modelo.py) y los de prueba no se tocan.

Población: la misma de la muestra (productos vendidos en la ventana de int_precios_dia, en los
tres estratos), así el modelo aprende del catálogo que ve el sitio.

Lee la base local en solo lectura. Escribe <carpeta de datos>/clasificacion/etiquetas_debiles.csv
con: clave, estrato, rubro, marca, descripciones (las de cada cadena separadas por " | ").

Uso: python -m scripts.armar_entrenamiento
"""
import csv
import random
from collections import Counter
from pathlib import Path

import duckdb

from ingesta import config
from scripts.elegir_muestra_etiquetado import POBLACION
from scripts.rubros import RENOMBRADOS, rubro_de_producto

RAIZ_REPO = Path(__file__).resolve().parents[1]
SALIDA = config.DATOS_DIR / "clasificacion" / "etiquetas_debiles.csv"
SEPARADOR = " | "


def leer_csv(ruta):
    with open(ruta, encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def main():
    muestra = {f["clave"] for f in leer_csv(RAIZ_REPO / "etiquetado" / "muestra.csv")}
    taxonomia = {f["rubro"] for f in leer_csv(RAIZ_REPO / "seeds" / "rubros.csv")}

    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    # La consulta POBLACION usa esta tabla temporal (la misma que arma elegir_muestra_etiquetado)
    con.execute("CREATE TEMP TABLE claves AS SELECT DISTINCT id_comercio, id_producto, clave FROM stg_productos")
    con.execute(f"CREATE TEMP TABLE poblacion AS SELECT * FROM ({POBLACION}) WHERE estrato IS NOT NULL")
    filas = con.execute("""
        WITH d AS (
            SELECT s.clave, s.id_comercio, arg_max(s.descripcion, s.fecha) AS descripcion
            FROM stg_productos s JOIN poblacion USING (clave)
            GROUP BY ALL)
        SELECT p.clave, p.estrato, coalesce(dp.marca, '') AS marca,
               list(d.descripcion ORDER BY d.id_comercio) FILTER (WHERE d.descripcion IS NOT NULL) AS descripciones
        FROM poblacion p
        JOIN d USING (clave)
        JOIN dim_productos dp USING (clave)
        GROUP BY ALL
    """).fetchall()
    con.close()
    print(f"Población: {len(filas):,} productos vendidos en la ventana de int_precios_dia\n")

    cuenta = {e: Counter() for e in ("comparables", "una cadena", "pesables")}
    elegidos = []
    for clave, estrato, marca, descripciones in filas:
        c = cuenta[estrato]
        c["productos"] += 1
        if clave in muestra:
            c["en la muestra (afuera)"] += 1
            continue
        descripciones = descripciones or []
        rubro = rubro_de_producto(descripciones)
        if rubro is None:
            c["sin regla"] += 1
            continue
        # Unánime: cada descripción, sola, da el mismo rubro que el producto
        if any(rubro_de_producto([d]) != rubro for d in descripciones):
            c["cadenas en desacuerdo"] += 1
            continue
        rubro = RENOMBRADOS.get(rubro, rubro)
        if rubro not in taxonomia:
            # "congelados" sin saber de qué tipo: no es un rubro de la taxonomía
            c["rubro fuera de la taxonomía"] += 1
            continue
        c["etiqueta débil"] += 1
        elegidos.append({"clave": clave, "estrato": estrato, "rubro": rubro, "marca": marca,
                         "descripciones": SEPARADOR.join(d.replace("|", "/") for d in descripciones)})

    columnas = ["productos", "en la muestra (afuera)", "sin regla", "cadenas en desacuerdo",
                "rubro fuera de la taxonomía", "etiqueta débil"]
    print(f"{'estrato':<14}" + "".join(f"{c:>14}" for c in ["productos", "en muestra", "sin regla",
                                                            "desacuerdo", "fuera taxon.", "débiles"]))
    for estrato, c in cuenta.items():
        print(f"{estrato:<14}" + "".join(f"{c[k]:>14,}" for k in columnas))
    total = Counter()
    for c in cuenta.values():
        total.update(c)
    print(f"{'total':<14}" + "".join(f"{total[k]:>14,}" for k in columnas))

    claves = {f["clave"] for f in elegidos}
    assert not claves & muestra, "una clave de la muestra se coló en las etiquetas débiles"
    assert len(claves) == len(elegidos), "claves repetidas"

    por_rubro = Counter(f["rubro"] for f in elegidos)
    print(f"\nRubros con etiqueta débil: {len(por_rubro)} de {len(taxonomia)}")
    print("Sin ningún ejemplo débil (el modelo solo los aprende de los 300 de desarrollo):")
    print("  " + (", ".join(sorted(taxonomia - set(por_rubro))) or "ninguno"))
    print("Con menos de 20 ejemplos:")
    print("  " + (", ".join(f"{r} ({n})" for r, n in sorted(por_rubro.items(), key=lambda x: x[1]) if n < 20)
                  or "ninguno"))
    print("Los 10 con más ejemplos:")
    for rubro, n in por_rubro.most_common(10):
        print(f"  {n:>7,}  {rubro}")

    azar = random.Random(6)
    print("\n20 al azar, para revisar a ojo si la etiqueta débil es razonable:")
    for f in azar.sample(elegidos, min(20, len(elegidos))):
        print(f"  {f['rubro']:<28}{f['descripciones'][:60]}")

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(elegidos[0]))
        escritor.writeheader()
        escritor.writerows(elegidos)
    print(f"\nEscrito {SALIDA} ({len(elegidos):,} productos)")


if __name__ == "__main__":
    main()
