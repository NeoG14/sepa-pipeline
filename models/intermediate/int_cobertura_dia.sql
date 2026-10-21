-- Sucursales que informaron precios: un registro por fecha, cadena y provincia (unas 99 filas por día).
-- Solo sucursales físicas con provincia y precio de lista, igual que el agregado diario.
--
-- Sirve para saber cuándo una cadena informó desde menos sucursales que lo habitual: la
-- Cooperativa Obrera informa 96 de 156 los domingos, y ese día la mediana cambia por la muestra y no
-- por el precio. Es incremental y se guarda para siempre, porque el exportador del sitio revisa
-- toda la historia. Para reconstruirla: borrar la tabla y correr
--   dbt build --select int_cobertura_dia+ --vars "{dias_cobertura: 100000}"
{% set dias = var('dias_cobertura', 21) %}

{{ config(
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'fecha',
    full_refresh = false
) }}

{% set fechas = fechas_a_procesar(dias) %}

select
    p.fecha,
    p.id_comercio,
    s.provincia,
    count(distinct p.id_bandera || '-' || p.id_sucursal) as sucursales
from {{ ref('stg_precios') }} as p
join {{ ref('stg_sucursales') }} as s
  on  s.fecha = p.fecha
  and s.id_comercio = p.id_comercio
  and s.id_bandera = p.id_bandera
  and s.id_sucursal = p.id_sucursal
where s.provincia is not null
  and coalesce(s.sucursales_tipo, '') <> 'Web'
  and p.precio_lista is not null
{% if fechas %}
  and p.fecha in ({% for f in fechas %}date '{{ f }}'{{ ", " if not loop.last }}{% endfor %})
  and s.fecha in ({% for f in fechas %}date '{{ f }}'{{ ", " if not loop.last }}{% endfor %})
{% else %}
  and false  -- no hay fechas nuevas: el modelo no inserta nada
{% endif %}
group by all