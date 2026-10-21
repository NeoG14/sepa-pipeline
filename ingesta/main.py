"""Ingesta diaria: baja las fechas que falten, las procesa, las copia a Drive y registra los controles.

Uso: python -m ingesta.main   (es lo que ejecuta el Programador de tareas)
"""
import logging
import os
import shutil
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

from ingesta import catalogo, config, registro
from ingesta.descarga import TEMP_DIR, descargar_fecha
from ingesta.procesar import copiar_a_drive, procesar_fecha

DIAS_SIN_DATOS_PARA_AVISAR = 3
RAIZ_REPO = Path(__file__).resolve().parents[1]  # donde están dbt_project.yml y profiles.yml
ESPERA_DRIVE_MINUTOS = 15
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
    log.propagate = False  # dbt configura su propio logging: sin esto cada línea sale dos veces


def esperar_drive(minutos=ESPERA_DRIVE_MINUTOS, cada_segundos=30):
    """Al iniciar sesión, Google Drive tarda unos minutos en montar la unidad: la espera un rato."""
    if config.DRIVE_DIR.exists():
        return True
    log.info(f"Drive todavía no está disponible; espero hasta {minutos} min")
    limite = time.monotonic() + minutos * 60
    while time.monotonic() < limite:
        time.sleep(cada_segundos)
        if config.DRIVE_DIR.exists():
            log.info("Drive disponible")
            return True
    return False


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


def correr_dbt():
    """Paso 9: dbt build actualiza el agregado diario, el historial y corre todos los tests.

    Corre siempre, haya fechas nuevas o no: si no hay, termina en segundos sin cambiar nada,
    y si una corrida anterior falló, esta lo vuelve a intentar.
    """
    from dbt.cli.main import dbtRunner  # import acá: si dbt falla al cargar, la ingesta ya terminó

    # profiles.yml lee la ruta de la base de esta variable; si la tarea programada no la
    # hereda, se usa la misma carpeta de datos que usa la ingesta
    os.environ.setdefault("SEPA_DATOS_DIR", str(config.DATOS_DIR))
    inicio = time.monotonic()
    try:
        resultado = dbtRunner().invoke(
            ["build", "--project-dir", str(RAIZ_REPO), "--profiles-dir", str(RAIZ_REPO), "--quiet"])
    except Exception:
        log.exception("dbt build no pudo arrancar")
        return False
    if resultado.result is None:  # error antes de ejecutar nodos (configuración, base bloqueada...)
        log.error(f"dbt build falló: {resultado.exception}")
        return False
    estados = Counter(str(r.status) for r in resultado.result.results)
    problemas = [r.node.name for r in resultado.result.results if str(r.status) in ("error", "fail")]
    avisos = [r.node.name for r in resultado.result.results if str(r.status) == "warn"]
    resumen = ", ".join(f"{estado} {n}" for estado, n in sorted(estados.items()))
    if resultado.success:
        log.info(f"dbt build OK en {time.monotonic() - inicio:,.0f} s | {resumen}")
        if avisos:
            log.warning(f"dbt avisos: {avisos}")
    else:
        log.error(f"dbt build con problemas en {time.monotonic() - inicio:,.0f} s | {resumen} | {problemas}")
    return resultado.success


def main():
    configurar_logging()
    log.info(f"Inicio | Drive: {config.DRIVE_DIR}")
    if not esperar_drive():
        log.error(f"No encuentro la carpeta de Drive después de {ESPERA_DRIVE_MINUTOS} min: {config.DRIVE_DIR}. "
                  "¿Está abierto Google Drive?")
        return 1
    sesion = catalogo.crear_sesion()
    try:
        pendientes = catalogo.fechas_pendientes(catalogo.consultar_catalogo(sesion))
    except Exception:
        log.exception("No se pudo consultar el catálogo")
        return 1
    log.info(f"Pendientes: {[z['fecha'].isoformat() for z in pendientes] or 'ninguna'}")

    fallidas = [z["fecha"] for z in pendientes if not procesar_pendiente(sesion, z)]
    dbt_ok = correr_dbt()

    ultima = registro.ultima_fecha_procesada()
    if ultima is None or (date.today() - ultima).days > DIAS_SIN_DATOS_PARA_AVISAR:
        log.warning(f"La última fecha procesada es {ultima}: hace más de {DIAS_SIN_DATOS_PARA_AVISAR} días sin datos nuevos")
    log.info(f"Fin | procesadas {len(pendientes) - len(fallidas)} | fallidas {[f.isoformat() for f in fallidas] or 'ninguna'}")
    return 1 if fallidas or not dbt_ok else 0


if __name__ == "__main__":
    sys.exit(main())