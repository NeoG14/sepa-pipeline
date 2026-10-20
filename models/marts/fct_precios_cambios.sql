-- Historial de cambios de precio: una fila cada vez que cambia alguno de los valores que
-- seguimos para un comercio, producto y provincia (SCD tipo 2, guardando solo los cambios).
-- Cada fila vale desde `fecha_desde` hasta el día anterior al próximo cambio.
--
-- Se ordena por la FECHA DEL DATO, no por la fecha de la corrida: si una fecha llega tarde,
-- queda en su lugar. Para eso, cada corrida borra y recalcula los últimos
-- `ventana_historial` días (14 por defecto), partiendo del último estado anterior a la ventana.
--
-- full_refresh = false protege el historial: un `dbt build --full-refresh` no lo borra.
-- Para reconstruirlo entero desde los Parquet, se agranda la ventana para que abarque todo:
--   dbt build --select int_precios_dia+ --full-refresh --vars "{dias_agregado_diario: 100000, ventana_historial: 100000}"
-- (la corrida normal siguiente vuelve a dejar el agregado diario en 21 días)
{% set ventana = var('ventana_historial', 14) %}
{% set columnas = [
    'precio_lista_mediana', 'precio_lista_min', 'precio_lista_max',
    'sucursales_promo1', 'precio_promo1_mediana',
    'sucursales_promo2', 'precio_promo2_mediana'
] %}

{{ config(
    materialized = 'incremental',
    incremental_strategy = 'append',
    full_refresh = false,
    pre_hook = "{% if is_incremental() %}delete from {{ this }} where fecha_desde > (select max(fecha) - " ~ ventana ~ " from {{ ref('int_precios_dia') }}){% endif %}"
) }}

with dias as (
    -- Los días a evaluar: todo el agregado la primera vez; después, solo la ventana
    select fecha, id_comercio, id_producto, provincia, sucursales,
           {{ columnas | join(', ') }},
           false as es_estado_previo
    from {{ ref('int_precios_dia') }}
    {% if is_incremental() %}
    where fecha > (select max(fecha) - {{ ventana }} from {{ ref('int_precios_dia') }})
    {% endif %}
),

{% if is_incremental() %}
estado_previo as (
    -- El último valor conocido de cada clave antes de la ventana: contra él se compara
    -- el primer día de la ventana
    select fecha_desde as fecha, id_comercio, id_producto, provincia, sucursales,
           {{ columnas | join(', ') }},
           true as es_estado_previo
    from {{ this }}
    where fecha_desde <= (select max(fecha) - {{ ventana }} from {{ ref('int_precios_dia') }})
    qualify row_number() over (
        partition by id_comercio, id_producto, provincia order by fecha_desde desc
    ) = 1
),
{% endif %}

secuencia as (
    select * from dias
    {% if is_incremental() %}
    union all
    select * from estado_previo
    {% endif %}
),

comparado as (
    select *,
        row_number() over clave as orden,
        {% for c in columnas %}
        lag({{ c }}) over clave as anterior_{{ c }}{{ "," if not loop.last }}
        {% endfor %}
    from secuencia
    window clave as (partition by id_comercio, id_producto, provincia order by fecha)
)

select
    id_comercio,
    id_producto,
    provincia,
    fecha as fecha_desde,
    sucursales,
    {{ columnas | join(', ') }}
from comparado
where not es_estado_previo
  and (
        orden = 1
        {% for c in columnas %}
        or {{ c }} is distinct from anterior_{{ c }}
        {% endfor %}
  )
