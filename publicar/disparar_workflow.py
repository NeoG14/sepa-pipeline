"""Dispara en GitHub el workflow que publica el sitio (publicar.yml).

Se llama al final de la corrida diaria, después de subir los marts a MotherDuck. Si el disparo falla,
no rompe la ingesta: el sitio queda con los datos del día anterior y el log lo avisa.

El token se lee de la variable de entorno SEPA_GITHUB_TOKEN: nunca va en el código. Es un token de
GitHub de alcance mínimo: solo este repositorio y solo el permiso "Actions: Read and write".

Uso: python -m publicar.disparar_workflow
"""
import logging
import os
import sys

import requests

REPO = "NeoG14/sepa-pipeline"
WORKFLOW = "publicar.yml"
RAMA = "main"

log = logging.getLogger("ingesta")


def disparar():
    """Pide a GitHub que corra el workflow. Devuelve True si GitHub lo aceptó."""
    token = os.environ.get("SEPA_GITHUB_TOKEN")
    if not token:
        log.error("Falta la variable de entorno SEPA_GITHUB_TOKEN: no se publica el sitio")
        return False
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    cabeceras = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        respuesta = requests.post(url, headers=cabeceras, json={"ref": RAMA}, timeout=30)
    except requests.RequestException as error:
        log.error(f"No se pudo llamar a GitHub: {type(error).__name__}")
        return False
    if respuesta.status_code == 204:
        log.info(f"Workflow {WORKFLOW} disparado en GitHub: el sitio se publica en unos minutos")
        return True
    log.error(f"GitHub rechazó el disparo: HTTP {respuesta.status_code} {respuesta.text[:200]}")
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(0 if disparar() else 1)
