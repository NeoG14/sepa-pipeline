"""Etiqueta los pesables con DeepSeek: a qué producto cotidiano corresponde cada uno ("Banana", "Asado"...).

Lee pesables_para_clasificar.csv (scripts.medir_pesables --exportar), manda los nombres en lotes y guarda
la etiqueta de cada uno en pesables_etiquetas_llm.csv. Guarda cada respuesta en un caché
(pesables_etiquetas_llm_<huella>.jsonl): un producto ya etiquetado no se vuelve a pagar, y si se corta, sigue.

Después compara con las reglas de scripts/clasificar_pesables.py: dónde coinciden y dónde no. Los
desacuerdos son lo que hay que mirar a ojo; no hay etiquetas hechas a mano para los pesables.

La clave va en la variable de entorno DEEPSEEK_API_KEY. Nunca en el código ni en el chat.
  PowerShell (solo esta ventana):  $env:DEEPSEEK_API_KEY = "<tu clave>"

Uso: python -m scripts.etiquetar_pesables_llm --muestra 300      (prueba barata, al azar)
     python -m scripts.etiquetar_pesables_llm                    (todos)
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from ingesta import config
from pathlib import Path

from scripts.clasificar_pesables import PRODUCTOS, producto_de, vetado

URL = "https://api.deepseek.com/chat/completions"
MODELO = "deepseek-flash"
# Precio de DeepSeek por millón de tokens en horario pico, el más caro (api-docs.deepseek.com, 24/10/2026)
USD_ENTRADA, USD_SALIDA = 0.30, 1.20

PRODUCTOS_VALIDOS = [nombre for nombre, *_ in PRODUCTOS]

INSTRUCCIONES = f"""Sos un clasificador de productos de supermercados argentinos. Recibís una lista de pesables
(productos que se venden por peso) con el nombre tal cual lo informa la cadena. Para cada uno elegí UNO de
estos productos cotidianos, escrito exactamente igual:

{chr(10).join('- ' + n for n in PRODUCTOS_VALIDOS)}
- Otro

Respondé "Otro" cuando:
- no es ninguno de los de la lista;
- no es el producto fresco y al natural: congelado, rebozado, cocido, ahumado, en conserva, deshidratado,
  preparado (milanesas, empanadas, tartas, sándwiches, ensaladas, pizzas) u orgánico;
- es de una línea premium (Etiqueta Negra, Signia, Huella Natural, Guanaco);
- es un envase chico (menos de 500 g, cubeta, atado, paquete) o dice por unidad ("X UNI");
- el producto es de carne vacuna o de pollo y el corte es de cerdo, cordero o pavo ("nalga de cerdo", "paleta cord");
- es uno de estos cortes o variedades, que tienen nombre propio y otro precio: "colita de cuadril" (no es
  cuadril), "ojo de bife" (no es bife ancho), "asado de bife", "asado banderita", "chorizo colorado", "morcilla
  vasca", "queso cremón" (no es cremoso), "pimiento Palermo" (no es morrón), "salamín" (no es salame);
- es un queso light o reducido en grasa;
- es una carne vacuna feteada ("peceto feteado", "nalga fet") o una verdura ya cortada ("trozado", "rallada").
Un nombre abreviado o con la marca (REGGIANITO LA PAULINA, SARDO X KG, EBRO SALAM CRIO, FILET DE PECHUGA) sí
cuenta como el producto. Aclaraciones: "Manzana roja" incluye toda manzana que no sea verde. "Asado" es el
asado de tira. "Carne picada común" no incluye la especial, magra, desgrasada ni la de fiambres. "Pollo
entero" incluye el pollo fresco entero (también parrillero), no el rostizado.

Respondé SOLO un JSON con esta forma: {{"items": [{{"i": 0, "producto": "Banana"}}, ...]}}, con un elemento por
cada producto recibido, usando el mismo número i."""


def llamar(nombres, clave):
    """Una llamada a la API con un lote de nombres. Devuelve (etiquetas, tokens_entrada, tokens_salida)."""
    cuerpo = {
        "model": MODELO,
        "messages": [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content": "\n".join(f"{i}: {n}" for i, n in enumerate(nombres))},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},   # sin "thinking": gasta muchos más tokens de salida y no hace falta
        "temperature": 0,
    }
    pedido = urllib.request.Request(URL, data=json.dumps(cuerpo).encode(), method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {clave}"})
    for intento in range(5):
        try:
            with urllib.request.urlopen(pedido, timeout=120) as r:
                datos = json.load(r)
            texto = datos["choices"][0]["message"]["content"]
            elementos = {int(x["i"]): str(x["producto"]) for x in json.loads(texto)["items"]}
            uso = datos.get("usage", {})
            return ([elementos.get(i) for i in range(len(nombres))],
                    uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0))
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 402, 403):
                sys.exit(f"La API rechazó el pedido (HTTP {e.code}): revisá la clave y el saldo.")
            time.sleep(2 ** intento)
    return [None] * len(nombres), 0, 0


def main():
    argumentos = argparse.ArgumentParser(description="Etiqueta los pesables con DeepSeek")
    argumentos.add_argument("--muestra", type=int, help="solo N pesables al azar (prueba barata)")
    argumentos.add_argument("--semilla", type=int, default=1, help="qué sorteo de --muestra (1 = el de desarrollo, 2 = el de prueba)")
    argumentos.add_argument("--lote", type=int, default=40, help="productos por llamada")
    argumentos.add_argument("--hilos", type=int, default=6)
    a = argumentos.parse_args()

    clave = os.environ.get("DEEPSEEK_API_KEY")
    if not clave:
        sys.exit("Falta la variable de entorno DEEPSEEK_API_KEY (ver el principio de este archivo).")

    entrada = config.DATOS_DIR / "pesables_para_clasificar.csv"
    # El caché depende del texto del pedido y del modelo: si cambian, las etiquetas viejas no valen
    huella = hashlib.sha1((MODELO + INSTRUCCIONES).encode()).hexdigest()[:8]
    cache_ruta = config.DATOS_DIR / f"pesables_etiquetas_llm_{huella}.jsonl"
    filas = list(csv.DictReader(entrada.open(encoding="utf-8")))
    if a.muestra:
        filas = random.Random(a.semilla).sample(filas, min(a.muestra, len(filas)))   # la misma muestra en cada corrida
    clave_de = lambda f: f"{f['id_comercio']}|{f['id_producto']}"

    cache = {}
    if cache_ruta.exists():
        for linea in cache_ruta.open(encoding="utf-8"):
            x = json.loads(linea)
            cache[x["k"]] = x["producto"]
    pendientes = [f for f in filas if clave_de(f) not in cache]
    print(f"{len(filas):,} pesables; {len(filas) - len(pendientes):,} ya etiquetados en el caché; "
          f"{len(pendientes):,} para enviar en {-(-len(pendientes) // a.lote)} llamadas")

    lotes = [pendientes[i:i + a.lote] for i in range(0, len(pendientes), a.lote)]
    entrada_tok = salida_tok = fallidos = 0
    with ThreadPoolExecutor(a.hilos) as pool, cache_ruta.open("a", encoding="utf-8") as salida:
        for lote, (etiquetas, t_in, t_out) in zip(lotes, pool.map(lambda l: llamar([f["nombre"] for f in l], clave), lotes)):
            entrada_tok += t_in
            salida_tok += t_out
            for f, etiqueta in zip(lote, etiquetas):
                if etiqueta is None:
                    fallidos += 1
                    continue
                if etiqueta not in PRODUCTOS_VALIDOS:
                    etiqueta = "Otro"   # inventó un nombre que no está en la lista
                cache[clave_de(f)] = etiqueta
                salida.write(json.dumps({"k": clave_de(f), "producto": etiqueta}, ensure_ascii=False) + "\n")
    usd = entrada_tok / 1e6 * USD_ENTRADA + salida_tok / 1e6 * USD_SALIDA
    print(f"Tokens: {entrada_tok:,} de entrada, {salida_tok:,} de salida; costo máximo estimado US$ {usd:.2f}"
          + (f"; {fallidos} sin respuesta (volvé a correr para reintentar)" if fallidos else ""))

    destino = config.DATOS_DIR / "pesables_etiquetas_llm.csv"
    hechos = [f for f in filas if clave_de(f) in cache]
    # DeepSeek propone; si el nombre cae en una exclusión de las reglas, la etiqueta se anula (queda "Otro").
    # El caché guarda la etiqueta cruda, así cambiar los vetos no cuesta nada.
    final = {}
    vetos = []
    for f in hechos:
        crudo = cache[clave_de(f)]
        final[clave_de(f)] = "Otro" if crudo != "Otro" and vetado(f["nombre"], crudo) else crudo
        if final[clave_de(f)] != crudo:
            vetos.append(f"{f['nombre'][:44]}  ({crudo})")
    with destino.open("w", encoding="utf-8", newline="") as s:
        w = csv.writer(s)
        w.writerow(["id_comercio", "id_producto", "nombre", "producto_llm", "producto_llm_crudo"])
        w.writerows((f["id_comercio"], f["id_producto"], f["nombre"], final[clave_de(f)], cache[clave_de(f)]) for f in hechos)
    print(f"Guardé {len(hechos):,} etiquetas en {destino}; los vetos anularon {len(vetos)}\n")

    # Medición contra las respuestas correctas (scripts/datos/pesables_gold_s<semilla>.csv: los 300 de --muestra 300,
    # revisados a mano por Claude con el mismo criterio de las reglas; 2 dudosos no cuentan)
    gold_ruta = Path(__file__).resolve().parent / "datos" / f"pesables_gold_s{a.semilla}.csv"
    gold = ({f"{g['id_comercio']}|{g['id_producto']}": g["correcto"] for g in csv.DictReader(gold_ruta.open(encoding="utf-8"))}
            if gold_ruta.exists() else {})
    evaluados = [f for f in hechos if gold.get(clave_de(f)) not in (None, "?")]
    if evaluados:
        print(f"Contra las respuestas correctas ({len(evaluados)} productos, {sum(1 for f in evaluados if gold[clave_de(f)])} reconocibles):")
        for titulo, etiqueta in [("DeepSeek solo", lambda f: cache[clave_de(f)]), ("DeepSeek con vetos", lambda f: final[clave_de(f)]),
                                 ("reglas", lambda f: (producto_de(f["nombre"]) or ["Otro"])[0]),
                                 ("reglas + DeepSeek", lambda f: (producto_de(f["nombre"]) or [final[clave_de(f)]])[0])]:
            ok = de_mas = perdidos = 0
            errores = []
            for f in evaluados:
                g = gold[clave_de(f)] or None
                l = etiqueta(f)
                l = None if l == "Otro" else l
                ok += bool(l and l == g)
                if l and l != g:
                    de_mas += 1
                    errores.append(f"  de más:   {f['nombre'][:44]}  {l}")
                if g and l != g:
                    perdidos += 1
                    errores.append(f"  perdido:  {f['nombre'][:44]}  era {g}")
            print(f"{titulo:<20} aciertos {ok}, de más {de_mas}, perdidos {perdidos} -> precisión {ok / max(ok + de_mas, 1):.0%}, cobertura {ok / max(ok + perdidos, 1):.0%}")
            if titulo == "reglas + DeepSeek":
                print("\n".join(errores))
        print()

    # Comparación con las reglas
    cuenta, ejemplos = Counter(), {}
    for f in hechos:
        llm = final[clave_de(f)]
        llm = None if llm == "Otro" else llm
        r = producto_de(f["nombre"])
        reglas = r[0] if r else None
        tipo = ("ninguno lo reconoce" if not llm and not reglas else
                "coinciden" if llm == reglas else
                "solo las reglas" if not llm else "solo DeepSeek" if not reglas else "distinto producto")
        cuenta[tipo] += 1
        ejemplos.setdefault(tipo, []).append(f"{f['nombre'][:44]}  reglas={reglas}  deepseek={llm}")
    for tipo in ["coinciden", "distinto producto", "solo las reglas", "solo DeepSeek", "ninguno lo reconoce"]:
        print(f"{tipo:<22}{cuenta[tipo]:>6,}")
    for tipo in ["distinto producto", "solo las reglas", "solo DeepSeek"]:
        print(f"\n{tipo} (hasta 25 ejemplos):")
        for e in ejemplos.get(tipo, [])[:25]:
            print("  " + e)


if __name__ == "__main__":
    main()
