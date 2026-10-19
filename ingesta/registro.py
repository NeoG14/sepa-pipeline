"""Registro diario: una fila por fecha y comercio, con alerta si varía mucho contra la semana anterior."""
import csv
from datetime import date, datetime, timedelta

from ingesta import config

REGISTRO = config.DRIVE_DIR / "registro.csv"
UMBRAL_ALERTA = 0.05  # ±5 % contra el mismo día de la semana anterior
COLUMNAS = ["fecha", "id_comercio", "filas", "sucursales_con_precios", "sin_precio_lista",
            "filas_sin_sucursal", "variacion_semana_anterior", "alerta", "procesado_en"]


def leer():
    if not REGISTRO.exists():
        return []
    with open(REGISTRO, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def registrar(controles):
    """Agrega (o reemplaza) las filas de una fecha y devuelve las alertas del día."""
    fecha = controles["fecha"]
    filas = [r for r in leer() if r["fecha"] != fecha]  # reprocesar una fecha no la duplica
    semana_anterior = (date.fromisoformat(fecha) - timedelta(days=7)).isoformat()
    referencia = {r["id_comercio"]: int(r["filas"]) for r in filas if r["fecha"] == semana_anterior}
    alertas = []
    for c in controles["por_comercio"]:
        ref = referencia.get(c["id_comercio"])
        variacion = (c["filas"] - ref) / ref if ref else None
        alerta = variacion is not None and abs(variacion) > UMBRAL_ALERTA
        if alerta:
            alertas.append(f"Comercio {c['id_comercio']}: {c['filas']:,} filas, "
                           f"{variacion:+.1%} contra el {semana_anterior} ({ref:,})")
        filas.append({
            "fecha": fecha, "id_comercio": c["id_comercio"], "filas": c["filas"],
            "sucursales_con_precios": c["sucursales_con_precios"], "sin_precio_lista": c["sin_precio_lista"],
            "filas_sin_sucursal": c["filas_sin_sucursal"],
            "variacion_semana_anterior": "" if variacion is None else f"{variacion:.4f}",
            "alerta": "sí" if alerta else "", "procesado_en": datetime.now().isoformat(timespec="seconds"),
        })
    filas.sort(key=lambda r: (r["fecha"], int(r["id_comercio"])))
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRO, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)
    return alertas


def ultima_fecha_procesada():
    fechas = [r["fecha"] for r in leer()]
    return date.fromisoformat(max(fechas)) if fechas else None