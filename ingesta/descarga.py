"""Pasos 2 y 3: descargar un zip del portal y verificar tamaño, integridad y fecha interna."""
import logging
import re
import sys
import time
import zipfile
from datetime import date

import requests

from ingesta import catalogo, config

TEMP_DIR = config.DATOS_DIR / "temp"
log = logging.getLogger("ingesta")


def descargar(sesion, url, destino, tamano_esperado=None, intentos=3):
    """Descarga por partes a un .part y lo renombra al terminar. Reintenta si se corta la conexión."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".part")
    for intento in range(1, intentos + 1):
        try:
            with sesion.get(url, stream=True, timeout=(30, 120)) as respuesta:
                respuesta.raise_for_status()
                with open(parcial, "wb") as f:
                    for bloque in respuesta.iter_content(chunk_size=1024 * 1024):
                        f.write(bloque)
            break
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError) as e:
            if intento == intentos:
                raise
            log.warning(f"La descarga se cortó ({e.__class__.__name__}); reintento {intento + 1} de {intentos}")
            time.sleep(15 * intento)
    tamano = parcial.stat().st_size
    if tamano_esperado and tamano != tamano_esperado:
        parcial.unlink()
        raise ValueError(f"Tamaño distinto al del catálogo: {tamano:,} bytes, se esperaban {tamano_esperado:,}")
    parcial.replace(destino)
    return destino


def verificar_zip(ruta, fecha_esperada):
    """Comprueba la integridad del zip y que su carpeta interna sea de la fecha esperada."""
    with zipfile.ZipFile(ruta) as z:
        roto = z.testzip()
        if roto:
            raise ValueError(f"Archivo dañado dentro del zip: {roto}")
        carpetas = {m.group(1) for n in z.namelist() if (m := re.match(r"(\d{4}-\d{2}-\d{2})/", n))}
    if carpetas != {fecha_esperada.isoformat()}:
        raise ValueError(f"Fecha interna {sorted(carpetas)}; se esperaba {fecha_esperada.isoformat()}")
    return fecha_esperada


def descargar_fecha(sesion, zip_info):
    """Descarga y verifica el zip de una fecha. Devuelve la ruta del zip listo para procesar."""
    destino = TEMP_DIR / f"sepa_{zip_info['fecha'].isoformat()}.zip"
    inicio = time.time()
    descargar(sesion, zip_info["url"], destino, zip_info["tamano"])
    try:
        verificar_zip(destino, zip_info["fecha"])
    except Exception:
        destino.unlink()  # un zip que no pasó la verificación no se deja con nombre de bueno
        raise
    log.info(f"{zip_info['fecha']}: {destino.stat().st_size / 1024**2:,.0f} MB descargados y verificados "
          f"en {time.time() - inicio:,.0f} s -> {destino}")
    return destino


if __name__ == "__main__":
    # Uso: python -m ingesta.descarga AAAA-MM-DD   (sin fecha: la pendiente más reciente)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sesion = catalogo.crear_sesion()
    pendientes = catalogo.fechas_pendientes(catalogo.consultar_catalogo(sesion))
    if len(sys.argv) > 1:
        pendientes = [z for z in pendientes if z["fecha"] == date.fromisoformat(sys.argv[1])]
    if not pendientes:
        sys.exit("No hay una fecha pendiente que coincida.")
    descargar_fecha(sesion, pendientes[-1])