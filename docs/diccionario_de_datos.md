# Diccionario de datos

Qué guarda el proyecto y qué significa cada columna. Las columnas y las filas salen de `python -m scripts.ver_columnas` (base local y Parquet del 24/10/2026, con 15 días de historia). Si cambia un modelo, se vuelve a correr ese script y se actualiza este archivo.

**Cadenas** (`id_comercio`): 2 La Anónima · 9 Cencosud · 10 Carrefour · 11 Changomas · 12 Coto · 13 Cooperativa Obrera · 15 DIA.
**Provincias** (`provincia`): código ISO 3166-2, por ejemplo `AR-B` es Buenos Aires.
**Clave de producto** (`clave`): el código de barras sin ceros a la izquierda. Si el producto solo tiene código interno de la cadena, `comercio-código` (no se mezcla entre cadenas).

## Cuánto se guarda de cada cosa

| Capa | Qué se conserva |
|---|---|
| Parquet crudos (`sepa-datos/parquet/fecha=*`) | Todos los días, sin recortar (copia en Drive) |
| `int_precios_dia` | Los últimos 21 días |
| Tablas incrementales (`fct_precios_cambios`, `int_ultima_vista`, `int_cobertura_dia`, `int_canasta_precios_dia`, `fct_indice_cadena`) | Para siempre: crecen cada día |
| `fct_canasta_provincia`, `fct_canasta_provincia_productos` | Se recalculan desde la ventana de 21 días |
| `fct_canasta_nacional`, `fct_cobertura` | Se recalculan desde tablas que se guardan para siempre, así que conservan toda la historia |
| `fct_canasta_provincia_grupo`, `fct_precio_kilo_provincia`, recetas | Solo el último día de cada provincia |

---

## 1. Datos crudos de la ingesta (Parquet, un día por carpeta)

Solo se conservan los 7 comercios de arriba (99 % de las filas).

### `precios` (14.051.448 filas el 24/10)
Una fila por sucursal y producto.

| Columna | Qué es | Usada en dbt |
|---|---|---|
| `fecha` | Día del dato | sí |
| `id_comercio`, `id_bandera`, `id_sucursal` | Cadena, marca dentro de la cadena (Vea, Disco, Jumbo…) y sucursal | sí |
| `id_producto` | Código que informa la cadena (código de barras o interno) | sí |
| `precio_lista` | Precio de lista | sí |
| `precio_promo1`, `precio_promo2` | Precio promocional | sí |
| `precio_referencia` | Precio por unidad de medida (por kilo, por litro…) | **no** |
| `cantidad_referencia`, `unidad_referencia` | Cantidad y unidad a la que se refiere ese precio | **no** |
| `leyenda_promo1`, `leyenda_promo2` | Texto de la promoción | **no** |

### `productos` (113.101 filas)
| Columna | Qué es | Usada en dbt |
|---|---|---|
| `fecha`, `id_comercio`, `id_producto` | Día, cadena y código | sí |
| `descripcion`, `marca` | Nombre y marca como los informa la cadena | sí |
| `productos_ean` | Código de barras informado por la cadena | **no** |
| `cantidad_presentacion`, `unidad_presentacion` | Tamaño del envase | **no** |

### `sucursales` (2.510 filas)
| Columna | Qué es | Usada en dbt |
|---|---|---|
| `fecha`, `id_comercio`, `id_bandera`, `id_sucursal` | Identifican la sucursal | sí |
| `sucursales_tipo` | Tipo (se descartan las `Web`) | sí |
| `provincia` | Provincia normalizada a código ISO | sí |
| `provincia_original` | Provincia como la informa la cadena | no |
| `sucursales_nombre`, `sucursales_calle`, `sucursales_numero`, `sucursales_barrio`, `sucursales_localidad`, `sucursales_codigo_postal` | Dirección | **no** |
| `sucursales_latitud`, `sucursales_longitud` | Ubicación | **no** |
| `sucursales_observaciones` | Texto libre | no |
| `sucursales_lunes_horario_atencion` … `sucursales_domingo_horario_atencion` (7 columnas) | Horario de atención por día | **no** |

### `comercios` (18 filas: una por bandera)
`fecha`, `id_comercio`, `id_bandera`, `comercio_cuit`, `comercio_razon_social`, `comercio_bandera_nombre`, `comercio_bandera_url`, `comercio_ultima_actualizacion`, `comercio_version_sepa`. Ninguna se usa en dbt.

---

## 2. Staging (vistas sobre los Parquet)

| Vista | Columnas |
|---|---|
| `stg_precios` | `fecha`, `id_comercio`, `id_bandera`, `id_sucursal`, `id_producto`, `precio_lista`, `precio_promo1`, `precio_promo2` |
| `stg_productos` | `fecha`, `id_comercio`, `id_producto`, `clave`, `descripcion` (sin el código de envase de la cadena 9), `envase`, `presentacion`, `marca` (normalizada) |
| `stg_sucursales` | `fecha`, `id_comercio`, `id_bandera`, `id_sucursal`, `provincia`, `sucursales_tipo` |

---

## 3. Precios

### `int_precios_dia` (20.584.015 filas, últimos 21 días)
Un registro por fecha, cadena, producto y provincia. Solo sucursales físicas, con provincia y con precio de lista.

| Columna | Qué es |
|---|---|
| `fecha`, `id_comercio`, `id_producto`, `provincia` | Clave |
| `sucursales` | Cuántas sucursales informan el producto en esa provincia ese día |
| `precio_lista_mediana`, `precio_lista_min`, `precio_lista_max` | Mediana, mínimo y máximo del precio de lista entre esas sucursales |
| `sucursales_promo1`, `precio_promo1_mediana` | Sucursales con precio promocional 1 y su mediana |
| `sucursales_promo2`, `precio_promo2_mediana` | Ídem, promoción 2 |

### `fct_precios_cambios` (2.088.374 filas, para siempre)
Historial: una fila cada vez que cambia alguno de los 7 valores de abajo para una cadena, producto y provincia. Vale desde `fecha_desde` hasta el día anterior al siguiente cambio.

Columnas: `id_comercio`, `id_producto`, `provincia`, `fecha_desde`, `sucursales`, `precio_lista_mediana`, `precio_lista_min`, `precio_lista_max`, `sucursales_promo1`, `precio_promo1_mediana`, `sucursales_promo2`, `precio_promo2_mediana` (mismo significado que en `int_precios_dia`).

### `fct_precios_historial` (vista sobre la anterior)
Las mismas columnas más:

| Columna | Qué es |
|---|---|
| `fecha_hasta` | Último día de esa versión del precio; vacío si sigue vigente |
| `estado` | `reemplazado`, `vigente` o `no disponible` (más de 7 días sin aparecer) |
| `ultima_fecha_vista` | Último día en que se vio el producto |

### `int_ultima_vista` (1.442.349 filas, para siempre)
`id_comercio`, `id_producto`, `provincia`, `ultima_fecha_vista`: la última fecha en que apareció cada combinación.

---

## 4. Cobertura de sucursales

### `int_cobertura_dia` (1.481 filas, para siempre)
`fecha`, `id_comercio`, `provincia`, `sucursales`: cuántas sucursales físicas informaron precios ese día.

### `fct_cobertura` (1.481 filas)
Lo anterior más:

| Columna | Qué es |
|---|---|
| `habituales` | Mediana de sucursales de los 28 días anteriores |
| `cobertura` | `sucursales` / `habituales` |
| `cobertura_baja` | Verdadero si la cobertura es menor a 80 % |

---

## 5. Catálogo y clasificación

### `dim_productos` (72.875 filas)
Un producto por `clave`, con todas las fechas para conservar los que ya no se venden.

| Columna | Qué es |
|---|---|
| `clave` | Clave del producto |
| `es_ean` | Falso si es un código interno de una cadena |
| `nombre` | La descripción más larga entre las cadenas |
| `marca` | Marca normalizada (la variante más frecuente del catálogo) |
| `envase`, `presentacion` | Sacados de la descripción de la cadena 9 |
| `cadenas` | En cuántas cadenas se vende |
| `primera_fecha`, `ultima_fecha` | Primer y último día en que se vio |
| `texto_busqueda` | Nombre y marca en mayúsculas y sin tildes, para el buscador |
| `rubro`, `grupo` | Clasificación (vacía si nadie la resolvió) |
| `fuente_rubro` | `manual`, `deepseek`, `regla`, `modelo` o `sin clasificar` |

### `clasificacion_productos` (72.875 filas)
Quién decidió el rubro de cada producto. Orden: corrección manual, después DeepSeek, después reglas y modelo.
Columnas: `clave`, `rubro`, `grupo`, `fuente`, `probabilidad` (del modelo; vacía si decidió una regla), `rubro_modelo` (lo que habría dicho el modelo aunque no llegara al umbral), `version`, `fecha`.

### `clasificacion_automatica` (72.875 filas)
La salida de las reglas y el modelo, una fila por producto. Columnas: `clave`, `rubro`, `probabilidad`, `fuente`, `rubro_modelo`, `version`, `fecha`.

### `int_productos` (72.875 filas) e `int_descripciones_producto` (72.875 filas)
- `int_productos`: las mismas columnas que `dim_productos` sin `rubro`, `grupo` ni `fuente_rubro`.
- `int_descripciones_producto`: `clave`, `marca`, `cadenas`, `descripciones` (lista con la descripción de cada cadena, ordenada por cadena). Es lo que lee el clasificador.

---

## 6. Rankings y canastas

### `fct_canasta_provincia` (1.481 filas)
Ranking diario de las cadenas en cada provincia, sobre los códigos de barras que tienen todas las cadenas de esa provincia ese día.

| Columna | Qué es |
|---|---|
| `fecha`, `provincia`, `id_comercio` | Clave |
| `cadenas` | Cuántas cadenas hay en la provincia ese día |
| `productos_comparados` | Cuántos productos entran en la comparación |
| `indice` | Media geométrica de (precio de la cadena / mediana entre cadenas); 1,00 es la mediana |
| `diferencia` | Cuánto más cara es que la más barata (0,07 = 7 % más cara) |
| `total` | Suma de los precios de esos productos en la cadena |
| `puesto` | Posición en el ranking (1 es la más barata) |

### `fct_canasta_provincia_productos` (619.671 filas)
`fecha`, `provincia`, `clave`, `mediana`: los productos que se comparan cada día en cada provincia, con la mediana entre cadenas. Es la lista de productos del sitio.

### `fct_canasta_provincia_grupo` (698 filas, último día)
El mismo índice por grupo de producto. Columnas: `fecha`, `provincia`, `grupo`, `id_comercio`, `productos_comparados`, `indice`, `diferencia`, `puesto`. Solo grupos con 30 o más productos por cadena.

### `fct_canasta_nacional` (105 filas)
Canasta fija de 31 productos, a nivel país.

| Columna | Qué es |
|---|---|
| `fecha`, `id_comercio` | Clave |
| `productos_observados` | Productos con precio ese día |
| `productos_arrastrados` | Productos con el último precio de hasta 7 días antes |
| `completa` | Verdadero si están los 31 |
| `total` | Suma de la canasta (vacío si no está completa) |

### `int_canasta_precios_dia` (3.249 filas, para siempre)
`fecha`, `id_comercio`, `clave`, `sucursales`, `precio_lista_mediana`: la mediana nacional de cada producto de la canasta fija.

### `int_canasta_provincia_precios` (vista)
Precio de cada cadena y producto por provincia y día.

| Columna | Qué es |
|---|---|
| `fecha`, `provincia`, `id_comercio`, `clave` | Clave |
| `precio` | Mediana del precio de lista entre sucursales |
| `sucursales` | Sucursales que lo informan |
| `sucursales_cadena` | Sucursales que tiene la cadena en la provincia ese día |
| `representativo` | Verdadero si lo informa al menos el 5 % de las sucursales de la cadena |

### `fct_indice_cadena` (1.378 filas, para siempre)
Cambio de precio de cada cadena de un día al siguiente. De acá sale el gráfico «¿Cuánto cambiaron los precios?».

| Columna | Qué es |
|---|---|
| `fecha`, `fecha_anterior` | Día y día contra el que se compara |
| `provincia`, `id_comercio` | Clave |
| `productos` | Productos que están los dos días y entran en el cálculo |
| `descartados` | Productos cuyo precio bajó a menos de la mitad o subió a más del doble (se descartan por posible error de carga) |
| `factor` | Media geométrica de (precio de hoy / precio de ayer); 1,01 es +1 % |

---

## 7. Precio por kilo

### `fct_precio_kilo_provincia` (3.169 filas, último día)
| Columna | Qué es |
|---|---|
| `fecha`, `provincia`, `id_comercio` | Clave |
| `producto`, `grupo` | Por ejemplo «Asado», «Carne vacuna» |
| `productos` | Cuántos códigos de ese producto tiene la cadena |
| `precio_kg` | Mediana del precio por kilo |
| `minimo` | El más barato entre esos códigos |
| `antes_kg`, `dias_antes` | Mediana de los 14 días anteriores y cuántos días la sostienen |
| `promo_kg` | Mediana del precio promocional por kilo |
| `baja_fuerte` | Verdadero si hoy cuesta el 80 % o menos que antes (con al menos 3 días de referencia) |
| `con_promo` | Verdadero si la mitad o más de las sucursales tiene promoción y la promoción es más de 3 % menor |

---

## 8. Recetas (solo en dbt, no se muestran en el sitio)

| Tabla | Filas | Columnas |
|---|---|---|
| `int_receta_linea` | 2.475 | `fecha`, `provincia`, `id_comercio`, `receta`, `porciones`, `ingrediente`, `cantidad`, `producto_elegido`, `precio_unidad`, `estimado`, `costo` |
| `fct_receta_provincia` | 297 | `fecha`, `provincia`, `id_comercio`, `receta`, `porciones`, `total`, `por_porcion`, `ingredientes`, `estimados`, `costo_estimado` |
| `ingrediente_producto` | 1.300 | `id_comercio`, `id_producto`, `ingrediente`, `tamano` |

`estimado` marca el ingrediente que la cadena no informa y se completa con la mediana de las otras cadenas; `estimados` cuenta cuántos hay en la receta y `costo_estimado`, cuánto suman.

---

## 9. Seeds (tablas chicas cargadas desde CSV)

| Seed | Filas | Columnas |
|---|---|---|
| `cadenas` | 7 | `id_comercio`, `nombre`, `banderas` |
| `canasta` | 31 | `ean`, `version`, `grupo`, `rubro`, `nombre` |
| `rubros` | 85 | `grupo`, `rubro`, `descripcion`, `division_indec`, `estado` |
| `rubros_llm` | 72.031 | `clave`, `rubro` (lo que clasificó DeepSeek) |
| `rubros_manuales` | 86 | `clave`, `rubro`, `motivo` |
| `pesables_producto` | 923 | `id_comercio`, `id_producto`, `producto`, `grupo`, `factor_kg` (multiplicador para pasar el precio a kilo) |
| `recetas` | 25 | `receta`, `porciones`, `ingrediente`, `cantidad`, `unidad`, `fuente`, `opciones` |
| `ingredientes` | 6 | `ingrediente`, `unidad`, `rubro`, `incluye`, `excluye`, `tam_min`, `tam_max` |

---

## Análisis que se pueden hacer con lo que hay

| Análisis | De dónde sale |
|---|---|
| Inflación por cadena y, con un cálculo nuevo, por grupo de producto | `fct_indice_cadena`, `dim_productos.grupo` |
| Cuánto varía el precio entre sucursales de una misma cadena | `precio_lista_min`, `precio_lista_max` en `int_precios_dia` |
| Frecuencia de cambios de precio por cadena y día de la semana | `fct_precios_cambios.fecha_desde` |
| Profundidad de las promociones por cadena | `sucursales_promo1` / `sucursales`, `precio_promo1_mediana` |
| Rotación del catálogo y productos discontinuados | `primera_fecha`, `ultima_fecha`, `estado` |
| Presencia geográfica de cada cadena | `int_cobertura_dia` |
| Calidad de la clasificación | `fuente`, `probabilidad` |

Para habilitar más análisis habría que traer al dbt estas columnas crudas: `precio_referencia` y `unidad_referencia` (precio por unidad de medida), `leyenda_promo1` y `leyenda_promo2` (tipo de promoción), `sucursales_latitud` y `sucursales_longitud` (mapa de sucursales) y `sucursales_localidad` (precio por zona).
