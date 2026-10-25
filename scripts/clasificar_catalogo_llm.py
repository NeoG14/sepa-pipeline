"""Clasifica el catálogo en rubros con DeepSeek y guarda el resultado en seeds/rubros_llm.csv.

Por qué DeepSeek: en las 300 de prueba (scripts.etiquetar_rubros_llm --conjunto prueba) dio 91,6 % de acierto
con 99,7 % de cobertura, contra 86,4 % y 85,7 % de la combinación reglas + modelo. En desarrollo, con solo
el nombre del producto, dio lo mismo (91,7 %). El pedido es el mismo que se midió: no cambiarlo sin volver
a medir en desarrollo.

Lee int_descripciones_producto (la última descripción de cada cadena y la marca, lo mismo que se midió) y
manda los productos en lotes, primero los que venden más cadenas: son los que entran en las comparaciones.
Cada respuesta queda en el caché clasificacion/rubros_llm_<huella>.jsonl (el mismo de la medición), así que un
producto no se paga dos veces y, si se corta, sigue desde donde quedó.

Sin --enviar no llama a la API: dice cuántos faltan y cuánto costaría, y rearma el seed con lo que ya hay en
el caché. Con --enviar clasifica los que faltan.

La clave va en la variable de entorno DEEPSEEK_API_KEY. Nunca en el código ni en el chat.
  PowerShell (solo esta ventana):  $env:DEEPSEEK_API_KEY = "<tu clave>"

Uso: python -m scripts.clasificar_catalogo_llm                                  (cuánto falta y cuánto cuesta)
     python -m scripts.clasificar_catalogo_llm --enviar --minimo-cadenas 2      (los que venden 2 cadenas o más)
     python -m scripts.clasificar_catalogo_llm --enviar                         (todo lo que falta)
Después: dbt seed --select rubros_llm  y  dbt build --select clasificacion_productos+
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import duckdb

from ingesta import config
from scripts import entrenar_modelo as em
from scripts.etiquetar_pesables_llm import MODELO, USD_ENTRADA, USD_SALIDA
from scripts.etiquetar_rubros_llm import armar_instrucciones, leer_rubros, linea_de, llamar

USD_POR_PRODUCTO = 0.017 / 300     # medido: 300 productos costaron como máximo US$ 0,017


def main():
    argumentos = argparse.ArgumentParser(description="Rubros del catálogo con DeepSeek")
    argumentos.add_argument("--enviar", action="store_true", help="llama a la API (sin esto solo estima)")
    argumentos.add_argument("--minimo-cadenas", type=int, default=1, help="solo productos que venden al menos N cadenas")
    argumentos.add_argument("--limite", type=int, help="como mucho N productos en esta corrida")
    argumentos.add_argument("--lote", type=int, default=40)
    argumentos.add_argument("--hilos", type=int, default=6)
    a = argumentos.parse_args()

    rubros = leer_rubros()
    validos = {r for _, r, _ in rubros}
    grupo_de = {r: g for g, r, _ in rubros}
    instrucciones = armar_instrucciones(rubros)
    huella = hashlib.sha1((MODELO + instrucciones).encode()).hexdigest()[:8]
    cache_ruta = em.CLASIFICACION / f"rubros_llm_{huella}.jsonl"
    cache = {}
    if cache_ruta.exists():
        for linea in cache_ruta.open(encoding="utf-8"):
            x = json.loads(linea)
            cache[x["k"]] = x["rubro"]

    con = duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    filas = con.execute("""
        SELECT d.clave, p.nombre, d.marca, d.cadenas, d.descripciones, p.rubro, p.fuente_rubro
        FROM int_descripciones_producto d
        JOIN dim_productos p USING (clave)
        ORDER BY d.cadenas DESC, d.clave""").fetchall()
    con.close()
    producto = {clave: {"nombre": nombre or "", "marca": marca or "",
                        "descripciones": [{"descripcion": x} for x in (descripciones or []) if x]}
                for clave, nombre, marca, _, descripciones, _, _ in filas}
    candidatos = [f[0] for f in filas if f[3] >= a.minimo_cadenas]
    pendientes = [c for c in candidatos if c not in cache]
    if a.limite:
        pendientes = pendientes[:a.limite]
    print(f"{len(filas):,} productos en el catálogo; {len(candidatos):,} venden {a.minimo_cadenas} cadena(s) o más; "
          f"{len(candidatos) - len([c for c in candidatos if c not in cache]):,} ya clasificados en el caché")
    print(f"Para enviar en esta corrida: {len(pendientes):,} en {-(-len(pendientes) // a.lote):,} llamadas; "
          f"costo estimado como mucho US$ {len(pendientes) * USD_POR_PRODUCTO:.2f}")

    if a.enviar and pendientes:
        clave_api = os.environ.get("DEEPSEEK_API_KEY")
        if not clave_api:
            sys.exit("Falta la variable de entorno DEEPSEEK_API_KEY (ver el principio de este archivo).")
        lotes = [pendientes[i:i + a.lote] for i in range(0, len(pendientes), a.lote)]
        entrada = salida = hechos = 0
        cache_ruta.parent.mkdir(parents=True, exist_ok=True)
        with cache_ruta.open("a", encoding="utf-8") as archivo, ThreadPoolExecutor(a.hilos) as pool:
            for n, (lote, (respuestas, t_in, t_out)) in enumerate(zip(lotes, pool.map(
                    lambda l: llamar(instrucciones, [linea_de(producto[c]) for c in l], clave_api), lotes)), 1):
                entrada += t_in
                salida += t_out
                for c, r in zip(lote, respuestas):
                    if r is not None:
                        cache[c] = r
                        hechos += 1
                        archivo.write(json.dumps({"k": c, "rubro": r}, ensure_ascii=False) + "\n")
                archivo.flush()
                if n % 50 == 0 or n == len(lotes):
                    print(f"  {n:,} de {len(lotes):,} llamadas; US$ {entrada / 1e6 * USD_ENTRADA + salida / 1e6 * USD_SALIDA:.2f} hasta ahora")
        print(f"Clasificados {hechos:,} de {len(pendientes):,}. Tokens: {entrada:,} de entrada, {salida:,} de salida; "
              f"costo como mucho US$ {entrada / 1e6 * USD_ENTRADA + salida / 1e6 * USD_SALIDA:.2f}")
        if hechos < len(pendientes):
            print(f"  {len(pendientes) - hechos:,} sin respuesta (la API falló): volvé a correr, retoma desde el caché.")
    elif pendientes:
        print("No envié nada: agregá --enviar para clasificarlos.")

    # El seed: todos los productos del catálogo que DeepSeek ya clasificó en un rubro de la lista
    en_catalogo = [f for f in filas if f[0] in cache]
    buenos = sorted((f[0], cache[f[0]]) for f in en_catalogo if cache[f[0]] in validos)
    sin = sum(1 for f in en_catalogo if cache[f[0]] == em.SIN_CLASIFICAR)
    otros = Counter(cache[f[0]] for f in en_catalogo if cache[f[0]] not in validos and cache[f[0]] != em.SIN_CLASIFICAR)
    destino = em.RAIZ_REPO / "seeds" / "rubros_llm.csv"
    if destino.exists() and len(buenos) < sum(1 for _ in destino.open(encoding="utf-8")) - 1:
        sys.exit(f"\nEl caché tiene menos rubros ({len(buenos):,}) que el seed que ya existe: no lo piso. "
                 f"¿Estás usando la misma carpeta de datos? (caché: {cache_ruta})")
    with destino.open("w", encoding="utf-8", newline="") as archivo:
        w = csv.writer(archivo)
        w.writerow(["clave", "rubro"])
        w.writerows(buenos)
    print(f"\nGuardé {len(buenos):,} rubros en {destino}  (sin clasificar: {sin:,}; respuestas fuera de la lista: "
          f"{sum(otros.values()):,} {dict(otros.most_common(5)) if otros else ''})")

    # Contra lo que hay hoy: dónde coincide con las reglas y el modelo, y qué pasa con los sin rubro
    print(f"\n{'hoy':<18}{'productos':>10}{'mismo rubro':>13}{'mismo grupo':>13}")
    por_fuente = defaultdict(list)
    for clave, _, _, _, _, rubro, fuente in en_catalogo:
        if cache[clave] in validos:
            por_fuente[fuente or "(sin fuente)"].append((rubro, cache[clave]))
    for fuente, pares in sorted(por_fuente.items(), key=lambda x: -len(x[1])):
        if fuente == "sin clasificar":
            continue
        mismo = sum(1 for r, l in pares if r == l)
        mismo_grupo = sum(1 for r, l in pares if grupo_de.get(r) == grupo_de.get(l))
        print(f"{fuente:<18}{len(pares):>10,}{mismo / len(pares):>13.0%}{mismo_grupo / len(pares):>13.0%}")
    nuevos = Counter(grupo_de[l] for r, l in por_fuente.get("sin clasificar", []))
    print(f"\nHoy sin rubro y ahora clasificados: {sum(nuevos.values()):,}. Por grupo: "
          + ", ".join(f"{g} {n:,}" for g, n in nuevos.most_common(8)))


if __name__ == "__main__":
    main()
