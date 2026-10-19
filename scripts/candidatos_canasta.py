"""Arma la lista de candidatos para la canasta y la guarda en un CSV para revisar a mano.

Candidato: EAN comparable que está en al menos 6 cadenas, y en cada una de ellas aparece todos
los días analizados salvo como mucho MAX_DIAS_FALTANTES (una cadena puede perder un día entero de
datos, como DIA el 13/10, sin que eso signifique que dejó de vender el producto).
Le agrega un rubro SUGERIDO (solo para ordenar la revisión: hay que mirarlo, no confiar en él),
las descripciones de cada cadena, la cadena que falta, las que tienen algún día sin informarlo y la
mediana nacional del precio de lista en la última fecha.

El rubro se decide por votación: cada cadena describe el producto a su manera, se clasifica
cada descripción con las reglas de scripts/rubros.py y gana el rubro con más votos (si empatan,
el de la regla que va primero). La columna "acuerdo" dice cuántas descripciones lo votaron.

Uso: python -m scripts.candidatos_canasta
Salida: <SEPA_DATOS_DIR>/canasta_candidatos.csv  (separado por ; para abrir en Excel)
"""
import csv

import duckdb

from ingesta import config
from scripts.rubros import RUBROS, SIN_AZUCAR

base = config.PARQUET_LOCAL_DIR.as_posix()
SALIDA = config.DATOS_DIR / "canasta_candidatos.csv"
MIN_CADENAS = 6
MAX_DIAS_FALTANTES = 1  # mismo criterio que scripts/verificar_canasta.py

con = duckdb.connect()
con.execute(f"""
    CREATE TABLE presencia AS
    SELECT DISTINCT ltrim(p.id_producto, '0') AS ean, p.id_comercio, s.provincia, p.fecha
    FROM read_parquet('{base}/fecha=*/precios.parquet') p
    JOIN read_parquet('{base}/fecha=*/sucursales.parquet') s
      ON s.fecha = p.fecha AND s.id_comercio = p.id_comercio
     AND s.id_bandera = p.id_bandera AND s.id_sucursal = p.id_sucursal
    WHERE s.provincia IS NOT NULL AND coalesce(s.sucursales_tipo, '') <> 'Web'
      AND p.precio_lista IS NOT NULL
      AND regexp_full_match(p.id_producto, '\\d+')
      AND length(ltrim(p.id_producto, '0')) >= 8
      AND NOT (length(p.id_producto) = 13 AND p.id_producto LIKE '2%')
""")
total_fechas = con.execute("SELECT count(DISTINCT fecha) FROM presencia").fetchone()[0]
ultima = con.execute("SELECT max(fecha) FROM presencia").fetchone()[0]
minimo_dias = total_fechas - MAX_DIAS_FALTANTES

con.execute(f"""
    CREATE TABLE candidatos AS
    WITH por_cadena AS (
        SELECT ean, id_comercio, count(DISTINCT fecha) AS dias FROM presencia GROUP BY ALL
    )
    SELECT ean,
           count(*) FILTER (WHERE dias >= {minimo_dias}) AS cadenas,
           list(id_comercio) FILTER (WHERE dias >= {minimo_dias}) AS completas,
           list(id_comercio) FILTER (WHERE dias >= {minimo_dias} AND dias < {total_fechas}) AS con_faltantes
    FROM por_cadena GROUP BY ean
    HAVING count(*) FILTER (WHERE dias >= {minimo_dias}) >= {MIN_CADENAS}
""")

# Una descripción por cadena, clasificada con las reglas (i = número de la regla que coincidió)
con.execute("CREATE TABLE reglas(i INTEGER, rubro VARCHAR)")
con.executemany("INSERT INTO reglas VALUES (?, ?)", [(i, rubro) for i, (rubro, _) in enumerate(RUBROS)])
caso = " ".join(f"WHEN regexp_matches(texto, '{patron}') THEN {i}" for i, (_, patron) in enumerate(RUBROS))
con.execute(f"""
    CREATE TABLE descripciones AS
    WITH d AS (
        SELECT ltrim(id_producto, '0') AS ean, id_comercio, descripcion, marca,
               regexp_replace(upper(strip_accents(coalesce(descripcion, ''))), '{SIN_AZUCAR}', ' ', 'g') AS texto
        FROM read_parquet('{base}/fecha={ultima}/productos.parquet')
        WHERE ltrim(id_producto, '0') IN (SELECT ean FROM candidatos)
    )
    SELECT ean, id_comercio, descripcion, marca, CASE {caso} END AS i FROM d
""")
con.execute("""
    CREATE TABLE rubro_elegido AS
    WITH votos AS (
        SELECT d.ean, r.rubro, count(*) AS votos, min(d.i) AS orden
        FROM descripciones d JOIN reglas r USING (i) GROUP BY ALL
    ),
    ranking AS (
        SELECT *, row_number() OVER (PARTITION BY ean ORDER BY votos DESC, orden) AS puesto FROM votos
    )
    SELECT ean, rubro, votos FROM ranking WHERE puesto = 1
""")

filas = con.execute(f"""
    WITH provincias AS (SELECT ean, count(DISTINCT provincia) AS provincias FROM presencia GROUP BY ean),
    textos AS (
        SELECT ean, mode(marca) AS marca, count(*) AS total,
               string_agg(DISTINCT descripcion, ' | ') AS descripciones
        FROM descripciones GROUP BY ean
    ),
    precio AS (
        SELECT ltrim(id_producto, '0') AS ean, median(precio_lista) AS mediana
        FROM read_parquet('{base}/fecha={ultima}/precios.parquet')
        WHERE precio_lista IS NOT NULL GROUP BY 1
    )
    SELECT c.ean, coalesce(r.rubro, '') AS rubro,
           CASE WHEN r.votos IS NULL THEN '' ELSE r.votos || '/' || t.total END AS acuerdo,
           c.cadenas, pr.provincias, c.completas, c.con_faltantes, t.marca, p.mediana, t.descripciones
    FROM candidatos c
    JOIN provincias pr USING (ean)
    LEFT JOIN rubro_elegido r USING (ean)
    LEFT JOIN textos t USING (ean)
    LEFT JOIN precio p USING (ean)
    ORDER BY rubro = '', rubro, c.cadenas DESC, pr.provincias DESC, c.ean
""").fetchall()

with open(SALIDA, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel muestra bien las tildes
    w = csv.writer(f, delimiter=";")
    w.writerow(["ean", "rubro_sugerido", "acuerdo", "cadenas", "provincias",
                "falta_en", "dias_faltantes_en", "marca", "precio_mediana", "descripciones"])
    for ean, rubro, acuerdo, cadenas, provincias, completas, con_faltantes, marca, mediana, descripciones in filas:
        falta = ",".join(str(c) for c in config.COMERCIOS if str(c) not in completas)
        precio = f"{mediana:.2f}".replace(".", ",") if mediana is not None else ""
        w.writerow([ean, rubro, acuerdo, cadenas, provincias, falta, ",".join(con_faltantes or []),
                    marca, precio, descripciones])

print(f"Fechas analizadas: {total_fechas} | última: {ultima}")
print(f"Candidatos (al menos {MIN_CADENAS} cadenas, cada una con {minimo_dias} de {total_fechas} días "
      f"o más): {len(filas):,}\n")
print(f"{'rubro sugerido':<28}{'7 cadenas':>11}{'(con días faltantes)':>22}{'6 cadenas':>11}")
conteo = {}
for _, rubro, _, cadenas, _, _, con_faltantes, *_ in filas:
    fila = conteo.setdefault(rubro or '(sin rubro)', [0, 0, 0])
    if cadenas == 7:
        fila[0] += 1
        fila[1] += 1 if con_faltantes else 0
    else:
        fila[2] += 1
for rubro, (siete, faltantes, seis) in sorted(conteo.items(), key=lambda x: (x[0] == '(sin rubro)', x[0])):
    print(f"{rubro:<28}{siete:>11,}{faltantes:>22,}{seis:>11,}")
totales = [sum(f[i] for f in conteo.values()) for i in range(3)]
print(f"{'total':<28}{totales[0]:>11,}{totales[1]:>22,}{totales[2]:>11,}")
print(f"\nGuardado en: {SALIDA}")