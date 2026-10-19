"""Paso 1: qué fechas ofrece hoy el portal y cuáles faltan procesar."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ingesta import config

DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
HORA_ARGENTINA = timezone(timedelta(hours=-3))


def crear_sesion():
    """Sesión HTTP con User-Agent propio y reintentos solo para errores temporales."""
    reintentos = Retry(
        total=4,
        backoff_factor=5,                      # espera creciente entre intentos
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    sesion = requests.Session()
    sesion.headers["User-Agent"] = config.USER_AGENT
    adaptador = HTTPAdapter(max_retries=reintentos)
    sesion.mount("https://", adaptador)
    sesion.mount("http://", adaptador)
    return sesion


def consultar_catalogo(sesion=None):
    """Devuelve el JSON del catálogo. Un 403 o 404 corta enseguida: reintentar no lo arregla."""
    sesion = sesion or crear_sesion()
    respuesta = sesion.get(config.URL_CATALOGO, timeout=60)
    respuesta.raise_for_status()
    return respuesta.json()


def sin_tildes(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def fecha_esperada(dia_semana, publicado):
    """La fecha más reciente con ese día de la semana que no es posterior a la publicación."""
    atras = (publicado.weekday() - dia_semana) % 7
    return publicado - timedelta(days=atras)


def zips_del_catalogo(catalogo):
    """Un registro por zip diario: día de la semana, fecha esperada, URL y tamaño."""
    zips = []
    for recurso in catalogo["result"]["resources"]:
        m = re.search(r"sepa_(\w+)\.zip$", sin_tildes(recurso.get("url", "")))
        if not m or m.group(1) not in DIAS:
            continue  # el Excel de provincias, el PDF de metadatos, etc.
        modificado = datetime.fromisoformat(recurso["last_modified"])
        if modificado.tzinfo is None:
            modificado = modificado.replace(tzinfo=timezone.utc)  # CKAN informa en UTC
        publicado = modificado.astimezone(HORA_ARGENTINA)
        zips.append({
            "dia": m.group(1),
            "fecha": fecha_esperada(DIAS[m.group(1)], publicado.date()),
            "publicado": publicado,
            "tamano": int(recurso["size"]) if recurso.get("size") else None,
            "url": recurso["url"],
        })
    return sorted(zips, key=lambda z: z["fecha"])


def ya_procesada(fecha):
    return (config.PARQUET_DIR / f"fecha={fecha.isoformat()}").is_dir()


def fechas_pendientes(catalogo):
    return [z for z in zips_del_catalogo(catalogo) if not ya_procesada(z["fecha"])]


def mostrar(catalogo):
    zips = zips_del_catalogo(catalogo)
    print(f"Carpeta de Parquet: {config.PARQUET_DIR}\n")
    print(f"{'día':<10}{'fecha':<12}{'publicado (AR)':<18}{'MB':>8}  procesada")
    for z in zips:
        mb = f"{z['tamano'] / 1024**2:,.0f}" if z["tamano"] else "?"
        print(f"{z['dia']:<10}{z['fecha'].isoformat():<12}{z['publicado']:%Y-%m-%d %H:%M}  {mb:>8}  "
              f"{'sí' if ya_procesada(z['fecha']) else 'NO'}")
    print(f"\nZips en el catálogo: {len(zips)} | pendientes: {sum(not ya_procesada(z['fecha']) for z in zips)}")


if __name__ == "__main__":
    mostrar(consultar_catalogo())