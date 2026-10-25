"""Reconoce, por el nombre, qué producto cotidiano es cada pesable ("Banana", "Asado", "Pollo entero"...).

Para el bloque "Precio por kilo" del sitio. No usa el rubro: el rubro actual se equivoca con los frescos
(el tomate figura como "conservas") y deja sin rubro frutas y verduras. Cada producto tiene una regla de
inclusión (el nombre empieza con...) y de exclusión (preparados, congelados, premium, envases chicos).

Entrada: pesables_para_clasificar.csv (scripts.medir_pesables --exportar). Solo lee, salvo con --guardar,
que escribe seeds/pesables_producto.csv (id_comercio, id_producto, producto, grupo, factor_kg).

Uso: python -m scripts.clasificar_pesables [--guardar] [--muestra N]
"""
import argparse
import csv
import re
import statistics
import unicodedata
from collections import defaultdict
from pathlib import Path

from ingesta import config

# Lo que no es el producto crudo, común a todos: premium, congelado, preparado, envases chicos
EXCLUIR = re.compile(
    r"ETIQUETA NEGRA|SIGNIA|HUELLA NAT|GUANACO|\bABC\b|CONGEL|DESCONG|REBOZ|EMPANAD|TARTA|PIZZA|SANDWICH|PURE|ORGANIC"
    r"|DESECAD|DESHIDRAT|COCIDA|AHUMAD|\bCONG\b|CONG\.|CUBETA|ATADO|\bPAQ\b|PAQUETE|\bUNI\b|UNID|\bX ?\d+ ?(GRS?|G)\b|\bLAT\b|BJA|ENSALADA"
    r"|\bCHIP\b|\bSC\b|BANDERITA|MARQUESA|TRENZA|BRISSE|PASTA ?FROLA|PASTEL")

# (producto, grupo, empieza con / contiene (regex sobre el nombre en mayúsculas y sin tildes), excluir)
PRODUCTOS = [
    # Verduras
    ("Papa", "Verduras", r"^PAPA\b", r"MINI|FRIT|PAPAYA|PAPIN|PAPAS"),
    ("Batata", "Verduras", r"^(BATATA|BONIATO)\b", r"D BATATA|DULCE"),
    ("Cebolla", "Verduras", r"^CEBOLLA\b", r"VERDEO|MORADA|ROJA|ESCAMAS|CEBOLLITAS"),
    ("Zanahoria", "Verduras", r"^ZANAHORIA\b", r"RALLAD|TROZ"),
    ("Tomate redondo", "Verduras", r"^TOMATE (RED|REDONDO|LARGA VIDA|LVIDA|EN RACIMO|RACIMO|PROMOCION)\b", r"CHERRY|CHERRI"),
    ("Tomate perita", "Verduras", r"^TOMATE PERITA\b", r"PELADO|CUBETEADO|COTO|ENVAS"),
    ("Lechuga", "Verduras", r"^LECHUGA\b", r"MIX|HIDROPONICA"),
    ("Zapallo anco", "Verduras", r"^ZAPALLO ANCO\b", r"RODAJAS"),
    ("Zapallito", "Verduras", r"^ZAPALLITO\b", r""),
    ("Brócoli", "Verduras", r"^BROCOLI\b", r""),
    ("Berenjena", "Verduras", r"^BERENJENAS?\b", r""),
    ("Morrón rojo", "Verduras", r"^(PIMIENTO|MORRON) ROJO\b", r"MIX"),
    ("Morrón verde", "Verduras", r"^(PIMIENTO|MORRON) VERDE\b", r"MIX"),
    ("Pepino", "Verduras", r"^PEPINOS?\b", r"ENTEROS"),
    ("Chaucha", "Verduras", r"^CHAUCHA\b", r""),
    ("Acelga", "Verduras", r"^ACELGA\b", r""),
    ("Coliflor", "Verduras", r"^COLIFLOR( X KG| BLANCA|,|$)", r"MORADO"),
    ("Repollo blanco", "Verduras", r"^REPOLLO BLANCO\b", r""),
    # Frutas
    ("Banana", "Frutas", r"^BANANA\b", r"PLATANO|X 500|X UNI"),
    ("Manzana roja", "Frutas", r"^MANZANA\b", r"GRANNY|GRANY|G\.? ?SMITH|VERDE|X 500"),
    ("Manzana verde", "Frutas", r"^MANZANA\b.*(GRANNY|GRANY|G\.? ?SMITH|VERDE)", r"X 500"),
    ("Naranja", "Frutas", r"^NARANJA\b", r"SANGUINEA|X 500|X UNI"),
    ("Mandarina", "Frutas", r"^MANDARINA\b", r""),
    ("Limón", "Frutas", r"^LIMON\b", r"CAIPIRINHA|X UNI"),
    ("Pera", "Frutas", r"^PERA\b", r"ASIATICA"),
    ("Palta", "Frutas", r"^PALTA\b", r"X UNI|MIXTO"),
    ("Frutilla", "Frutas", r"^FRUTILLA", r"BURBUJAS|CUBETA"),
    ("Sandía", "Frutas", r"^SANDIA\b", r"MINI"),
    # Carne vacuna
    ("Asado", "Carne vacuna", r"^ASADO\b", r"RUSO|DE BIFE|VENTANA|COLITA|PLANCHA|CARNICERO BANDEJA|CRIOLLO"),
    ("Bife de chorizo", "Carne vacuna", r"^BIFE DE CHORIZO\b", r"PORCION"),
    ("Bife ancho", "Carne vacuna", r"^BIFE ANCHO\b", r""),
    ("Matambre", "Carne vacuna", r"^MATAMBRE\b", r"ARROLLADO|DESCO"),
    ("Carne picada especial", "Carne vacuna", r"^PICADA (ESPECIAL|DESGRASADA)", r""),
    ("Vacío", "Carne vacuna", r"^VACIO\b", r"ENSALADA|HORNO|CERDO|POLLO|CON "),
    ("Carne picada común", "Carne vacuna",
     r"^(CARNE )?PICADA\b(?!.*(ESPECIAL|MAGRA|DESGRAS|TARTARE|VARIADA|CERDO|MIXTA|GRASA|FIAM|GOURMET|PREMIUM))", r""),
    ("Nalga", "Carne vacuna", r"^NALGA\b", r"FET|TAPA|CTO PUL"),
    ("Cuadril", "Carne vacuna", r"^CUADRIL\b", r"CHURRASCO|COLITA"),
    ("Peceto", "Carne vacuna", r"^PECETO\b", r"CAZADORA|DEMIGLASE|COMIDA|FET"),
    ("Bola de lomo", "Carne vacuna", r"^BOLA DE LOMO\b", r"FET"),
    ("Roast beef", "Carne vacuna", r"^ROAST BEEF\b", r"CHURRASCO"),
    ("Paleta", "Carne vacuna", r"^PALETA\b", r"CERDO|CHURRASCO|COCID"),
    ("Osobuco", "Carne vacuna", r"^OSOBUCO\b", r"EMPANADA"),
    ("Falda", "Carne vacuna", r"^FALDA\b", r"CERDO"),
    ("Milanesa de nalga", "Carne vacuna", r"^(UG )?MILANESA (DE )?NALGA\b", r"EMPANADA"),
    # Pollo
    ("Pollo entero", "Pollo", r"^POLLO (ENTERO|FRESCO|PARRILLERO|REFRIGERADO|ESPREFRIGERADO|A 01|A \(COMUN|DEL ABUELO|VERD CON)",
     r"ROSTIZADO|SPIEDO|PORTUGUESA|VERDEO|PAPA|ENS\b|WRAP|MILA|MENUDOS"),
    ("Pechuga de pollo", "Pollo", r"^(FILET DE )?PECHUGAS?\b", r"PAVO|VACIO|REBOZ"),
    ("Pata muslo y muslo", "Pollo", r"^(PATA ?MUSLO|MUSLOS?)\b", r"VACIO|PAPAS|CHEDDAR|MUSLITOS"),
    # Cerdo y embutidos
    ("Bondiola de cerdo", "Cerdo", r"^BONDIOLA( DE CERDO)?\b", r"FETEAD|\bFET\b|LARIO|AL |CURADA|CRUDA|SALADA"),
    ("Chuleta de cerdo", "Cerdo", r"^(CHULETAS?|COSTELETAS?) (DE )?(CERDO|PALETA|JAMON)", r""),
    ("Carré de cerdo", "Cerdo", r"^CARRE\b", r"CORDERO|T BONE|CHULETAS|TERCIOS"),
    ("Matambrito de cerdo", "Cerdo", r"^MATAMBRITO (DE )?CERDO", r""),
    ("Chorizo", "Cerdo", r"^CHORIZO\b", r"COPETIN|SECO|ESPANOL|COLORADO|ORIENTAL|BB|COCIDO"),
    ("Morcilla", "Cerdo", r"^MORCILLA\b", r"DULCE|VASCA|ESPANOLA"),
    ("Salchicha parrillera", "Cerdo", r"^SALCHICHA PARRILLERA", r""),
    # Fiambres y quesos
    ("Jamón cocido", "Fiambres y quesos", r"^(JAMON|JAM N|J)( D)? COCIDO\b", r"FIAMBRE|SANDWICH"),
    ("Jamón crudo", "Fiambres y quesos", r"^(JAMON|JAM N|J)( D)? CRUDO\b", r""),
    ("Mortadela", "Fiambres y quesos", r"^MORTADELA\b", r"PISTACHO"),
    ("Salame", "Fiambres y quesos", r"^SALAME\b|\bSALAM\b", r"MILAN.*PICADO"),
    ("Queso cremoso", "Fiambres y quesos", r"^QUESO CREMOSO\b", r"LIGHT|DESLACT|CREMON"),
    ("Queso port salut", "Fiambres y quesos", r"^(QUESO )?PORT( SALUT)?\b", r"LIGHT"),
    ("Queso pategrás", "Fiambres y quesos", r"^QUESO PATEGR", r"LIGHT"),
    ("Queso mozzarella", "Fiambres y quesos", r"^QUESO (MOZZARELLA|MUZZARELLA|MUZARELLA)\b", r"RALL"),
    ("Queso sardo", "Fiambres y quesos", r"^(QUESO )?SARDO\b", r""),
    ("Queso reggianito", "Fiambres y quesos", r"^(QUESO )?REGGIANITO\b", r"RALL"),
    # Pescado
    ("Filet de merluza", "Pescado", r"^(FILET|FILETE|FILER)( DE| D/)? ?MERLUZA|^MERLUZA", r"MEDALLON|MILANESA|BASTON|ENTERA|QIESO|QUESO"),
    ("Salmón rosado", "Pescado", r"^(FILET DE )?SALM[ON ]+ROSADO|^SALM[ON]+ ROSADO|^FILET( DE)? SALM", r""),
]
# Cerdo, cordero y pavo no son carne vacuna ni pollo aunque el corte se llame igual ("nalga de cerdo")
OTRA_CARNE = re.compile(r"CERDO|CORDERO|\bCORD\b|PAVO|CAPON|LECHON")
GRUPOS_SOLO_SU_CARNE = {"Carne vacuna", "Pollo"}

# Un nombre con peso ("QUESO PAQ 250 GRM", "X 500 GRS") es un envase: su precio por kilo sale del precio de
# referencia. Sin peso (o "X KG", "1 KGR") se vende al peso y el precio de lista ya es el del kilo. Se prefiere
# el precio de lista porque el de referencia de algunos productos de Carrefour viene dividido por 10
# (una bondiola de $ 20.500 el kilo figura a $ 2.050).
PESO_EN_NOMBRE = re.compile(r"\b(\d+(?:[.,]\d+)?) ?(KGS?|KGM|KGR|GRS?|GRM|G)\b")


def vendido_al_peso(nombre):
    for m in PESO_EN_NOMBRE.finditer(normalizar(nombre)):
        if m.group(2).startswith("KG") and float(m.group(1).replace(",", ".")) == 1:
            continue
        return False
    return True


def precio_kilo(fila):
    """Precio por kilo de una fila del CSV, o None si no se puede pasar a kilo (viene por unidad, litro...)."""
    if not fila["precio_kg"]:
        return None
    if vendido_al_peso(fila["nombre"]) and fila["precio_lista"]:
        return float(fila["precio_lista"])
    return float(fila["precio_kg"])


# El precio por kilo de DIA en la carne vacuna no es creíble: SEPA informa el asado al vacío a $ 6.990 y en la
# web de DIA cuesta entre $ 18.500 y $ 19.300 el kilo (verificado el 24/10/2026). Se excluye hasta entender por qué.
NO_CREIBLE = {("15", "Carne vacuna")}

# Productos que algunas cadenas venden por pieza de peso conocido: precio por kilo = precio de la pieza / peso.
# Pollo entero de Changomas: la pieza pesa 2,7 kg (así figura en la web: "Pollo entero fresco 2,700 kg").
PESO_PIEZA_KG = {("11", "Pollo entero"): 2.7}

COMPILADOS = [(n, g, re.compile(i), re.compile(e) if e else None) for n, g, i, e in PRODUCTOS]


# Exclusiones por producto que valen tanto para las reglas como para el veto a DeepSeek: son variantes con otro
# precio que el producto común (el asado de tira no es la tapa de asado; un queso light o sin lactosa no es el común)
_QUESO_ESPECIAL = re.compile(r"LIGH?T|LIGTH|LITE\b|REDUCID|SIN LACTOSA|\bS/? ?LACTOSA|SIN SAL\b|BAJO EN")
EXTRA_EXCLUIR = {"Asado": re.compile(r"TAPA DE ASADO"),
                 "Pechuga de pollo": re.compile(r"SUPREMA"),
                 "Carré de cerdo": re.compile(r"DESH|SIN HUESO"),        # a $ 19.999 el kilo: es la milanesa de pollo, no la pechuga
                 "Salmón rosado": re.compile(r"EVISCERAD"),
                 # sin color en el nombre ("PIMIENTO MORRON X KG") no se sabe cuál es: no es el rojo ni el verde
                 "Morrón rojo": re.compile(r"^(?!.*\bROJO\b)"),
                 "Morrón verde": re.compile(r"^(?!.*\bVERDE\b)")}       
EXTRA_EXCLUIR.update({n: _QUESO_ESPECIAL for n, g, *_ in PRODUCTOS if n.startswith("Queso ")})


def normalizar(texto):
    sin_tildes = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn").upper().strip()


def vetado(nombre, producto):
    """True si el nombre cae en una exclusión de las reglas (congelado, premium, envase chico, por unidad,
    corte de cerdo...) o en las del propio producto ("COLORADO" para el chorizo). Se usa para controlar a
    DeepSeek: él propone la etiqueta y estas exclusiones la pueden anular."""
    n = normalizar(nombre)
    if EXCLUIR.search(n):
        return True
    if producto in EXTRA_EXCLUIR and EXTRA_EXCLUIR[producto].search(n):
        return True
    for nombre_producto, grupo, _, excluir in COMPILADOS:
        if nombre_producto != producto:
            continue
        if grupo in GRUPOS_SOLO_SU_CARNE and OTRA_CARNE.search(n):
            return True
        return bool(excluir and excluir.search(n))
    return False


def producto_de(nombre):
    """El producto cotidiano al que corresponde el nombre, o None. Gana el primero que coincide."""
    n = normalizar(nombre)
    if EXCLUIR.search(n):
        return None
    for producto, grupo, incluir, excluir in COMPILADOS:
        if grupo in GRUPOS_SOLO_SU_CARNE and OTRA_CARNE.search(n):
            continue
        if producto in EXTRA_EXCLUIR and EXTRA_EXCLUIR[producto].search(n):
            continue
        if incluir.search(n) and not (excluir and excluir.search(n)):
            return producto, grupo
    return None


def main():
    argumentos = argparse.ArgumentParser(description="Reconoce pesables cotidianos por el nombre")
    argumentos.add_argument("--guardar", action="store_true", help="escribe seeds/pesables_producto.csv")
    argumentos.add_argument("--con-deepseek", action="store_true",
                            help="donde las reglas no reconocen nada, usa la etiqueta de pesables_etiquetas_llm.csv (ya con vetos)")
    argumentos.add_argument("--muestra", type=int, default=4, help="nombres de ejemplo por producto")
    a = argumentos.parse_args()

    filas = list(csv.DictReader((config.DATOS_DIR / "pesables_para_clasificar.csv").open(encoding="utf-8")))
    cadenas = {"10": "Carrefour", "12": "Coto", "11": "Changomas", "15": "DIA", "2": "La Anónima", "9": "Cencosud"}
    orden = ["10", "12", "11", "15", "2", "9"]
    grupo_del_producto = {n: g for n, g, *_ in PRODUCTOS}
    etiquetas_llm = {}
    if a.con_deepseek:
        ruta = config.DATOS_DIR / "pesables_etiquetas_llm.csv"
        etiquetas_llm = {(e["id_comercio"], e["id_producto"]): e["producto_llm"] for e in csv.DictReader(ruta.open(encoding="utf-8"))}
        if len(etiquetas_llm) < len(filas):
            raise SystemExit(f"pesables_etiquetas_llm.csv tiene {len(etiquetas_llm):,} etiquetas y hay {len(filas):,} pesables: "
                             "corré python -m scripts.etiquetar_pesables_llm sin --muestra")

    def reconocer(f):
        r = producto_de(f["nombre"])
        if r or not a.con_deepseek:
            return r
        llm = etiquetas_llm.get((f["id_comercio"], f["id_producto"]))
        return (llm, grupo_del_producto[llm]) if llm in grupo_del_producto else None

    por = defaultdict(lambda: defaultdict(list))   # producto -> cadena -> precios por kilo
    nombres = defaultdict(list)
    grupo_de, reconocidos, con_precio = {}, [], []
    for f in filas:
        r = reconocer(f)
        if not r:
            continue
        producto, grupo = r
        grupo_de[producto] = grupo
        reconocidos.append((f["id_comercio"], f["id_producto"], producto))
        nombres[producto].append(f"{f['nombre'][:34]} ({cadenas.get(f['id_comercio'], f['id_comercio'])[:3]})")
        kilo = precio_kilo(f)
        pieza = PESO_PIEZA_KG.get((f["id_comercio"], producto))
        if kilo is None and pieza and f["precio_lista"]:
            kilo = round(float(f["precio_lista"]) / pieza)
        if (f["id_comercio"], grupo) in NO_CREIBLE:
            kilo = None
        if kilo:
            con_precio.append((producto, f["id_comercio"], f["nombre"], kilo, f["id_producto"], float(f["precio_lista"])))
    # Guarda: un precio a menos de un cuarto o a más de cuatro veces la mediana del producto en todas las
    # cadenas es un error de carga o un producto que no es el mismo (chorizo a $ 274 el kilo)
    mediana = {p: statistics.median(x[3] for x in con_precio if x[0] == p) for p in {x[0] for x in con_precio}}
    descartados, para_seed = [], []
    for producto, cadena, nombre, kilo, id_producto, lista in con_precio:
        if not mediana[producto] / 4 <= kilo <= mediana[producto] * 4:
            descartados.append(f"{nombre[:36]} ({cadenas.get(cadena, cadena)[:3]}) {kilo:,.0f} vs {mediana[producto]:,.0f}")
        else:
            por[producto][cadena].append(kilo)
            # factor_kg: por cuánto se multiplica el precio de lista de este producto para tener el del kilo
            # (1 si ya viene por kilo; 4 si es un envase de 250 g; 1/2,7 si es una pieza de 2,7 kg)
            if lista > 0:
                para_seed.append((cadena, id_producto, producto, grupo_de[producto], round(kilo / lista, 6)))

    print(f"{len(reconocidos):,} de {len(filas):,} pesables reconocidos como {len(grupo_de)} productos")
    print(f"{len(descartados)} precios descartados por la guarda: " + " | ".join(descartados[:12]) + "\n")
    print(f"{'producto':<22}" + "".join(f"{cadenas[c][:9]:>12}" for c in orden))
    print(f"{'':<22}" + "".join(f"{'mediana (n)':>12}" for _ in orden))
    grupo_actual = None
    for producto, grupo, _, _ in COMPILADOS:
        if producto not in grupo_de:
            print(f"{producto:<22}  (ningún pesable)")
            continue
        if grupo != grupo_actual:
            grupo_actual = grupo
            print(f"-- {grupo}")
        celdas = []
        medianas = {c: statistics.median(por[producto][c]) for c in orden if por[producto].get(c)}
        for c in orden:
            v = por[producto].get(c)
            otras = [m for k, m in medianas.items() if k != c]
            raro = bool(v) and len(otras) >= 2 and not 0.55 <= medianas[c] / statistics.median(otras) <= 1.8
            celdas.append(f"{statistics.median(v):>7,.0f}{'?' if raro else ' '} ({len(v)})" if v else f"{'—':>12}")
        print(f"{producto:<22}" + "".join(f"{x:>12}" for x in celdas))
    print()
    for producto in grupo_de:
        print(f"{producto}: " + " | ".join(nombres[producto][:a.muestra]))

    if a.guardar:
        destino = Path(__file__).resolve().parent.parent / "seeds" / "pesables_producto.csv"
        with destino.open("w", encoding="utf-8", newline="") as salida:
            w = csv.writer(salida)
            w.writerow(["id_comercio", "id_producto", "producto", "grupo", "factor_kg"])
            w.writerows(sorted(para_seed))
        print(f"\nGuardé {len(para_seed):,} productos con precio por kilo en {destino}")


if __name__ == "__main__":
    main()
