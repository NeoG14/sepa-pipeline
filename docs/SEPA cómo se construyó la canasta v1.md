# SEPA: cómo se construyó la canasta v1

Oct 19, 2026 · @Nicolas

## Resumen en 30 segundos

La canasta v1 son **31 productos envasados**, identificados por su código de barras (EAN), que venden las **7 cadenas** grandes que informan a SEPA en las **24 provincias**. Sirve para comparar precios entre cadenas y a lo largo del tiempo usando exactamente el mismo producto.

- **El 19/10/2026 cuesta entre $101.728 (Cencosud) y $105.465 (La Anónima)**, sumando la mediana nacional de cada producto: la más cara es un 3,7 % más cara que la más barata.
- **Salió de 8 días de datos** (12/10 al 19/10), unos 14 millones de precios por día.
- **Cubre cinco grupos:** almacén (12 productos), lácteos (5), bebidas (3), otros alimentos (3) y limpieza e higiene (8).
- **Herramientas:** Python y DuckDB sobre archivos Parquet. Cada número de este documento sale de una consulta, no de una estimación.

## El problema: por qué una lista fija de códigos

Para comparar precios hay que comparar el mismo producto. Por eso la canasta es una lista fija de EAN y no un promedio de todo lo que vende cada cadena.

- **Un promedio de todo mezcla surtidos.** Si una cadena vende más productos premium, su promedio sube aunque no sea más cara.
- **El EAN identifica el producto exacto:** marca, variedad y tamaño. Es el mismo código en todas las cadenas, así que su precio en DIA y en Coto se puede comparar directamente.
- **La alternativa era comparar por categoría**, por ejemplo "leche entera 1 L, cualquier marca". Se parece más a lo que compra la gente, pero SEPA no trae una columna de categoría: hay que clasificar texto libre y medir el error. La dejé como una fase 2 aparte, para no frenar el pipeline.
- **La lista se guarda como un seed de dbt:** `seeds/canasta.csv`, versionado en git y con una columna `version`. Así la selección queda documentada y se puede reproducir. Si un producto cambia de código, se publica una v2 sin romper la serie.

## Los datos de partida

SEPA es un dataset abierto donde los supermercados informan cada día el precio de cada producto en cada sucursal. Mi pipeline lo descarga todos los días desde la PC, lo valida y lo guarda en Parquet, particionado por fecha.

- **Cadenas:** me quedé con las 7 grandes, que suman alrededor del 99 % de las filas. Son DIA (id 15), Carrefour (10), Changomas (11), Cencosud (9), Coto (12), La Anónima (2) y Coop. Obrera (13). Los números son los id que usa SEPA y los que muestran las salidas de los scripts.
- **Volumen:** unos 14 millones de filas por día. En Parquet ocupan unos 70 MB por día, contra 1.506 MB en CSV: 21 veces menos.
- **Ventana analizada:** 8 fechas, del 12/10 al 19/10/2026.
- **Herramienta:** DuckDB, que consulta los Parquet con SQL directamente desde Python, sin cargarlos en una base de datos.

Todo el análisis de la canasta usa solo sucursales físicas con provincia informada. Las tiendas online (`sucursales_tipo = 'Web'`) quedan afuera, porque no tienen una ubicación comparable.

## Paso 1: qué códigos se pueden comparar

No todos los códigos de SEPA son EAN reales. Para unir el mismo producto entre cadenas definí una regla de tres partes:

1. **Se quitan los ceros de la izquierda.** Una cadena puede informar el mismo producto con un cero de más adelante; sin los ceros, los dos códigos quedan iguales.
2. **Tiene que tener 8 dígitos o más.** El EAN más corto, el EAN-8, tiene 8. Los códigos más cortos son internos de cada cadena.
3. **No puede ser un código de 13 dígitos que empieza con 2.** Ese rango está reservado para uso interno, como los productos que se pesan en la sucursal, y cada cadena lo usa a su manera.

En SQL queda así:

```sql
WHERE regexp_full_match(id_producto, '\d+')
  AND length(ltrim(id_producto, '0')) >= 8
  AND NOT (length(id_producto) = 13 AND id_producto LIKE '2%')
```

Con esta regla, el 66,9 % de las filas son de códigos comparables que aparecen en al menos 2 cadenas. Antes de usarla con datos reales la probé con datos inventados: un EAN con un cero de más, un código interno que empieza con 2, un código corto y un producto al que le falta un día. Los cuatro casos dieron lo esperado.

## Paso 2: medir qué productos están en todas las cadenas

De 66.657 códigos comparables, solo **560 estaban en las 7 cadenas los 8 días**: menos del 1 %. Lo medí antes de elegir nada, con un script (`medir_canasta.py`) que cuenta, para cada EAN, en cuántas cadenas aparece todos los días, en cuántas provincias y qué cadena falta en los que casi llegan.

- **La mayoría es de una sola cadena:** 45.901 códigos aparecen todos los días en una sola cadena.
- **Lo que está en muchas cadenas llega a todo el país:** de los 2.115 EAN presentes en 6 cadenas o más, 2.019 están en las 24 provincias.
- **La cadena que más falta es DIA, no las regionales.** La hipótesis era que faltarían La Anónima y Coop. Obrera, que operan en pocas provincias. La medición mostró otra cosa: entre los EAN que están en 6 cadenas, DIA es la que falta en 608 casos, seguida por Changomas (357) y Cencosud (294).
- **Los mejor cubiertos no eran comida.** Los 30 primeros eran cremas Nivea, máquinas Gillette, pasta Colgate, whisky y vodka: marcas multinacionales con el mismo código en todo el país. Para encontrar alimentos básicos había que ordenar los candidatos por rubro.

## Paso 3: clasificar los candidatos por rubro

Para encontrar alimentos entre más de 2.000 candidatos armé un clasificador de reglas: 67 patrones de texto escritos a mano que asignan 62 rubros, más una votación entre cadenas. No es machine learning: nada se aprende de los datos.

1. **Normalizar el texto.** Cada descripción pasa a mayúsculas y sin tildes, y se borran frases como "sin azúcar" o "menos azúcares". Así la palabra "azúcar" no manda una gaseosa al rubro azúcar.
2. **Lista de decisión.** Cada regla es un rubro con una expresión regular. Se prueban en orden y gana la primera que coincide; en SQL es un `CASE WHEN`. El orden es la clave: lo que no es comida va primero, y lo específico antes que lo general ("dulce de leche" antes que "leche").
3. **Votación entre cadenas.** Cada cadena describe el mismo EAN a su manera. Cada descripción vota un rubro, gana el más votado y la columna `acuerdo` (por ejemplo, 7/7) dice cuántas coincidieron. Una descripción rara no arruina la clasificación.

La primera versión tenía errores que encontré revisando el resultado a mano:

| Error | Causa | Corrección |
| --- | --- | --- |
| Shampoo y cremas corporales en "aceite" | Dicen "aceite de argán" o "aceite de coco" | Las reglas de cuidado personal van antes, y la de aceite pide "aceite de girasol", "de oliva", etc. |
| Arroz Molinos Ala en "limpieza de ropa" | La regla buscaba la marca de jabón ALA | La regla busca "jabón en polvo", "suavizante", etc., no la marca |
| Powerade en "gaseosa" | ISOTONICA contiene TONICA, de "agua tónica" | La regla de isotónicas va antes que la de gaseosas |
| Coca-Cola en "azúcar" | Una cadena la describe "MENOS AZUCARES" | La normalización también borra "menos azúcares" |

**Por qué reglas y no un modelo, por ahora.** No tenía productos etiquetados para entrenar ni para medir un modelo. Para elegir unos 30 productos alcanzaba con ordenar los candidatos y revisarlos a mano. Las reglas tienen límites conocidos: no combinan evidencia (un Kit Kat de oblea cae en galletitas) y, como las escribí mirando estos mismos datos, su acierto no está medido. Por eso la clasificación de verdad quedó para la fase 2, con un conjunto de prueba etiquetado a mano y métricas, comparando reglas contra un modelo supervisado y contra un LLM. Estas reglas van a ser el punto de comparación.

## Paso 4: elegir los productos y verificarlos

Elegí un producto por rubro entre los candidatos presentes en las 7 cadenas, con la presentación típica y una marca masiva. Sumé limpieza e higiene porque también son gasto del hogar. El primer borrador tenía 29 productos.

Para controlarlo escribí `verificar_canasta.py`, que hace cuatro chequeos con consultas:

1. **Presencia:** en cuántas cadenas está cada producto, en cuántas provincias y qué fechas le faltan a cada cadena.
2. **Nombre contra datos:** el nombre que le puse, al lado de la descripción más común en los datos, para detectar un EAN equivocado.
3. **Total por cadena:** la suma de las medianas nacionales de cada producto en la última fecha, con un aviso si a una cadena le falta alguno.
4. **Precios sospechosos:** productos cuyo precio varía más del doble entre cadenas, señal de que alguna informa otra presentación con el mismo código.

Antes de usarlo con datos reales lo probé con datos inventados: un producto al que le falta un día, una cadena con un precio tres veces mayor y productos que no aparecen. El script marcó los tres casos. Y antes de cada corrida anoté qué resultado esperaba: cuando no coincide, hay algo que entender antes de seguir.

## Paso 5: cuestionar el criterio, el caso DIA

El criterio de "todos los días" dejaba afuera productos que DIA sí vende, por un día en que sus datos llegaron incompletos. Lo descubrí porque el borrador no coincidía con lo que veo en las góndolas.

**La sospecha.** El borrador cambiaba la lavandina Ayudín por un limpiador Poett, porque "no estaba en DIA", y la Coca-Cola común por Pepsi. Pero en DIA yo había visto las dos mantecas, la de 100 g y la de 200 g, y la Coca común y la lavandina Ayudín están en cualquier supermercado. Que un producto no aparezca en SEPA no significa que la cadena no lo venda.

**La herramienta.** Escribí `buscar_producto.py`: busca por palabras o por EAN y muestra, cadena por cadena, el código, cuántos días aparece, en cuántas sucursales y a qué precio.

**Lo que encontré:**

- **DIA abrevia todo.** La marca viene como "AYUDI", "SEREN", "LEDES" o "COCA", y la descripción como "GASEO COLA". Buscando "AYUDIN" no aparecía; buscando por EAN, sí.
- **A DIA le faltaba un día.** La lavandina y la manteca de 200 g estaban 7 de 8 días. El día faltante era el 13/10, cuando el archivo de DIA llegó con 421.004 filas menos. Era un problema de datos, no de surtido.
- **La Coca común estaba en las 7 cadenas** los 8 días, pero el clasificador la había mandado a "azúcar" por el "MENOS AZUCARES" de una descripción.

**El cambio.** Ahora una cadena cuenta si le falta como mucho 1 día (`MAX_DIAS_FALTANTES = 1`). Lo validé con consultas, no a ojo:

- **Los EAN en las 7 cadenas pasaron de 560 a 631.** De los 71 nuevos, 70 entraron porque a DIA le faltaba un día y 1 por Coop. Obrera. Eso confirma que la tolerancia cubre la caída de DIA y no un problema general.
- **La verificación muestra la fecha:** la lavandina figura con "15: falta 13/10", justo el día de la caída.
- **Aparecieron rubros nuevos:** dulce de leche pasó de 0 a 4 candidatos en las 7 cadenas.

Con eso la canasta pasó de 29 a 31 productos: la Coca-Cola común reemplazó a Pepsi, y se sumaron la lavandina Ayudín 1 L y el dulce de leche La Serenísima 400 g.

## Decisiones de diseño y su porqué

La regla general fue preferir una comparación honesta con menos productos a una más completa que esconda huecos.

| Decisión | Alternativa descartada | Por qué |
| --- | --- | --- |
| Exigir las 7 cadenas | Aceptar productos en 6 cadenas, lo que sumaba queso y fiambres | Con 6, la cadena que falta cambia según el producto. Una cadena con menos productos parecería más barata, y las salidas (inventar el precio, comparar por pares) esconden datos o complican la comparación |
| Tolerar 1 día faltante por cadena | Exigir los 8 días | Una caída de datos de un día, como la de DIA el 13/10, no significa que el producto dejó de venderse |
| Un solo ítem de gaseosa: Coca-Cola común 2,25 L | Unir Coca y Pepsi, comunes y zero, en un ítem | La canasta mide siempre el mismo producto. Con "la más barata de las dos", el total bajaría por una oferta de Pepsi sin que baje ningún precio; además una es de 2 L y la otra de 2,25 L |
| Azúcar afuera | Sumar Ledesma Superior y Ledesma Clásica como un ítem | Ningún azúcar está en 6 o más cadenas: el que más llega, Ledesma Superior 1 kg, está en 4. Coto y La Anónima no venden Ledesma, y la Superior (refinada) y la Clásica (común) son productos distintos |
| Queso y fiambres afuera | Incluirlos aunque estén en 6 cadenas | Ningún producto llega a las 7: se venden fraccionados y con marcas regionales |
| Dulce de leche clásico La Serenísima 400 g | Colonial, 250 g o 1 kg | 400 g es la presentación más común y la línea clásica es la básica: la Colonial de 400 g cuesta $4.800, contra $4.015 |

Para el azúcar no me quedé con la búsqueda: revisé con una consulta todos los candidatos cuya descripción dice "azúcar". Solo aparecieron productos "sin azúcar" o "azucarados", y un endulzante que se vende como "azúcar light". Agrupar marcas (Coca con Pepsi, todos los azúcares) y comparar por precio por kilo o por litro es justamente el objetivo de la fase 2.

## Resultado: la canasta v1

La canasta v1 tiene 31 productos presentes en las 7 cadenas y en las 24 provincias. La lista, con sus EAN, está en `seeds/canasta.csv`.

&#91;embedded content: medir\_canasta.py y candidatos\_canasta.py · 8 fechas, 12/10 al 19/10/2026\]

Cada paso deja afuera la mayor parte del anterior: casi todos los códigos los vende una sola cadena, y de los 631 que están en todas elegí 31 que cubren los rubros básicos.

| Grupo | Productos |
| --- | --- |
| Almacén (12) | Aceite de girasol Cocinero 900 ml · Arroz largo fino Molinos Ala 1 kg · Fideos tallarines Matarazzo 500 g · Harina ultra refinada Pureza 1 kg · Sal fina Celusal 500 g · Yerba mate Amanda 1 kg · Café molido La Virginia 250 g · Té La Virginia 25 saquitos · Puré de tomate Arcor 520 g · Mayonesa Natura 250 cc · Caldo de carne Knorr x12 · Galletitas Traviata 5 × 108 g |
| Lácteos (5) | Leche entera La Serenísima sachet 1 L · Yogur entero frutilla Tregar 125 g · Manteca La Serenísima 100 g · Crema para cocinar La Serenísima 200 cc · Dulce de leche clásico La Serenísima 400 g |
| Bebidas (3) | Agua mineral Villavicencio 2 L · Coca-Cola regular 2,25 L · Jugo de naranja Del Valle 1 L |
| Otros alimentos (3) | Mermelada de frutilla Arcor 454 g · Hamburguesas Paty finitas x2 · Salchichas Vienissima x6 |
| Limpieza e higiene (8) | Limpiador Poett 900 cc · Lavandina Ayudín 1 L · Lavavajillas Cif limón 500 ml · Jabón en polvo Ala 800 g · Papel higiénico Higienol 4 × 100 m · Crema dental Colgate triple acción 90 g · Jabón de tocador Palmolive 85 g · Shampoo Sedal 340 cc |

&#91;embedded content: verificar\_canasta.py · 19/10/2026\]

Las siete cadenas quedan dentro de un rango de $3.737. Es una foto de un solo día: la serie diaria va a mostrar si el orden se mantiene.

## Limitaciones

La canasta v1 compara bien a las cadenas entre sí, pero no mide el costo de vida. Estos límites están asumidos a propósito:

- **Solo productos envasados con EAN.** Carne, verdura y fiambre al peso usan códigos internos y quedan afuera. No es la Canasta Básica del INDEC: es una unidad de cada producto, sin ponderar por consumo.
- **Es una suma de medianas nacionales.** No es lo que paga alguien en una sucursal concreta, y esconde las diferencias entre provincias.
- **Precio de lista, sin promociones.** Las ofertas y los descuentos por medio de pago no entran.
- **Calibrada con 8 días.** Con más historial, algunos productos se van a discontinuar, y la tolerancia de "1 día" conviene expresarla como una proporción de días.
- **Depende de lo que informa cada cadena.** Que un producto no esté en SEPA no prueba que no esté en la góndola, y al revés.
- **La clasificación por rubro no tiene el acierto medido.** Sirvió para ordenar la revisión manual, no como resultado.

## Próximos pasos

Lo siguiente es llevar la canasta a la nube y calcularla todos los días.

1. **Cargarla en BigQuery como seed de dbt** y calcular el total diario por cadena, que el sitio va a publicar.
2. **Definir qué pasa cuando falta un producto:** usar el último precio visto hasta 7 días y, después de eso, marcar la canasta de esa cadena como incompleta, en lugar de sumarla con un producto menos.
3. **Mantenerla en el tiempo:** si un EAN desaparece (por ejemplo, por un cambio de envase), se reemplaza y se publica una nueva versión con la columna `version`, para que la serie no tenga saltos falsos.
4. **Fase 2, clasificación por categorías:** un conjunto de prueba etiquetado a mano, la comparación entre reglas, un modelo supervisado y un LLM, con métricas. Eso habilita una canasta por categorías, con precio por kilo o por litro, que puede incluir azúcar, queso, fiambres y frescos.

## Cómo contarlo en una entrevista

La historia que conviene contar no es "armé una lista", sino "medí antes de decidir, verifiqué con consultas y corregí el criterio cuando los datos no cerraban".

**Pitch de un minuto:**

> En mi pipeline de precios de supermercados tengo unos 14 millones de precios por día de 7 cadenas, y quería responder cuál es más barata. Para comparar en serio hace falta el mismo producto, así que armé una canasta de códigos de barras. Primero definí qué códigos son comparables y medí cuántos están en todas las cadenas: de 66.657, solo 560. Como los mejor cubiertos eran cremas y whisky, escribí un clasificador de reglas con votación entre cadenas para encontrar alimentos. Elegí los productos y escribí un script que los verifica con consultas. Después cuestioné el resultado: yo sé que DIA vende lavandina Ayudín, y descubrí que un día de datos incompletos de DIA dejaba afuera productos que sí vende. Ajusté el criterio, lo validé y quedó una canasta de 31 productos presentes en las 7 cadenas y las 24 provincias. El 19/10, la más cara costaba un 3,7 % más que la más barata.

**Preguntas probables:**

- **¿Por qué no usaste todos los productos?** Porque cada cadena vende un surtido distinto, y un promedio de todo compara cosas diferentes. Con la misma lista de EAN, la diferencia de precio es real.
- **¿Por qué la mediana y no el promedio?** Porque es robusta: una sucursal con un precio mal cargado casi no la mueve, y al promedio sí.
- **¿Cómo sabés que los números están bien?** Por un script de verificación con cuatro controles, pruebas con datos inventados y una predicción anotada antes de cada corrida. Por ejemplo, predije que la tolerancia de un día iba a sumar sobre todo productos de DIA, y la consulta dio 70 de 71.
- **¿Por qué reglas y no machine learning?** Porque no tenía datos etiquetados para entrenar ni para medir un modelo, y para elegir 30 productos alcanzaba con ordenar y revisar a mano. La comparación con un modelo, con métricas, es la fase 2.
- **¿Qué fue lo más difícil?** Entender que la ausencia en los datos no es ausencia en la góndola. Hizo falta conocer el dominio para sospechar y una herramienta de búsqueda para comprobarlo.
- **¿Qué harías distinto?** Buscar por EAN desde el principio, en lugar de por palabras, y tener la verificación escrita antes de elegir los productos.
- **¿Usaste IA?** Conviene responder con la verdad y con precisión, por ejemplo: "Usé Claude como asistente para escribir código y discutir alternativas. Las decisiones y la verificación de cada resultado fueron mías, y puedo explicar cada script." Antes de la entrevista, repasá los scripts para poder explicarlos línea por línea.
