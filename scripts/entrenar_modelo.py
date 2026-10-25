"""Entrena el modelo de rubros y lo compara con las reglas en el conjunto de DESARROLLO (paso 6).

Modelo: TF-IDF de fragmentos de 2 a 5 caracteres (resiste abreviaturas como "FID." o "DCE DE
LECHE") y de palabras sueltas y pares, más una regresión logística con clases balanceadas. El
texto de cada producto son todas sus descripciones juntas más la marca.

Entrena con las etiquetas débiles (armar_entrenamiento.py) y con los 300 de desarrollo. Para
medir en desarrollo sin que el modelo se vea a sí mismo se usa validación cruzada: los 300 se
parten en 5 grupos de 60; para cada grupo se entrena con las débiles y los otros 240, y se
predicen esos 60. Así cada producto de desarrollo tiene una predicción hecha sin verlo.

Compara, con las mismas métricas y separado por estrato:
  reglas        la votación de scripts/rubros.py (sin regla = sin clasificar)
  modelo        el rubro más probable del modelo
  combinación   las reglas cuando todas las cadenas votan lo mismo; el modelo para el resto
y muestra la curva de cobertura contra aciertos según el umbral de probabilidad.

Ojo: las reglas se escribieron mirando desarrollo, y las etiquetas débiles salen de esas reglas.
En desarrollo, reglas y combinación salen favorecidas. El número que vale es el de prueba (paso 7).
Los 300 de prueba no se leen en este script.

Escribe <carpeta de datos>/clasificacion/predicciones_desarrollo.csv para el análisis de errores.
Uso: python -m scripts.entrenar_modelo
"""
import csv
import json
import time
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import KFold
from sklearn.pipeline import FeatureUnion, make_pipeline

from ingesta import config
from scripts.rubros import RENOMBRADOS, rubro_de_producto

RAIZ_REPO = Path(__file__).resolve().parents[1]
CARPETA = RAIZ_REPO / "etiquetado"
CLASIFICACION = config.DATOS_DIR / "clasificacion"
SEMILLA = 42
GRUPOS = 5
PESO_DESARROLLO = 5      # una etiqueta hecha a mano pesa como 5 débiles
C = 10                   # regularización de la regresión logística (más alto = menos regularización)
SIN_CLASIFICAR = "(sin clasificar)"
UMBRALES = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def leer_csv(ruta):
    with open(ruta, encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def texto(descripciones, marca):
    """El texto que ve el modelo: descripciones y marca, en mayúsculas y sin tildes."""
    crudo = " | ".join(descripciones) + " | " + (marca or "")
    descompuesto = unicodedata.normalize("NFD", crudo.upper())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def nuevo_modelo():
    variables = FeatureUnion([
        ("caracteres", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3,
                                       sublinear_tf=True, max_features=300_000)),
        ("palabras", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2,
                                     token_pattern=r"(?u)\b\w+\b", sublinear_tf=True)),
    ])
    clasificador = LogisticRegression(C=C, class_weight="balanced", max_iter=2000)
    return make_pipeline(variables, clasificador)


def reglas(descripciones):
    """Rubro de las reglas y si todas las cadenas votan lo mismo."""
    rubro = rubro_de_producto(descripciones)
    unanime = rubro is not None and all(rubro_de_producto([d]) == rubro for d in descripciones)
    return RENOMBRADOS.get(rubro, rubro), unanime


def medir(humano, prediccion):
    """Cobertura, acierto entre los clasificados, acierto sobre todos y F1 macro."""
    n = len(humano)
    cubiertos = [(h, p) for h, p in zip(humano, prediccion) if p != SIN_CLASIFICAR]
    bien = sum(h == p for h, p in cubiertos)
    # F1 macro sobre los rubros que aparecen en las etiquetas: cada rubro pesa igual
    f1 = f1_score(humano, prediccion, labels=sorted(set(humano)), average="macro", zero_division=0)
    return {"cobertura": len(cubiertos) / n, "acierto": bien / len(cubiertos) if cubiertos else 0,
            "acierto_total": bien / n, "f1_macro": f1}


def main():
    inicio = time.time()
    muestra = {f["clave"]: f for f in leer_csv(CARPETA / "muestra.csv")}
    # Solo la ronda 1: la ronda 2 fue la de consistencia
    etiquetas = {f["clave"]: f["rubro"] for f in leer_csv(CARPETA / "etiquetas.csv") if f["ronda"] != "2"}
    productos = {p["clave"]: p for p in json.loads(
        (CARPETA / "productos.json").read_text(encoding="utf-8"))["productos"]}

    desarrollo = sorted(c for c, f in muestra.items() if f["conjunto"] == "desarrollo")
    assert len(desarrollo) == 300 and all(c in etiquetas for c in desarrollo)
    dev_desc = [[d["descripcion"] or "" for d in productos[c]["descripciones"]] for c in desarrollo]
    dev_x = np.array([texto(ds, productos[c]["marca"]) for c, ds in zip(desarrollo, dev_desc)], dtype=object)
    dev_y = np.array([etiquetas[c] for c in desarrollo], dtype=object)
    dev_estrato = [muestra[c]["estrato"] for c in desarrollo]

    debiles = leer_csv(CLASIFICACION / "etiquetas_debiles.csv")
    assert not {f["clave"] for f in debiles} & set(muestra), "hay productos de la muestra en las débiles"
    deb_x = np.array([texto(f["descripciones"].split(" | "), f["marca"]) for f in debiles], dtype=object)
    deb_y = np.array([f["rubro"] for f in debiles], dtype=object)
    print(f"Entrenamiento: {len(debiles):,} etiquetas débiles + 300 de desarrollo (peso {PESO_DESARROLLO})")
    faltan = sorted(set(dev_y) - set(deb_y))
    print(f"Rubros de desarrollo sin ningún ejemplo débil: {', '.join(faltan) or 'ninguno'}\n")

    # Validación cruzada: cada producto de desarrollo se predice con un modelo que no lo vio
    prob_max = np.zeros(300)
    pred_modelo = np.empty(300, dtype=object)
    for i, (entrena, evalua) in enumerate(KFold(GRUPOS, shuffle=True, random_state=SEMILLA).split(dev_x), 1):
        x = np.concatenate([deb_x, dev_x[entrena]])
        y = np.concatenate([deb_y, dev_y[entrena]])
        pesos = np.concatenate([np.ones(len(deb_x)), np.full(len(entrena), PESO_DESARROLLO)])
        modelo = nuevo_modelo()
        modelo.fit(x, y, logisticregression__sample_weight=pesos)
        prob = modelo.predict_proba(dev_x[evalua])
        clases = modelo.classes_
        pred_modelo[evalua] = clases[prob.argmax(axis=1)]
        prob_max[evalua] = prob.max(axis=1)
        print(f"  grupo {i} de {GRUPOS}: entrenado con {len(y):,} productos ({time.time() - inicio:,.0f} s)")

    regla = [reglas(ds) for ds in dev_desc]
    pred_reglas = [r or SIN_CLASIFICAR for r, _ in regla]
    pred_comb = [r if unanime else m for (r, unanime), m in zip(regla, pred_modelo)]
    print(f"\nLas reglas votan unánime en {sum(u for _, u in regla)} de 300; "
          f"el modelo decide los otros {sum(not u for _, u in regla)}\n")

    metodos = {"reglas": pred_reglas, "modelo": list(pred_modelo), "combinación": pred_comb}
    print(f"{'estrato':<14}{'método':<13}{'productos':>10}{'cobertura':>11}{'acierto':>9}"
          f"{'acierto total':>15}{'F1 macro':>10}")
    for estrato in ["todos", "comparables", "una cadena", "pesables"]:
        indices = [i for i, e in enumerate(dev_estrato) if estrato in ("todos", e)]
        for nombre, pred in metodos.items():
            m = medir([dev_y[i] for i in indices], [pred[i] for i in indices])
            print(f"{estrato:<14}{nombre:<13}{len(indices):>10}{m['cobertura']:>11.1%}{m['acierto']:>9.1%}"
                  f"{m['acierto_total']:>15.1%}{m['f1_macro']:>10.3f}")
        print()
    print("cobertura = % con rubro; acierto = bien entre los que tienen rubro; acierto total = bien sobre todos\n")

    print("Curva según el umbral (el modelo deja sin clasificar si su probabilidad es menor):")
    print(f"{'umbral':>7}   {'modelo: cobertura':>18}{'acierto':>9}   {'combinación: cobertura':>23}{'acierto':>9}")
    unanime = np.array([u for _, u in regla])
    for umbral in UMBRALES:
        solo = [m if p >= umbral else SIN_CLASIFICAR for m, p in zip(pred_modelo, prob_max)]
        comb = [c if (u or p >= umbral) else SIN_CLASIFICAR for c, u, p in zip(pred_comb, unanime, prob_max)]
        a, b = medir(list(dev_y), solo), medir(list(dev_y), comb)
        print(f"{umbral:>7.1f}   {a['cobertura']:>18.1%}{a['acierto']:>9.1%}   {b['cobertura']:>23.1%}{b['acierto']:>9.1%}")

    print("\nDónde se equivoca la combinación (humano contra predicción):")
    for (h, p), n in Counter((h, p) for h, p in zip(dev_y, pred_comb) if h != p).most_common(15):
        print(f"  {n:>3}  humano: {h:<28} predicción: {p}")

    salida = CLASIFICACION / "predicciones_desarrollo.csv"
    with open(salida, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["clave", "estrato", "humano", "reglas", "unanime", "modelo", "probabilidad",
                           "combinacion", "nombre"])
        for i, c in enumerate(desarrollo):
            escritor.writerow([c, dev_estrato[i], dev_y[i], pred_reglas[i], regla[i][1], pred_modelo[i],
                               round(float(prob_max[i]), 3), pred_comb[i], productos[c]["nombre"]])
    print(f"\nEscrito {salida}   ({time.time() - inicio:,.0f} s en total)")


if __name__ == "__main__":
    main()
