"""Escribe seeds/ingrediente_producto.csv: qué productos del catálogo son cada ingrediente envasado de las
recetas (seeds/ingredientes.csv) y de qué tamaño son, en kg o litros. Con las mismas reglas que
medir_ingredientes.py (que muestra el resultado por provincia antes de guardarlo).

Usa el nombre y el rubro de dim_productos y el tamaño del último día de productos.parquet. No usa DeepSeek.
Un producto nuevo entra solo en la próxima corrida, sin que nadie lo clasifique.

Uso: python -m scripts.clasificar_ingredientes              (cuenta cuántos entran, no escribe)
     python -m scripts.clasificar_ingredientes --guardar    (escribe la seed)
Después: dbt seed --select recetas ingrediente_producto
"""
import argparse
import csv
from collections import Counter
from pathlib import Path

import duckdb

from ingesta import config
from publicar.exportar_json import CLAVE
from scripts.medir_ingredientes import evaluar, leer_ingredientes

RAIZ = Path(__file__).resolve().parents[1]


def main():
    a = argparse.ArgumentParser(description="Seed de productos por ingrediente")
    a.add_argument("--guardar", action="store_true", help="escribe seeds/ingrediente_producto.csv")
    a = a.parse_args()

    ingredientes = leer_ingredientes()
    carpeta = sorted((config.DATOS_DIR / "parquet").glob("fecha=*"))[-1]
    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    filas = con.execute(f"""
        WITH tam AS (
            SELECT id_comercio, id_producto, any_value(cantidad_presentacion) AS cantidad,
                   lower(trim(any_value(unidad_presentacion))) AS unidad
            FROM read_parquet('{(carpeta / "productos.parquet").as_posix()}')
            GROUP BY ALL)
        SELECT id_comercio, id_producto, d.nombre, d.rubro, cantidad, unidad
        FROM tam
        JOIN dim_productos d ON d.clave = ({CLAVE})
    """).fetchall()
    con.close()
    print(f"{len(filas):,} productos del {carpeta.name}")

    salida = []
    por_ingrediente = {}
    for ing in ingredientes:
        cuenta = Counter()
        for id_comercio, id_producto, nombre, rubro, cantidad, unidad in filas:
            estado, tamano, _ = evaluar(ing, nombre, rubro, cantidad, unidad)
            cuenta[estado] += 1
            if estado == "entra":
                salida.append((id_comercio, id_producto, ing["ingrediente"], round(tamano, 6)))
        por_ingrediente[ing["ingrediente"]] = cuenta
    print(f"\n{'ingrediente':<28}{'entran':>8}{'sin tamaño':>12}{'fuera de rango':>16}")
    for nombre, c in por_ingrediente.items():
        print(f"{nombre:<28}{c['entra']:>8,}{c['sin_tamano']:>12,}{c['fuera_de_rango']:>16,}")
    if a.guardar:
        destino = RAIZ / "seeds" / "ingrediente_producto.csv"
        with destino.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id_comercio", "id_producto", "ingrediente", "tamano"])
            w.writerows(sorted(salida))
        print(f"\nGuardé {len(salida):,} filas en {destino}")
    else:
        print("\nNo escribí nada: agregá --guardar.")


if __name__ == "__main__":
    main()
