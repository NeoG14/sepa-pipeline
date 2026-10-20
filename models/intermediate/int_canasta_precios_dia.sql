-- Precio nacional de cada producto de la canasta: un registro por fecha, cadena y producto, con la
-- mediana del precio de lista entre todas las sucursales físicas del país. Se calcula desde las
-- sucursales y no desde el agregado por provincia, porque la mediana de las medianas provinciales
-- no es la mediana nacional.
--
-- Es incremental y se guarda para siempre (unas 217 filas por día): el agregado diario solo guarda
-- 21 días, así que la historia de la canasta tiene que vivir acá. Por eso full_refresh = false.
-- Para reconstruirla desde los Parquet: borrar la tabla y correr
--   dbt build --select int_canasta_precios_dia+ --vars "{dias_canasta: 100000}"
{% set dias = var('dias_canasta', 21) %}

{{ config(
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'fecha',
    full_refresh = false
) }}

{% set fechas = fechas_a_procesar(dias) %}

with canasta as (
    select distinct ltrim(ean, '0') as clave from {{ ref('canasta') }}
)

select
    p.fecha,
    p.id_comercio,
    ltrim(p.id_producto, '0')      as clave,
    count(*)                       as sucursales,
    median(p.precio_lista)         as precio_lista_mediana
from {{ ref('stg_precios') }} as p
join {{ ref('stg_sucursales') }} as s
  on  s.fecha = p.fecha
  and s.id_comercio = p.id_comercio
  and s.id_bandera = p.id_bandera
  and s.id_sucursal = p.id_sucursal
where s.provincia is not null
  and coalesce(s.sucursales_tipo, '') <> 'Web'
  and p.precio_lista is not null
  and ltrim(p.id_producto, '0') in (select clave from canasta)
{% if fechas %}
  and p.fecha in ({% for f in fechas %}date '{{ f }}'{{ ", " if not loop.last }}{% endfor %})
  and s.fecha in ({% for f in fechas %}date '{{ f }}'{{ ", " if not loop.last }}{% endfor %})
{% else %}
  and false  -- no hay fechas nuevas: el modelo no inserta nada
{% endif %}
group by all