"""El índice de precios de cada cadena para el sitio: indice/<provincia>.json, desde fct_indice_cadena. Lo usa exportar_json.py.

fct_indice_cadena guarda, por día, provincia y cadena, cuánto cambió el precio contra el día anterior (`factor`). Acá se
acumulan: el índice parte de 100 el día anterior al primer factor de la cadena y se multiplica por cada factor.

Cada archivo trae:
- s: {cadena: [[día, índice], ...]}  (días desde la fecha base de meta.json; el índice con 2 decimales)
- n: {cadena: mediana de productos por día}  (cuántos productos entran en el índice de esa cadena)
Si una cadena no informó un día, no tiene punto ese día y el índice sigue de ahí con el primer factor que sí tiene.
"""
import json
import statistics


def leer(con, dia):
    """-> {provincia: {"s": ..., "n": ...}}. `dia` pasa una fecha a días desde la fecha base."""
    series, productos = {}, {}
    for provincia, cadena, fecha, anterior, factor, n in con.execute(
            "SELECT provincia, id_comercio, fecha, fecha_anterior, factor, productos FROM fct_indice_cadena "
            "WHERE factor IS NOT NULL ORDER BY provincia, try_cast(id_comercio AS INTEGER), fecha").fetchall():
        puntos = series.setdefault((provincia, cadena), [])
        if not puntos:
            puntos.append([dia(anterior), 100.0])
        puntos.append([dia(fecha), round(puntos[-1][1] * float(factor), 4)])
        productos.setdefault((provincia, cadena), []).append(n)
    por_provincia = {}
    for (provincia, cadena), puntos in series.items():
        datos = por_provincia.setdefault(provincia, {"s": {}, "n": {}})
        datos["s"][cadena] = [[d, round(v, 2)] for d, v in puntos]
        datos["n"][cadena] = round(statistics.median(productos[(provincia, cadena)]))
    return por_provincia


def escribir(salida, por_provincia):
    """Escribe salida/indice/<provincia>.json y devuelve los bytes escritos."""
    carpeta = salida / "indice"
    carpeta.mkdir(parents=True, exist_ok=True)
    total = 0
    for provincia, datos in por_provincia.items():
        texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
        (carpeta / f"{provincia}.json").write_text(texto, encoding="utf-8")
        total += len(texto.encode("utf-8"))
    return total
