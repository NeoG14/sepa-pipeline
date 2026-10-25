"""Elige el umbral del modelo con las predicciones de desarrollo (paso 6). No vuelve a entrenar.

Lee <carpeta de datos>/clasificacion/predicciones_desarrollo.csv (de entrenar_modelo.py: cada
producto de desarrollo predicho por un modelo que no lo vio) y, para cada umbral, muestra la
cobertura y el acierto de la combinación por estrato, al lado de las reglas y de los pisos del
criterio de éxito. Con --umbral lista los errores (si vinieron de las reglas o del modelo) y los
productos que quedan sin clasificar.

El umbral se elige acá, en desarrollo. En prueba (paso 7) solo se mide: si se eligiera mirando
prueba, la nota final saldría inflada.

Uso: python -m scripts.elegir_umbral [--umbral 0.4]
"""
import argparse
import csv

from ingesta import config

ENTRADA = config.DATOS_DIR / "clasificacion" / "predicciones_desarrollo.csv"
UMBRALES = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
ESTRATOS = ["todos", "comparables", "una cadena", "pesables"]
# Pisos del criterio de éxito (acierto, cobertura); además hay que superar a las reglas
PISOS = {"comparables": (0.90, 0.90), "pesables": (0.85, 0.75)}
SIN_CLASIFICAR = "(sin clasificar)"


def combinacion(fila, umbral):
    if fila["unanime"] == "True":
        return fila["reglas"], "reglas"
    if float(fila["probabilidad"]) >= umbral:
        return fila["modelo"], "modelo"
    return SIN_CLASIFICAR, "sin clasificar"


def medir(filas, prediccion):
    cubiertos = [f for f in filas if prediccion(f) != SIN_CLASIFICAR]
    bien = sum(prediccion(f) == f["humano"] for f in cubiertos)
    return len(cubiertos) / len(filas), (bien / len(cubiertos) if cubiertos else 0)


def main():
    argumentos = argparse.ArgumentParser(description="Umbral del modelo en desarrollo")
    argumentos.add_argument("--umbral", type=float, default=0.4)
    a = argumentos.parse_args()

    with open(ENTRADA, encoding="utf-8", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    grupos = {e: [f for f in filas if e in ("todos", f["estrato"])] for e in ESTRATOS}
    print(f"{len(filas)} productos de desarrollo\n")
    print("cobertura / acierto de la combinación según el umbral")
    print(f"{'':<8}" + "".join(f"{e + ' (' + str(len(grupos[e])) + ')':>22}" for e in ESTRATOS))

    def linea(nombre, prediccion):
        celdas = []
        for e in ESTRATOS:
            cob, ac = medir(grupos[e], prediccion)
            celdas.append(f"{cob:>11.1%} /{ac:>7.1%}")
        print(f"{nombre:<8}" + "".join(f"{c:>22}" for c in celdas))

    linea("reglas", lambda f: f["reglas"])
    for umbral in UMBRALES:
        linea(f"{umbral:.1f}", lambda f, u=umbral: combinacion(f, u)[0])
    print(f"{'pisos':<8}{'':>22}" + "".join(
        f"{(f'{PISOS[e][1]:.0%} / {PISOS[e][0]:.0%}' if e in PISOS else '-'):>22}" for e in ESTRATOS[1:]))

    u = a.umbral
    print(f"\nCon umbral {u}:")
    errores = [(f, *combinacion(f, u)) for f in filas]
    print("Errores (humano, predicción, de dónde vino, nombre):")
    for f, pred, origen in errores:
        if pred not in (f["humano"], SIN_CLASIFICAR):
            print(f"  {f['humano']:<30}{pred:<30}{origen:<8}{f['nombre'][:45]}")
    print("Quedan sin clasificar (humano, lo que habría dicho el modelo, probabilidad, nombre):")
    for f, pred, origen in errores:
        if pred == SIN_CLASIFICAR:
            print(f"  {f['humano']:<30}{f['modelo']:<30}{float(f['probabilidad']):<8.2f}{f['nombre'][:45]}")


if __name__ == "__main__":
    main()
