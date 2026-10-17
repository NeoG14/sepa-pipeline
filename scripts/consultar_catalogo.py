"""Etapa 0, paso 2: consulta el catálogo CKAN del portal y lista los
recursos (archivos) del dataset SEPA. No descarga nada."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get(
    "SEPA_API_URL",
    "https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios",
)
INTENTOS = 4
TIMEOUT_SEG = 30
USER_AGENT = "sepa-pipeline-portfolio/0.1 (github.com/NeoG14/sepa-pipeline)"


def consultar(url):
    """GET con tiempo límite y reintentos con espera creciente."""
    for intento in range(1, INTENTOS + 1):
        inicio = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEG) as resp:
                cuerpo = resp.read()
                print(f"intento {intento}: HTTP {resp.status} en "
                      f"{time.time() - inicio:.1f}s, {len(cuerpo)} bytes")
                return json.loads(cuerpo)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"intento {intento}: falló tras {time.time() - inicio:.1f}s -> {e!r}")
            if intento < INTENTOS:
                espera = 5 * 2 ** (intento - 1)
                print(f"  reintento en {espera}s")
                time.sleep(espera)
    return None


def main():
    print(f"Consultando: {URL}")
    data = consultar(URL)
    if data is None:
        print("ERROR: no se pudo consultar el catálogo")
        sys.exit(1)
    if not data.get("success"):
        print("ERROR: la respuesta no trae success=true")
        print(json.dumps(data)[:500])
        sys.exit(1)

    pkg = data["result"]
    print(f"Título: {pkg.get('title')}")
    print(f"Licencia: {pkg.get('license_id')} / {pkg.get('license_title')}")
    print(f"Metadata modificada: {pkg.get('metadata_modified')}")

    recursos = pkg.get("resources", [])
    print(f"Recursos: {len(recursos)}")
    for r in recursos:
        print("-" * 60)
        print(f"nombre:        {r.get('name')}")
        print(f"formato:       {r.get('format')}")
        print(f"tamaño (B):    {r.get('size')}")
        print(f"modificado:    {r.get('last_modified')}")
        print(f"url:           {r.get('url')}")


if __name__ == "__main__":
    main()