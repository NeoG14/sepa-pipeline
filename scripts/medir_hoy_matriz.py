"""Mide cuánto pesarían los archivos hoy/<provincia>.json con los datos del diseño nuevo.

No toca la base: lee lo que ya exportó publicar.exportar_json (sitio/datos) y arma en memoria
tres formatos del archivo de cada provincia, para comparar:

- actual:   clave > [precio más bajo, bits de las más baratas, bits de las que tienen precio]
- matriz:   clave > [precio de hoy en cada cadena, en el orden de bits_cadenas; 0 = no lo vende]
            (para la tabla de precios por cadena de los resultados)
- matriz + cambios: lo mismo y, solo si alguna cadena cambió el precio en los últimos N días,
            un elemento más: [[cadena, hace cuántos días, precio anterior], ...]
            (para el gráfico chico y "qué cambió" de cada resultado)

El tamaño comprimido (gzip) es el que importa para la descarga: GitHub Pages sirve los JSON
comprimidos.

Uso: python scripts/medir_hoy_matriz.py [--datos sitio/datos] [--dias 13]
"""
import argparse
import gzip
import json
from pathlib import Path

DIAS_NO_DISPONIBLE = 7  # igual que en publicar/exportar_json.py
RAIZ_REPO = Path(__file__).resolve().parents[1]


def tamanio(datos):
    """Bytes del JSON tal como lo escribe el exportador, sin comprimir y comprimido."""
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return len(texto), len(gzip.compress(texto, 6))


def main():
    argumentos = argparse.ArgumentParser(description="Mide los formatos posibles de hoy/*.json")
    argumentos.add_argument("--datos", type=Path, default=RAIZ_REPO / "sitio" / "datos")
    argumentos.add_argument("--dias", type=int, default=13, help="días que muestra el gráfico chico")
    a = argumentos.parse_args()

    meta = json.loads((a.datos / "meta.json").read_text(encoding="utf-8"))
    dia_dato = meta["dia_dato"]
    bits = meta["bits_cadenas"]
    orden = sorted(bits, key=bits.get)          # cadenas en el orden de sus bits: 2, 9, 10, ...
    posicion = {c: i for i, c in enumerate(orden)}
    primer_dia = dia_dato - (a.dias - 1)        # primer día que muestra el gráfico

    actual, matriz, con_cambios = {}, {}, {}
    total_cambios = productos_que_cambiaron = 0
    for archivo in sorted((a.datos / "historia").glob("*.json")):
        for clave, provincias in json.loads(archivo.read_text(encoding="utf-8")).items():
            for provincia, cadenas in provincias.items():
                # Misma regla que precios_de_hoy: solo cadenas vistas en los últimos 7 días
                vigentes = {c: linea for c, linea in cadenas.items()
                            if dia_dato - linea["u"] <= DIAS_NO_DISPONIBLE}
                if not vigentes:
                    continue
                hoy = {c: linea["p"][-1][1] for c, linea in vigentes.items()}
                minimo = min(hoy.values())
                actual.setdefault(provincia, {})[clave] = [
                    minimo,
                    sum(bits.get(c, 0) for c, p in hoy.items() if p == minimo),
                    sum(bits.get(c, 0) for c in hoy)]

                precios = [0] * len(orden)
                for c, p in hoy.items():
                    if c in posicion:
                        precios[posicion[c]] = p
                matriz.setdefault(provincia, {})[clave] = precios

                # Cambios dentro del gráfico: un punto con otro antes (el primero de la línea no es un
                # cambio) y posterior al primer día (un cambio ese mismo día solo fija el precio inicial)
                cambios = [[posicion[c], dia_dato - linea["p"][k][0], linea["p"][k - 1][1]]
                           for c, linea in vigentes.items() if c in posicion
                           for k in range(1, len(linea["p"])) if linea["p"][k][0] > primer_dia]
                if cambios:
                    total_cambios += len(cambios)
                    productos_que_cambiaron += 1
                con_cambios.setdefault(provincia, {})[clave] = precios + [cambios] if cambios else precios

    # Control: el formato actual armado acá tiene que pesar lo mismo que hoy/ en disco
    en_disco = sum(f.stat().st_size for f in (a.datos / "hoy").glob("*.json"))

    mb = lambda b: b / 1024 / 1024
    print(f"Fecha del dato: {meta['fecha_dato']} | días con historia: {dia_dato + 1} | "
          f"gráfico chico: últimos {a.dias} días")
    if dia_dato + 1 <= a.dias:
        print("  (la historia todavía no es más larga que el gráfico: se usan todos los días que hay)")
    print(f"Productos con precio, sumando provincias: {sum(len(p) for p in actual.values()):,}")
    print(f"  con algún cambio en el gráfico: {productos_que_cambiaron:,} | cambios: {total_cambios:,}\n")

    formatos = {"actual": actual, "matriz": matriz, "matriz + cambios": con_cambios}
    base = None
    print(f"{'formato':<18}{'total MB':>10}{'gzip MB':>10}{'x actual':>10}{'mayor provincia':>22}{'KB':>8}{'gzip KB':>9}")
    for nombre, por_provincia in formatos.items():
        medidas = {provincia: tamanio(productos) for provincia, productos in por_provincia.items()}
        total = sum(m[0] for m in medidas.values())
        comprimido = sum(m[1] for m in medidas.values())
        base = base or total
        mayor = max(medidas, key=lambda p: medidas[p][0])
        print(f"{nombre:<18}{mb(total):>10.1f}{mb(comprimido):>10.1f}{total / base:>10.2f}"
              f"{mayor:>22}{medidas[mayor][0] / 1024:>8,.0f}{medidas[mayor][1] / 1024:>9,.0f}")
        if nombre == "actual":
            print(f"  control: hoy/ en disco pesa {en_disco:,} bytes; armado acá, {total:,} -> "
                  f"{'coinciden' if en_disco == total else 'NO coinciden'}")


if __name__ == "__main__":
    main()
