"""Rubro de cada producto según las reglas y el modelo (paso 8 del plan de categorización).

Es incremental: clasifica solo los productos que todavía no tienen la versión actual del modelo,
es decir, los nuevos y, cuando se cambia VERSION, todos los demás. Lo ya clasificado no se toca,
así que la corrida diaria clasifica solo lo que entró ese día.

Para cada producto:
  1. Si todas las cadenas votan el mismo rubro con las reglas (scripts/rubros.py) y ese rubro está
     en la taxonomía: fuente "regla".
  2. Si no, decide el modelo: si su probabilidad llega al umbral, fuente "modelo"; si no, queda
     "sin clasificar" (sin rubro) y se guarda lo que el modelo habría dicho, para revisarlo.

Cambio posterior a la prueba: cuando las reglas reconocen un congelado pero no de qué tipo,
devuelven "congelados", que no es un rubro de la taxonomía. En la evaluación de prueba esos casos
pasaban como unánimes y daban error; ahora los decide el modelo. No se volvió a medir en prueba.

Las correcciones manuales (rubros_manuales) no se aplican acá sino en clasificacion_productos, así
corrigen también lo ya clasificado sin reentrenar.

Para sacar una versión nueva del modelo: entrenarlo, guardarlo como rubros-vN.joblib en la carpeta
clasificacion de la carpeta de datos y cambiar VERSION (y UMBRAL si cambió).
"""
import os
import sys
from datetime import date

import pandas as pd

VERSION = "v1"
UMBRAL = 0.4
ARCHIVO_MODELO = f"rubros-{VERSION}.joblib"


def model(dbt, session):
    dbt.config(materialized="incremental", unique_key="clave")

    try:
        from scripts.entrenar_modelo import reglas, texto
    except ImportError:
        # dbt desde la consola no pone la carpeta del proyecto en el path (python -m ingesta.main sí)
        sys.path.insert(0, os.environ.get("SEPA_REPO_DIR", os.getcwd()))
        from scripts.entrenar_modelo import reglas, texto
    import joblib
    from ingesta import config

    # Cada dbt.ref en su propia línea: dbt lee el archivo sin ejecutarlo para saber de qué depende
    # el modelo, y no encuentra un ref anidado dentro de otra expresión
    productos = dbt.ref("int_descripciones_producto").df()
    rubros = dbt.ref("rubros").df()
    taxonomia = set(rubros["rubro"])
    if dbt.is_incremental:
        hechos = session.sql(f"select clave from {dbt.this} where version = '{VERSION}'").df()
        productos = productos[~productos["clave"].isin(set(hechos["clave"]))]

    filas = []
    para_modelo = []   # índices de las filas que decide el modelo
    textos = []
    for clave, marca, descripciones in zip(productos["clave"], productos["marca"], productos["descripciones"]):
        descripciones = [] if descripciones is None else list(descripciones)
        marca = marca if isinstance(marca, str) else ""
        rubro, unanime = reglas(descripciones)
        if unanime and rubro in taxonomia:
            filas.append([clave, rubro, None, "regla", None])
        else:
            para_modelo.append(len(filas))
            textos.append(texto(descripciones, marca))
            filas.append([clave, None, None, "sin clasificar", None])

    if textos:
        modelo = joblib.load(config.DATOS_DIR / "clasificacion" / ARCHIVO_MODELO)
        prob = modelo.predict_proba(textos)
        mejor = prob.argmax(axis=1)
        for i, k in zip(para_modelo, range(len(textos))):
            p = float(prob[k, mejor[k]])
            filas[i][4] = modelo.classes_[mejor[k]]    # lo que dice el modelo, aunque no llegue al umbral
            filas[i][2] = p
            if p >= UMBRAL:
                filas[i][1], filas[i][3] = filas[i][4], "modelo"

    resultado = pd.DataFrame(filas, columns=["clave", "rubro", "probabilidad", "fuente", "rubro_modelo"])
    resultado["version"] = VERSION
    resultado["fecha"] = date.today()
    print(f"clasificacion_automatica {VERSION}: {len(resultado):,} productos nuevos "
          f"({resultado['fuente'].value_counts().to_dict()})")

    # Tipos explícitos: una columna toda nula (corridas donde todo sale por regla) o una tabla
    # vacía no pueden darle a la tabla un tipo distinto del que ya tiene
    session.register("resultado_df", resultado)
    return session.sql("""
        select clave::varchar as clave, rubro::varchar as rubro, probabilidad::double as probabilidad,
               fuente::varchar as fuente, rubro_modelo::varchar as rubro_modelo,
               version::varchar as version, fecha::date as fecha
        from resultado_df
    """)
