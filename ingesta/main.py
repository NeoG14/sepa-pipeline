"""Ingesta diaria: baja las fechas que falten, las procesa, las copia a Drive y registra los controles.

Uso: python -m ingesta.main   (es lo que ejecuta el Programador de tareas)
"""
import logging
import shutil
import sys
from datetime import date

from ingesta import catalogo, config, registro
from ingesta.descarga import TEMP_DIR, descargar_fecha
from ingesta.procesar import copiar_a_drive, procesar_fecha

DIAS_SIN_DATOS_PARA_AVISAR = 3
log = logging.getLogger("ingesta")


def configurar_logging():
    if log.handlers:  # ya configurado en este proceso
        return
    carpeta = config.DATOS_DIR / "logs"
    carpeta.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    archivo = logging.FileHandler(carpeta / f"ingesta_{date.today():%Y-%m}.log", encoding="utf-8")
    pantalla = logging.StreamHandler(sys.stdout)
    for h in (archivo, pantalla):
        h.setFormatter(formato)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def limpiar(fecha):
    """Borra el zip y los CSV extraídos de una fecha, haya salido bien o mal."""
    (TEMP_DIR / f"sepa_{fecha.isoformat()}.zip").unlink(missing_ok=True)
    shutil.rmtree(TEMP_DIR / f"extraido_{fecha.isoformat()}", ignore_errors=True)


def procesar_pendiente(sesion, zip_info):
    fecha = zip_info["fecha"]
    try:
        descargar_fecha(sesion, zip_info)
        controles = procesar_fecha(fecha)
        destino = copiar_a_drive(fecha)
        alertas = registro.registrar(controles)
        log.info(f"{fecha}: {controles['filas']:,} filas | sin sucursal {sum(c['filas_sin_sucursal'] for c in controles['por_comercio']):,} "
                 f"| claves repetidas {controles['claves_repetidas']} | sucursales sin provincia "
                 f"{controles['sucursales_sin_provincia']} -> {destino}")
        for alerta in alertas:
            log.warning(f"{fecha}: ALERTA {alerta}")
        return True
    except Exception:
        log.exception(f"{fecha}: falló; se reintenta en la próxima ejecución")
        return False
    finally:
        limpiar(fecha)


def main():
    configurar_logging()
    log.info(f"Inicio | Drive: {config.DRIVE_DIR}")
    if not config.DRIVE_DIR.exists():
        log.error(f"No encuentro la carpeta de Drive: {config.DRIVE_DIR}. ¿Está abierto Google Drive?")
        return 1
    sesion = catalogo.crear_sesion()
    try:
        pendientes = catalogo.fechas_pendientes(catalogo.consultar_catalogo(sesion))
    except Exception:
        log.exception("No se pudo consultar el catálogo")
        return 1
    log.info(f"Pendientes: {[z['fecha'].isoformat() for z in pendientes] or 'ninguna'}")

    fallidas = [z["fecha"] for z in pendientes if not procesar_pendiente(sesion, z)]

    ultima = registro.ultima_fecha_procesada()
    if ultima is None or (date.today() - ultima).days > DIAS_SIN_DATOS_PARA_AVISAR:
        log.warning(f"La última fecha procesada es {ultima}: hace más de {DIAS_SIN_DATOS_PARA_AVISAR} días sin datos nuevos")
    log.info(f"Fin | procesadas {len(pendientes) - len(fallidas)} | fallidas {[f.isoformat() for f in fallidas] or 'ninguna'}")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main())