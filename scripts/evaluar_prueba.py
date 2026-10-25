"""Evaluación final en el conjunto de PRUEBA (paso 7 del plan de categorización). Se corre UNA vez.

1. Comprueba que scripts/rubros.py es el congelado (mismo SHA256 que quedó en el plan).
2. Entrena el modelo final con todas las etiquetas débiles y los 300 de desarrollo (los mismos
   parámetros que en el paso 6) y lo guarda en la carpeta de datos.
3. Clasifica los 300 de prueba con reglas, modelo y combinación (umbral 0,4, elegido en
   desarrollo) y mide todo por estrato, contra el criterio de éxito del plan:
     - la combinación supera a las reglas en acierto y en cobertura
     - comparables: 90 % de acierto y 90 % de cobertura como piso; pesables: 85 % y 75 %

Después de mirar estos números ya no se cambian reglas, etiquetas, parámetros ni umbral: si se
cambiaran, prueba dejaría de ser una medición limpia. Por eso el script se niega a correr si
predicciones_prueba.csv ya existe.

Escribe en <carpeta de datos>/clasificacion/: modelo_rubros.joblib y predicciones_prueba.csv.
Uso: python -m scripts.evaluar_prueba
"""
import csv
import hashlib
import json
import time
from collections import Counter

import joblib
import numpy as np

from scripts.entrenar_modelo import (CARPETA, CLASIFICACION, PESO_DESARROLLO, RAIZ_REPO, SIN_CLASIFICAR,
                                     leer_csv, medir, nuevo_modelo, reglas, texto)

HASH_REGLAS = "218CF093F8BBC3FBAD0BF7334492DB124A31D5DA22C4C1C0EC876A3D49997A0A"
UMBRAL = 0.4
PISOS = {"comparables": (0.90, 0.90), "pesables": (0.85, 0.75)}   # (acierto, cobertura)
SALIDA = CLASIFICACION / "predicciones_prueba.csv"
MODELO = CLASIFICACION / "modelo_rubros.joblib"


def main():
    inicio = time.time()
    if SALIDA.exists():
        raise SystemExit(f"{SALIDA} ya existe: la evaluación en prueba se hace una sola vez.")
    hash_actual = hashlib.sha256((RAIZ_REPO / "scripts" / "rubros.py").read_bytes()).hexdigest().upper()
    if hash_actual != HASH_REGLAS:
        raise SystemExit(f"scripts/rubros.py cambió desde que se congeló (SHA256 {hash_actual}).")
    print("scripts/rubros.py es el congelado (SHA256 coincide)\n")

    muestra = {f["clave"]: f for f in leer_csv(CARPETA / "muestra.csv")}
    etiquetas = {f["clave"]: f["rubro"] for f in leer_csv(CARPETA / "etiquetas.csv") if f["ronda"] != "2"}
    productos = {p["clave"]: p for p in json.loads(
        (CARPETA / "productos.json").read_text(encoding="utf-8"))["productos"]}

    def conjunto(nombre):
        claves = sorted(c for c, f in muestra.items() if f["conjunto"] == nombre)
        assert len(claves) == 300 and all(c in etiquetas for c in claves)
        descripciones = [[d["descripcion"] or "" for d in productos[c]["descripciones"]] for c in claves]
        x = np.array([texto(ds, productos[c]["marca"]) for c, ds in zip(claves, descripciones)], dtype=object)
        y = np.array([etiquetas[c] for c in claves], dtype=object)
        return claves, descripciones, x, y

    _, _, dev_x, dev_y = conjunto("desarrollo")
    claves, prueba_desc, prueba_x, prueba_y = conjunto("prueba")
    estrato = [muestra[c]["estrato"] for c in claves]

    debiles = leer_csv(CLASIFICACION / "etiquetas_debiles.csv")
    assert not {f["clave"] for f in debiles} & set(muestra), "hay productos de la muestra en las débiles"
    x = np.concatenate([np.array([texto(f["descripciones"].split(" | "), f["marca"]) for f in debiles],
                                 dtype=object), dev_x])
    y = np.concatenate([np.array([f["rubro"] for f in debiles], dtype=object), dev_y])
    pesos = np.concatenate([np.ones(len(debiles)), np.full(300, PESO_DESARROLLO)])
    print(f"Entrenando el modelo final con {len(y):,} productos (unos 2 minutos)...")
    modelo = nuevo_modelo()
    modelo.fit(x, y, logisticregression__sample_weight=pesos)
    MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, MODELO)
    print(f"Guardado {MODELO} ({MODELO.stat().st_size / 1e6:,.0f} MB, {time.time() - inicio:,.0f} s)\n")

    prob = modelo.predict_proba(prueba_x)
    pred_modelo = modelo.classes_[prob.argmax(axis=1)]
    prob_max = prob.max(axis=1)
    regla = [reglas(ds) for ds in prueba_desc]
    pred_reglas = [r or SIN_CLASIFICAR for r, _ in regla]
    pred_comb = [r if u else (m if p >= UMBRAL else SIN_CLASIFICAR)
                 for (r, u), m, p in zip(regla, pred_modelo, prob_max)]
    print(f"Prueba: 300 productos. Las reglas votan unánime en {sum(u for _, u in regla)}; "
          f"el modelo decide el resto con umbral {UMBRAL}\n")

    metodos = {"reglas": pred_reglas, "modelo": list(pred_modelo), "combinación": pred_comb}
    resultados = {}
    print(f"{'estrato':<14}{'método':<13}{'productos':>10}{'cobertura':>11}{'acierto':>9}"
          f"{'acierto total':>15}{'F1 macro':>10}")
    for e in ["todos", "comparables", "una cadena", "pesables"]:
        indices = [i for i, x_ in enumerate(estrato) if e in ("todos", x_)]
        for nombre, pred in metodos.items():
            m = medir([prueba_y[i] for i in indices], [pred[i] for i in indices])
            resultados[e, nombre] = m
            print(f"{e:<14}{nombre:<13}{len(indices):>10}{m['cobertura']:>11.1%}{m['acierto']:>9.1%}"
                  f"{m['acierto_total']:>15.1%}{m['f1_macro']:>10.3f}")
        print()
    print("(modelo = sin umbral; combinación = reglas unánimes + modelo con umbral)\n")

    print("Criterio de éxito:")
    comb, reg = resultados["todos", "combinación"], resultados["todos", "reglas"]
    chequeos = [("supera a las reglas en acierto", comb["acierto"] > reg["acierto"],
                 f"{comb['acierto']:.1%} contra {reg['acierto']:.1%}"),
                ("supera a las reglas en cobertura", comb["cobertura"] > reg["cobertura"],
                 f"{comb['cobertura']:.1%} contra {reg['cobertura']:.1%}")]
    for e, (piso_ac, piso_cob) in PISOS.items():
        m = resultados[e, "combinación"]
        chequeos.append((f"{e}: acierto de {piso_ac:.0%} o más", m["acierto"] >= piso_ac, f"{m['acierto']:.1%}"))
        chequeos.append((f"{e}: cobertura de {piso_cob:.0%} o más", m["cobertura"] >= piso_cob,
                         f"{m['cobertura']:.1%}"))
    for nombre, ok, valor in chequeos:
        print(f"  {'CUMPLE   ' if ok else 'NO CUMPLE'}  {nombre:<36}{valor}")

    print("\nCurva según el umbral (solo para describir; el umbral ya está fijado en 0,4):")
    for umbral in [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
        curva = [r if u else (m if p >= umbral else SIN_CLASIFICAR)
                 for (r, u), m, p in zip(regla, pred_modelo, prob_max)]
        m = medir(list(prueba_y), curva)
        print(f"  {umbral:.1f}   cobertura {m['cobertura']:>6.1%}   acierto {m['acierto']:>6.1%}")

    print("\nErrores de la combinación (humano, predicción, de dónde vino, nombre):")
    for i, c in enumerate(claves):
        if pred_comb[i] not in (prueba_y[i], SIN_CLASIFICAR):
            origen = "reglas" if regla[i][1] else "modelo"
            print(f"  {prueba_y[i]:<30}{pred_comb[i]:<30}{origen:<8}{productos[c]['nombre'][:45]}")
    print("\nRubros donde más se equivoca (humano contra predicción):")
    for (h, p), n in Counter((h, p) for h, p in zip(prueba_y, pred_comb)
                             if p not in (h, SIN_CLASIFICAR)).most_common(8):
        print(f"  {n:>3}  {h:<30}{p}")
    sin = [i for i, p in enumerate(pred_comb) if p == SIN_CLASIFICAR]
    print(f"\nSin clasificar: {len(sin)} (humano, lo que habría dicho el modelo, probabilidad, nombre)")
    for i in sin:
        print(f"  {prueba_y[i]:<30}{pred_modelo[i]:<30}{prob_max[i]:<8.2f}{productos[claves[i]]['nombre'][:45]}")

    with open(SALIDA, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["clave", "estrato", "humano", "reglas", "unanime", "modelo", "probabilidad",
                           "combinacion", "nombre"])
        for i, c in enumerate(claves):
            escritor.writerow([c, estrato[i], prueba_y[i], pred_reglas[i], regla[i][1], pred_modelo[i],
                               round(float(prob_max[i]), 3), pred_comb[i], productos[c]["nombre"]])
    print(f"\nEscrito {SALIDA}   ({time.time() - inicio:,.0f} s en total)")


if __name__ == "__main__":
    main()
