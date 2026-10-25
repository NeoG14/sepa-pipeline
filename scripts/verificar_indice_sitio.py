"""Compara indice/<provincia>.json del sitio con lo que guardó dbt (fct_indice_cadena). Solo lee.

Uso: python -m scripts.verificar_indice_sitio [--provincia AR-B] [--salida sitio/datos]
"""
import argparse
import json
from pathlib import Path

import duckdb

from ingesta import config

RAIZ = Path(__file__).resolve().parents[1]


def main():
    a = argparse.ArgumentParser(description="Verifica el índice exportado")
    a.add_argument("--provincia", default="AR-B")
    a.add_argument("--salida", type=Path, default=RAIZ / "sitio" / "datos")
    a = a.parse_args()
    archivo = a.salida / "indice" / f"{a.provincia}.json"
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    nombre = dict(con.execute("SELECT id_comercio, nombre FROM cadenas").fetchall())
    esperado = dict(con.execute(
        "SELECT id_comercio, 100 * exp(sum(ln(factor))) FROM fct_indice_cadena WHERE provincia = ? GROUP BY 1", [a.provincia]).fetchall())
    print(f"{archivo} ({archivo.stat().st_size:,} bytes)\n")
    print(f"{'cadena':<20}{'puntos':>8}{'primero':>10}{'último':>9}{'esperado (dbt)':>16}{'productos':>11}{'':>4}")
    todo_ok = True
    for cadena, puntos in sorted(datos["s"].items(), key=lambda x: int(x[0])):
        ok = abs(puntos[-1][1] - esperado[cadena]) < 0.01
        todo_ok &= ok
        print(f"{nombre.get(cadena, cadena):<20}{len(puntos):>8}{puntos[0][1]:>10.2f}{puntos[-1][1]:>9.2f}{esperado[cadena]:>16.2f}{datos['n'][cadena]:>11,}{'  ok' if ok else '  DIFIERE'}")
    print("\nTodo coincide" if todo_ok and len(datos["s"]) == len(esperado) else "\nHAY DIFERENCIAS")
    con.close()


if __name__ == "__main__":
    main()
