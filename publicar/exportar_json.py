"""Exporta los JSON que lee el sitio, desde la base sepa_nube de MotherDuck.

Escribe en la carpeta de salida (por defecto sitio/datos):
- meta.json: fecha del dato, fecha base de los días, fecha de publicación, nombre de cada cadena, la lista de
  rubros ([rubro, grupo]) y columnas de cada lista.
- indice.json: un registro por producto con historia, para el buscador. El último dato de cada registro es
  el rubro, como posición en la lista `rubros` de meta.json (-1 = sin clasificar).
- historia/NNN.json: unos 1.000 archivos. En cada uno, por producto, provincia y cadena, los cambios
  de la mediana del precio de lista como [día, precio] y el último día en que se vio. El archivo de
  cada producto sale de un hash fijo de la clave (crc32), así cae siempre en el mismo.
- hoy/<provincia>.json: por producto, el precio de hoy en cada cadena de esa provincia y los cambios
  de los últimos días (para los resultados del buscador: la tabla de precios por cadena, el gráfico
  chico y "qué cambió"; el navegador baja solo el de la provincia elegida).
- canasta.json: los productos de la canasta básica, la canasta nacional por día y el ranking por
  provincia (índice de precios sobre los productos que tienen todas las cadenas de cada provincia).
- comparacion/<provincia>.json: los códigos de esos productos, del último día de cada provincia (la
  lista de la página de la canasta; los precios salen de hoy/<provincia>.json).
- kilo/<provincia>.json: el precio por kilo de los productos pesables, por cadena.
- indice/<provincia>.json: el índice de precios de cada cadena (cuánto cambió su precio desde el primer día), de
  fct_indice_cadena; ver publicar/indice_json.py.

Los días son la cantidad de días desde la fecha base (números chicos ocupan menos que fechas).
Solo se publica la mediana y solo cuando cambia: es lo que muestra el gráfico, y así la historia
ocupa ~240 MB por año en vez de ~355 (medido el 21/10 con scripts/medir_historia_provincial.py).
Tampoco se publican los picos de muestra: un cambio de un día que vuelve al precio anterior, en un
día con cobertura baja de esa cadena en esa provincia (ver fct_cobertura).

La clave del producto es la misma regla de la macro clave_producto de dbt; si cambia allá, hay que
cambiarla acá.

Uso: python -m publicar.exportar_json [--local] [--salida CARPETA]
  --local lee la base de la PC en vez de MotherDuck (para probar, o si MotherDuck no está).
"""
import argparse
import json
import logging
import shutil
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ingesta import config
from publicar import indice_json

ARCHIVOS_HISTORIA = 1000
DIAS_NO_DISPONIBLE = 7
DIAS_GRAFICO = 13  # días que muestra el gráfico chico de cada resultado (hoy incluido)
RAIZ_REPO = Path(__file__).resolve().parents[1]
SALIDA_POR_DEFECTO = RAIZ_REPO / "sitio" / "datos"

CLAVE = """CASE WHEN regexp_full_match(id_producto, '\\d+') AND length(ltrim(id_producto, '0')) >= 8
                    AND NOT (length(id_producto) = 13 AND id_producto LIKE '2%')
               THEN ltrim(id_producto, '0') ELSE id_comercio || '-' || id_producto END"""

log = logging.getLogger("ingesta")


def precio(valor):
    """Decimal a número para JSON: 1310 en vez de 1310.0, y 2 decimales si los tiene."""
    if valor is None:
        return None
    p = round(float(valor), 2)
    return int(p) if p.is_integer() else p


def escribir(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    ruta.write_text(texto, encoding="utf-8")
    return len(texto.encode("utf-8"))


def precios_de_hoy(historia, dia_dato, orden_cadenas):
    """Por provincia: {clave: [precio de hoy en cada cadena, en el orden de orden_cadenas; 0 = no lo vende]}.

    Si alguna cadena cambió el precio dentro del gráfico chico (los últimos DIAS_GRAFICO días), la
    lista lleva un elemento más con esos cambios: [[posición de la cadena, hace cuántos días, precio
    anterior], ...]. Con el precio de hoy y los cambios, el sitio arma hacia atrás la línea de cada
    cadena. Ejemplo: [4200, 4300, 0, ..., [[1, 6, 4150]]] = la cadena 2 de la lista subió hace 6 días;
    antes costaba 4150.

    Solo cuentan las cadenas que siguen vendiendo el producto, vistas en los últimos
    DIAS_NO_DISPONIBLE días. Es la foto de hoy: se reemplaza cada día y no crece con la historia
    (~38 MB en total y ~0,85 MB comprimido la provincia más grande; medido el 21/10 con
    scripts/medir_hoy_matriz.py).
    """
    posicion = {c: i for i, c in enumerate(orden_cadenas)}
    primer_dia = dia_dato - (DIAS_GRAFICO - 1)
    hoy, desconocidas = {}, set()
    for productos in historia.values():
        for clave, provincias in productos.items():
            for provincia, cadenas in provincias.items():
                vigentes = {c: linea for c, linea in cadenas.items()
                            if dia_dato - linea["u"] <= DIAS_NO_DISPONIBLE}
                desconocidas |= set(vigentes) - set(posicion)
                vigentes = {c: linea for c, linea in vigentes.items() if c in posicion}
                if not vigentes:
                    continue
                precios = [0] * len(orden_cadenas)
                for c, linea in vigentes.items():
                    precios[posicion[c]] = linea["p"][-1][1]
                # Un cambio es un punto con otro antes (el primero de la línea no lo es), posterior al
                # primer día del gráfico (un cambio ese mismo día solo fija el precio con que arranca)
                cambios = [[posicion[c], dia_dato - linea["p"][k][0], linea["p"][k - 1][1]]
                           for c, linea in vigentes.items()
                           for k in range(1, len(linea["p"])) if linea["p"][k][0] > primer_dia]
                hoy.setdefault(provincia, {})[clave] = precios + [cambios] if cambios else precios
    if desconocidas:
        log.warning(f"Cadenas que no están en la semilla cadenas.csv (no aparecen en hoy/*.json): "
                    f"{sorted(desconocidas)}")
    return hoy


def conectar(local):
    if local:
        return duckdb.connect((config.DATOS_DIR / "sepa.duckdb").as_posix(), read_only=True)
    return duckdb.connect("md:sepa_nube")


def exportar(local=False, salida=SALIDA_POR_DEFECTO):
    inicio = time.monotonic()
    con = conectar(local)
    try:
        # Historia: solo los cambios de la mediana, con la clave del producto y días desde la fecha base
        con.execute("""
            CREATE TEMP TABLE mediana AS
            SELECT * EXCLUDE (anterior) FROM (
                SELECT id_producto, provincia, id_comercio, fecha_desde,
                       precio_lista_mediana AS precio, ultima_fecha_vista,
                       lag(precio_lista_mediana) OVER (
                           PARTITION BY id_comercio, id_producto, provincia ORDER BY fecha_desde) AS anterior
                FROM fct_precios_historial)
            WHERE anterior IS NULL OR anterior <> precio
        """)
        # Picos de muestra: un cambio que dura un día y vuelve al precio anterior, en un día en que la
        # cadena informó desde menos sucursales que lo habitual en esa provincia (fct_cobertura). No es
        # un cambio de precio: cambió el grupo de sucursales. Los picos con la cobertura normal se
        # quedan, porque son reales (Coto los domingos). Después de sacarlos se vuelven a juntar los
        # puntos repetidos: el precio del día siguiente al pico es igual al de antes.
        con.execute(f"""
            CREATE TEMP TABLE serie AS
            WITH vecinos AS (
                SELECT m.*,
                       lag(precio) OVER w AS precio_antes, lead(precio) OVER w AS precio_despues,
                       lead(fecha_desde) OVER w AS fecha_despues
                FROM mediana m
                WINDOW w AS (PARTITION BY id_comercio, id_producto, provincia ORDER BY fecha_desde)),
            sin_picos AS (
                SELECT v.* FROM vecinos v
                LEFT JOIN fct_cobertura k
                  ON k.fecha = v.fecha_desde AND k.id_comercio = v.id_comercio AND k.provincia = v.provincia
                -- coalesce: sin punto anterior o siguiente (el primero o el último de la línea), la
                -- comparación da NULL y el WHERE descartaría la fila; así cuenta como "no es pico"
                WHERE NOT coalesce(k.cobertura_baja
                                   AND v.fecha_despues = v.fecha_desde + 1
                                   AND v.precio_despues = v.precio_antes, false))
            SELECT {CLAVE} AS clave, provincia, id_comercio, fecha_desde, precio, ultima_fecha_vista
            FROM (
                SELECT *, lag(precio) OVER (
                           PARTITION BY id_comercio, id_producto, provincia ORDER BY fecha_desde) AS anterior
                FROM sin_picos)
            WHERE anterior IS NULL OR anterior <> precio
        """)
        picos = con.execute("SELECT (SELECT count(*) FROM mediana) - (SELECT count(*) FROM serie)").fetchone()[0]
        fecha_base, fecha_dato = con.execute(
            "SELECT min(fecha_desde), (SELECT max(fecha) FROM fct_cobertura) FROM serie").fetchone()

        def dia(fecha):
            return (fecha - fecha_base).days

        historia = {}
        for clave, provincia, comercio, desde, valor, ultima in con.execute(
                "SELECT clave, provincia, id_comercio, fecha_desde, precio, ultima_fecha_vista "
                "FROM serie ORDER BY clave, provincia, id_comercio, fecha_desde").fetchall():
            archivo = historia.setdefault(zlib.crc32(clave.encode()) % ARCHIVOS_HISTORIA, {})
            linea = archivo.setdefault(clave, {}).setdefault(provincia, {}).setdefault(
                comercio, {"p": [], "u": dia(ultima)})
            linea["p"].append([dia(desde), precio(valor)])

        # Lista de rubros (semilla rubros.csv): el índice guarda la posición en esta lista y no el nombre,
        # para no repetirlo en decenas de miles de filas
        rubros = [[rubro, grupo] for rubro, grupo in
                  con.execute("SELECT rubro, grupo FROM rubros ORDER BY grupo, rubro").fetchall()]
        posicion_rubro = {rubro: i for i, (rubro, _) in enumerate(rubros)}

        # Índice: solo productos que tienen historia
        archivo_de = {clave: n for n, productos in historia.items() for clave in productos}
        indice, rubros_desconocidos = [], set()
        for clave, nombre, marca, presentacion, cadenas, rubro in con.execute(
                "SELECT clave, nombre, marca, presentacion, cadenas, rubro FROM dim_productos ORDER BY clave").fetchall():
            if clave not in archivo_de:
                continue
            if rubro is not None and rubro not in posicion_rubro:
                rubros_desconocidos.add(rubro)
            indice.append([clave, nombre, marca, presentacion, cadenas, archivo_de[clave],
                           posicion_rubro.get(rubro, -1)])
        if rubros_desconocidos:
            raise ValueError(f"dim_productos tiene rubros que no están en la semilla rubros: {sorted(rubros_desconocidos)}. "
                             f"¿Se subió rubros a MotherDuck? (python -m publicar.subir_marts rubros dim_productos)")
        con_rubro = sum(fila[6] >= 0 for fila in indice)

        # Nombre de cada cadena (semilla cadenas.csv), para que el sitio no muestre números
        nombres_cadenas = {id_comercio: {"nombre": nombre, "banderas": banderas}
                           for id_comercio, nombre, banderas in
                           con.execute("SELECT id_comercio, nombre, banderas FROM cadenas").fetchall()}
        # Orden de las cadenas en hoy/*.json: por número de comercio. Va en meta.json para el sitio,
        # así una cadena nueva en la semilla aparece sola, sin tocar app.js.
        orden_cadenas = sorted(nombres_cadenas, key=int)

        # Qué cadenas hay en cada provincia (para el mapa de la portada y las columnas de los
        # resultados): las que informaron desde alguna sucursal en los últimos DIAS_NO_DISPONIBLE días,
        # la misma ventana que usa hoy/*.json. Así un domingo con menos sucursales no cambia el mapa.
        cadenas_por_provincia = {
            provincia: sorted(ids, key=int)
            for provincia, ids in con.execute(f"""
                SELECT provincia, list(DISTINCT id_comercio)
                FROM fct_cobertura
                WHERE provincia IS NOT NULL AND sucursales > 0
                  AND fecha >= (SELECT max(fecha) FROM fct_cobertura) - INTERVAL {DIAS_NO_DISPONIBLE} DAY
                GROUP BY provincia""").fetchall()}

        # Productos de la comparación de cada provincia, el último día que tiene cada una: la misma
        # tabla con que dbt arma el ranking, así la lista coincide con el "631 productos" del sitio
        comparacion = {}
        for provincia, clave in con.execute("""
                SELECT provincia, clave FROM fct_canasta_provincia_productos
                WHERE (provincia, fecha) IN (
                    SELECT provincia, max(fecha) FROM fct_canasta_provincia_productos GROUP BY provincia)
                ORDER BY provincia, clave""").fetchall():
            comparacion.setdefault(provincia, []).append(clave)

        canasta = {
            "productos": con.execute(
                "SELECT ltrim(ean, '0'), nombre, grupo, rubro FROM canasta ORDER BY grupo, rubro").fetchall(),
            "nacional": [
                [dia(f), cadena, precio(total), observados, arrastrados, completa]
                for f, cadena, total, observados, arrastrados, completa in con.execute(
                    "SELECT fecha, id_comercio, total, productos_observados, productos_arrastrados, completa "
                    "FROM fct_canasta_nacional ORDER BY fecha, id_comercio").fetchall()],
            "provincias": [
                [dia(f), provincia, cadena, cadenas, productos, indice, diferencia, puesto]
                for f, provincia, cadena, cadenas, productos, indice, diferencia, puesto in con.execute(
                    "SELECT fecha, provincia, id_comercio, cadenas, productos_comparados, indice, diferencia, puesto "
                    "FROM fct_canasta_provincia ORDER BY fecha, provincia, puesto").fetchall()],
            "grupos": [
                [dia(f), provincia, grupo, cadena, productos, indice, diferencia, puesto]
                for f, provincia, grupo, cadena, productos, indice, diferencia, puesto in con.execute(
                    "SELECT fecha, provincia, grupo, id_comercio, productos_comparados, indice, diferencia, puesto "
                    "FROM fct_canasta_provincia_grupo ORDER BY provincia, grupo, puesto").fetchall()],
        }
        # Precio por kilo: un archivo por provincia, con el último día de cada una
        kilo = {}
        for provincia, producto, grupo, cadena, productos, precio_kg, antes, promo, baja, con_promo in con.execute("""
                SELECT provincia, producto, grupo, id_comercio, productos, precio_kg, antes_kg, promo_kg,
                       baja_fuerte, con_promo
                FROM fct_precio_kilo_provincia
                ORDER BY provincia, grupo, producto, id_comercio""").fetchall():
            archivo = kilo.setdefault(provincia, {"productos": [], "filas": []})
            nombres = [p[0] for p in archivo["productos"]]
            if producto not in nombres:
                archivo["productos"].append([producto, grupo])
                nombres.append(producto)
            fila = [nombres.index(producto), cadena, productos, precio(precio_kg)]
            if baja:
                fila += [1, precio(antes)]
            elif con_promo:
                fila += [2, precio(promo)]
            archivo["filas"].append(fila)

        # Índice de precios de cada cadena: un archivo por provincia (ver publicar/indice_json.py)
        indice_cadenas = indice_json.leer(con, dia)
    finally:
        con.close()

    # Se escribe todo de nuevo: así no quedan archivos de una corrida anterior
    if salida.exists():
        shutil.rmtree(salida)
    bytes_historia = sum(escribir(salida / "historia" / f"{n:03d}.json", productos)
                         for n, productos in historia.items())
    bytes_indice = escribir(salida / "indice.json", indice)
    bytes_hoy = sum(escribir(salida / "hoy" / f"{provincia}.json", productos)
                    for provincia, productos in precios_de_hoy(historia, dia(fecha_dato), orden_cadenas).items())
    bytes_canasta = escribir(salida / "canasta.json", canasta)
    bytes_comparacion = sum(escribir(salida / "comparacion" / f"{provincia}.json", claves)
                            for provincia, claves in comparacion.items())
    bytes_kilo = sum(escribir(salida / "kilo" / f"{provincia}.json", datos) for provincia, datos in kilo.items())
    bytes_indice_cadenas = indice_json.escribir(salida, indice_cadenas)
    escribir(salida / "meta.json", {
        "fecha_dato": fecha_dato.isoformat(),
        "fecha_base": fecha_base.isoformat(),
        "dia_dato": dia(fecha_dato),
        "publicado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cadenas": nombres_cadenas,
        "orden_cadenas": orden_cadenas,
        "rubros": rubros,
        "cadenas_por_provincia": cadenas_por_provincia,
        "dias_grafico": DIAS_GRAFICO,
        "columnas": {
            "indice": ["clave", "nombre", "marca", "presentacion", "cadenas", "archivo", "rubro (posicion en rubros; -1 = sin clasificar)"],
            "historia": "clave > provincia > cadena > {p: [[dia, precio], ...], u: ultimo dia visto}",
            "comparacion": "comparacion/<provincia>.json: lista de claves de los productos con que se compara la provincia",
            "hoy": "hoy/<provincia>.json: clave > [precio de hoy de cada cadena en orden_cadenas (0 = no lo vende), "
                   "y si hubo cambios en los ultimos dias_grafico dias: [[posicion de la cadena, hace cuantos dias, precio anterior], ...]]",
            "canasta_productos": ["clave", "nombre", "grupo", "rubro"],
            "canasta_nacional": ["dia", "cadena", "total", "observados", "arrastrados", "completa"],
            "canasta_grupos": ["dia", "provincia", "grupo", "cadena", "productos", "indice", "diferencia", "puesto"],
            "kilo": "kilo/<provincia>.json: productos [[nombre, grupo]] y filas [posicion del producto, cadena, productos, precio por kilo, tipo (1 baja fuerte, 2 promocion; sin tipo = normal), precio anterior o de promocion]",
            "indice_cadenas": "indice/<provincia>.json: s = {cadena: [[dia, indice con base 100 el primer dia], ...]} y n = {cadena: mediana de productos por dia}",
        },
    })
    mb = lambda b: b / 1024 / 1024
    puntos = sum(len(l["p"]) for a in historia.values() for p in a.values() for pr in p.values() for l in pr.values())
    log.info(f"JSON exportados en {time.monotonic() - inicio:,.0f} s -> {salida} | fecha del dato {fecha_dato} | "
             f"índice {len(indice):,} productos, {con_rubro:,} con rubro ({mb(bytes_indice):,.1f} MB) | historia {len(historia):,} archivos, "
             f"{puntos:,} puntos ({mb(bytes_historia):,.1f} MB, {picos:,} quitados por picos de muestra) | "
             f"precios de hoy {mb(bytes_hoy):,.1f} MB | canasta {mb(bytes_canasta) * 1024:,.0f} KB | "
             f"comparación {sum(map(len, comparacion.values())):,} productos en {len(comparacion)} provincias "
             f"({mb(bytes_comparacion) * 1024:,.0f} KB) | "
             f"kilo {len(kilo)} provincias ({mb(bytes_kilo) * 1024:,.0f} KB) | "
             f"índice de cadenas {len(indice_cadenas)} provincias ({mb(bytes_indice_cadenas) * 1024:,.0f} KB)")

    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    argumentos = argparse.ArgumentParser(description="Exporta los JSON del sitio")
    argumentos.add_argument("--local", action="store_true", help="leer la base de la PC en vez de MotherDuck")
    argumentos.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO, help="carpeta de salida")
    a = argumentos.parse_args()
    sys.exit(0 if exportar(a.local, a.salida) else 1)
