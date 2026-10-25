"""Clasifica productos en rubros con DeepSeek y mide si mejora lo que ya hay (reglas + modelo).

Usa seeds/rubros.csv (rubro, descripción y qué NO incluye) como lista de opciones. Mide sobre las muestras
etiquetadas a mano del paso 5, con las mismas reglas del juego que el resto de la clasificación:

  --conjunto desarrollo   (por defecto) las 300 de desarrollo. Acá se puede afinar el pedido (INSTRUCCIONES)
                          todas las veces que haga falta, porque para eso están. Compara con las reglas;
                          no con el modelo, que ya se entrenó con estas 300.
  --conjunto prueba       las 300 de prueba, UNA sola vez y con el pedido ya fijado. Compara contra las
                          predicciones que quedaron en clasificacion/predicciones_prueba.csv (reglas, modelo y
                          combinación actual). Se niega a correr si ya corrió. Esas 300 ya se miraron con el
                          método anterior; el pedido a DeepSeek no se afinó con ellas.

Cada respuesta queda en un caché (rubros_llm_<huella>.jsonl, dentro de clasificacion/): un producto ya
etiquetado no se vuelve a pagar, y si se corta, sigue. La huella cambia con el pedido, así que al afinar
el pedido se vuelve a etiquetar (unos centavos).

La clave va en la variable de entorno DEEPSEEK_API_KEY. Nunca en el código ni en el chat.
  PowerShell (solo esta ventana):  $env:DEEPSEEK_API_KEY = "<tu clave>"

Uso: python -m scripts.etiquetar_rubros_llm
     python -m scripts.etiquetar_rubros_llm --conjunto prueba
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from scripts import entrenar_modelo as em
from scripts.etiquetar_pesables_llm import MODELO, URL, USD_ENTRADA, USD_SALIDA


def leer_rubros():
    filas = em.leer_csv(em.RAIZ_REPO / "seeds" / "rubros.csv")
    return [(f["grupo"], f["rubro"], f["descripcion"]) for f in filas if f["rubro"]]


def armar_instrucciones(rubros):
    lista = "\n".join(f"- {rubro}: {descripcion}" for _, rubro, descripcion in rubros)
    return f"""Sos un clasificador de productos de supermercados argentinos. Recibís productos con el nombre que le
pone cada cadena (si lo vende más de una, varias descripciones separadas por " | ") y la marca. Para cada uno
elegí UN rubro de esta lista, escrito exactamente igual. Después de los dos puntos está de qué trata el rubro y,
donde dice "No:", qué NO incluye (eso va en otro rubro).

{lista}

Si el nombre no alcanza para saber a cuál va, o no encaja con claridad en ninguno, respondé "(sin clasificar)":
es mejor eso que adivinar. Los nombres vienen abreviados y con errores (LECHE DESC. = leche descremada).

Respondé SOLO un JSON con esta forma: {{"items": [{{"i": 0, "rubro": "aceite"}}, ...]}}, con un elemento por
cada producto recibido, usando el mismo número i."""


def llamar(instrucciones, lineas, clave):
    """Una llamada con un lote. Devuelve (rubros, tokens_entrada, tokens_salida)."""
    cuerpo = {
        "model": MODELO,
        "messages": [{"role": "system", "content": instrucciones},
                     {"role": "user", "content": "\n".join(f"{i}: {x}" for i, x in enumerate(lineas))}],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "temperature": 0,
    }
    pedido = urllib.request.Request(URL, data=json.dumps(cuerpo).encode(), method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {clave}"})
    for intento in range(5):
        try:
            with urllib.request.urlopen(pedido, timeout=120) as r:
                datos = json.load(r)
            elementos = {int(x["i"]): str(x["rubro"]) for x in json.loads(datos["choices"][0]["message"]["content"])["items"]}
            uso = datos.get("usage", {})
            return ([elementos.get(i) for i in range(len(lineas))],
                    uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0))
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 402, 403):
                sys.exit(f"La API rechazó el pedido (HTTP {e.code}): revisá la clave y el saldo.")
            time.sleep(2 ** intento)
    return [None] * len(lineas), 0, 0


def linea_de(producto, formato="descripciones"):
    if formato == "nombre":      # lo que tiene el catálogo: un solo nombre (el más largo) y la marca
        return producto["nombre"] + (f" || marca: {producto['marca']}" if producto["marca"] else "")
    descripciones = list(dict.fromkeys(d["descripcion"] for d in producto["descripciones"] if d["descripcion"]))[:3]
    marca = f" || marca: {producto['marca']}" if producto["marca"] else ""
    return " | ".join(descripciones or [producto["nombre"]]) + marca


def main():
    argumentos = argparse.ArgumentParser(description="Rubros con DeepSeek, medidos contra las etiquetas a mano")
    argumentos.add_argument("--conjunto", choices=["desarrollo", "prueba"], default="desarrollo")
    argumentos.add_argument("--formato", choices=["descripciones", "nombre"], default="descripciones",
                            help="qué ve DeepSeek de cada producto: hasta 3 descripciones (como se midió en prueba) o solo "
                                 "el nombre más largo (como lo tiene el catálogo)")
    argumentos.add_argument("--lote", type=int, default=40)
    argumentos.add_argument("--hilos", type=int, default=6)
    a = argumentos.parse_args()

    clave_api = os.environ.get("DEEPSEEK_API_KEY")
    if not clave_api:
        sys.exit("Falta la variable de entorno DEEPSEEK_API_KEY (ver el principio de este archivo).")

    carpeta, clasificacion = em.CARPETA, em.CLASIFICACION
    sufijo = "" if a.formato == "descripciones" else f"_{a.formato}"
    salida = clasificacion / f"rubros_llm_{a.conjunto}{sufijo}.csv"
    if a.conjunto == "prueba" and a.formato != "descripciones":
        sys.exit("En prueba solo se corre el formato con el que se midió (descripciones): probar otro con prueba ya sería afinar con ella.")
    if a.conjunto == "prueba":
        if salida.exists():
            sys.exit(f"{salida} ya existe: la evaluación en prueba se hace una sola vez.")
        if not (clasificacion / "predicciones_prueba.csv").exists():
            sys.exit("Falta clasificacion/predicciones_prueba.csv: hay que haber corrido scripts.evaluar_prueba.")

    rubros = leer_rubros()
    validos = {r for _, r, _ in rubros}
    instrucciones = armar_instrucciones(rubros)

    muestra = {f["clave"]: f for f in em.leer_csv(carpeta / "muestra.csv")}
    etiquetas = {f["clave"]: f["rubro"] for f in em.leer_csv(carpeta / "etiquetas.csv") if f["ronda"] != "2"}
    productos = {p["clave"]: p for p in json.loads((carpeta / "productos.json").read_text(encoding="utf-8"))["productos"]}
    claves = sorted(c for c, f in muestra.items() if f["conjunto"] == a.conjunto)
    fuera = sorted({etiquetas[c] for c in claves if etiquetas[c] not in validos})
    print(f"{len(rubros)} rubros; {len(claves)} productos del conjunto {a.conjunto}"
          + (f"; etiquetas a mano que no están en rubros.csv: {fuera}" if fuera else ""))

    huella = hashlib.sha1((MODELO + instrucciones).encode()).hexdigest()[:8]
    cache_ruta = clasificacion / f"rubros_llm_{huella}{sufijo}.jsonl"
    cache = {}
    if cache_ruta.exists():
        for linea in cache_ruta.open(encoding="utf-8"):
            x = json.loads(linea)
            cache[x["k"]] = x["rubro"]
    pendientes = [c for c in claves if c not in cache]
    lotes = [pendientes[i:i + a.lote] for i in range(0, len(pendientes), a.lote)]
    print(f"{len(claves) - len(pendientes)} ya en el caché; {len(pendientes)} para enviar en {len(lotes)} llamadas")

    entrada = salida_tok = 0
    if lotes:
        cache_ruta.parent.mkdir(parents=True, exist_ok=True)
        with cache_ruta.open("a", encoding="utf-8") as archivo, ThreadPoolExecutor(a.hilos) as pool:
            for lote, (respuestas, t_in, t_out) in zip(lotes, pool.map(
                    lambda l: llamar(instrucciones, [linea_de(productos[c], a.formato) for c in l], clave_api), lotes)):
                entrada += t_in
                salida_tok += t_out
                for c, r in zip(lote, respuestas):
                    if r is not None:
                        cache[c] = r
                        archivo.write(json.dumps({"k": c, "rubro": r}, ensure_ascii=False) + "\n")
        print(f"Tokens: {entrada:,} de entrada, {salida_tok:,} de salida; costo máximo US$ "
              f"{entrada / 1e6 * USD_ENTRADA + salida_tok / 1e6 * USD_SALIDA:.3f}")
    faltan = [c for c in claves if c not in cache]
    if faltan:
        sys.exit(f"{len(faltan)} productos sin respuesta (la API falló): volvé a correr, retoma desde el caché.")

    invalidos = Counter(cache[c] for c in claves if cache[c] not in validos and cache[c] != em.SIN_CLASIFICAR)
    llm = {c: cache[c] if cache[c] in validos else em.SIN_CLASIFICAR for c in claves}
    if invalidos:
        print(f"Respuestas que no son un rubro de la lista (se toman como sin clasificar): {dict(invalidos)}")

    humano = {c: etiquetas[c] for c in claves}
    estrato = {c: muestra[c]["estrato"] for c in claves}
    sin = em.SIN_CLASIFICAR
    metodos = {}
    if a.conjunto == "desarrollo":
        reg = {c: em.reglas([d["descripcion"] or "" for d in productos[c]["descripciones"]]) for c in claves}
        metodos["reglas"] = {c: reg[c][0] or sin for c in claves}
        metodos["reglas unánimes"] = {c: reg[c][0] if reg[c][1] else sin for c in claves}
        metodos["DeepSeek solo"] = llm
        metodos["unánimes + DeepSeek"] = {c: reg[c][0] if reg[c][1] else llm[c] for c in claves}
        principal = "unánimes + DeepSeek"
        extra = {c: ("", "") for c in claves}
    else:
        previas = {f["clave"]: f for f in em.leer_csv(clasificacion / "predicciones_prueba.csv")}
        metodos["reglas"] = {c: previas[c]["reglas"] for c in claves}
        metodos["modelo"] = {c: previas[c]["modelo"] for c in claves}
        metodos["combinación actual"] = {c: previas[c]["combinacion"] for c in claves}
        metodos["DeepSeek solo"] = llm
        metodos["unánimes + DeepSeek"] = {c: previas[c]["reglas"] if previas[c]["unanime"] == "True" else llm[c] for c in claves}
        metodos["combinación + DeepSeek"] = {c: previas[c]["combinacion"] if previas[c]["combinacion"] != sin else llm[c] for c in claves}
        principal = "combinación + DeepSeek"
        extra = {c: (previas[c]["combinacion"], previas[c]["unanime"]) for c in claves}

    print(f"\n{'estrato':<14}{'método':<24}{'productos':>10}{'cobertura':>11}{'acierto':>9}{'acierto total':>15}{'F1 macro':>10}")
    for e in ["todos", "comparables", "una cadena", "pesables"]:
        indices = [c for c in claves if e in ("todos", estrato[c])]
        if not indices:
            continue
        for nombre, pred in metodos.items():
            m = em.medir([humano[c] for c in indices], [pred[c] for c in indices])
            print(f"{e:<14}{nombre:<24}{len(indices):>10}{m['cobertura']:>11.1%}{m['acierto']:>9.1%}"
                  f"{m['acierto_total']:>15.1%}{m['f1_macro']:>10.3f}")
        print()

    pred = metodos[principal]
    errores = [c for c in claves if pred[c] not in (humano[c], sin)]
    print(f"Errores de «{principal}» ({len(errores)}): humano | predicción | nombre")
    for c in errores[:40]:
        print(f"  {humano[c]:<26}{pred[c]:<26}{productos[c]['nombre'][:44]}")
    perdidos = [c for c in claves if pred[c] == sin]
    print(f"\nQuedaron sin clasificar con «{principal}»: {len(perdidos)} (humano | lo que dijo DeepSeek | nombre)")
    for c in perdidos[:40]:
        print(f"  {humano[c]:<26}{llm[c]:<26}{productos[c]['nombre'][:44]}")

    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="") as archivo:
        w = csv.writer(archivo)
        w.writerow(["clave", "estrato", "humano", "deepseek", "combinacion_previa", "unanime", "nombre"])
        for c in claves:
            w.writerow([c, estrato[c], humano[c], llm[c], extra[c][0], extra[c][1], productos[c]["nombre"]])
    print(f"\nEscrito {salida}")


if __name__ == "__main__":
    main()
