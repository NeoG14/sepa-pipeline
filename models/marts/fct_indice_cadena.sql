-- Cuánto cambió el precio de cada cadena de un día al siguiente, por provincia: la base del índice de precios de cada
-- cadena que muestra el sitio (miles de productos por cadena, no una canasta de 31).
--
-- Para cada fecha, provincia y cadena: se toman los productos (solo códigos de barras, con la regla de cobertura del
-- 5 % de int_canasta_provincia_precios) que la cadena informó ese día Y el día anterior con datos de esa provincia, y se
-- promedia el cambio de precio con la media geométrica: exp(avg(ln(precio de hoy / precio de ayer))). Cada producto
-- pesa lo mismo, sea caro o barato. `factor` = 1,004 es una suba de 0,4 % ese día. El índice (base 100 el primer día)
-- es el producto acumulado de los factores: lo arma el exportador del sitio.
--
-- Por qué así y no con una canasta fija: la lista de productos que una cadena informa todos los días se achica con el
-- tiempo; comparando de un día al siguiente se usan siempre todos los que tiene. Solo dice cuánto cambió cada cadena,
-- no cuál es más barata (eso lo hace fct_canasta_provincia).
--
-- Los cambios de menos de la mitad o más del doble en un día (`indice_cambio_maximo`, 2) son errores de carga: se
-- descartan del promedio y se cuentan en `descartados`.
--
-- Es incremental: el agregado diario guarda solo 21 días y el índice tiene que seguir creciendo. Cada corrida calcula
-- desde la primera fecha que todavía no tiene (así un día que llega tarde, como el 16/10, se completa y se recalcula
-- el siguiente, que lo usaba de base). No se reconstruye con --full-refresh: lo anterior ya no existe en el agregado.
{{ config(
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'fecha',
    full_refresh = false
) }}
{% set maximo = var('indice_cambio_maximo', 2) %}

with precios as (
    select fecha, provincia, id_comercio, clave, precio
    from {{ ref('int_canasta_provincia_precios') }}
    where representativo and precio > 0
),

dias as (
    select provincia, fecha, lag(fecha) over (partition by provincia order by fecha) as anterior
    from (select distinct provincia, fecha from precios)
),

pendientes as (
    -- el primer día de cada provincia no tiene con qué compararse
    select provincia, fecha, anterior
    from dias
    where anterior is not null
    {% if is_incremental() %}
      and fecha >= coalesce(
          (select min(fecha) from dias where anterior is not null and fecha not in (select fecha from {{ this }})),
          date '9999-12-31')
    {% endif %}
),

pares as (
    select d.fecha, d.anterior, d.provincia, h.id_comercio, ln(h.precio / a.precio) as cambio
    from pendientes d
    join precios h on h.provincia = d.provincia and h.fecha = d.fecha
    join precios a on a.provincia = d.provincia and a.fecha = d.anterior
                  and a.id_comercio = h.id_comercio and a.clave = h.clave
)

select fecha, anterior as fecha_anterior, provincia, id_comercio,
       count(*) filter (where cambio between ln(1.0 / {{ maximo }}) and ln({{ maximo }}))     as productos,
       count(*) filter (where not cambio between ln(1.0 / {{ maximo }}) and ln({{ maximo }})) as descartados,
       exp(avg(cambio) filter (where cambio between ln(1.0 / {{ maximo }}) and ln({{ maximo }}))) as factor
from pares
group by fecha, anterior, provincia, id_comercio
