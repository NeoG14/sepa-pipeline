-- Agregado diario: un registro por fecha, comercio, producto y provincia.
-- Solo sucursales físicas con provincia, y solo precios de lista informados.
--
-- Es incremental: cada corrida calcula solo las fechas que todavía no tiene, y conserva
-- las últimas `dias_agregado_diario` fechas del calendario (21 por defecto). Más atrás no hace
-- falta: el historial de cambios guarda lo viejo. Ocupa ~31 MB por día.
{% set dias = var('dias_agregado_diario', 21) %}

{{ config(
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'fecha',
    post_hook = "delete from {{ this }} where fecha <= (select max(fecha) - " ~ dias ~ " from {{ this }})"
) }}

{% set fechas = fechas_a_procesar(dias) %}

select
    p.fecha,
    p.id_comercio,
    p.id_producto,
    s.provincia,
    count(*)                                              as sucursales,
    median(p.precio_lista)                                as precio_lista_mediana,
    min(p.precio_lista)                                   as precio_lista_min,
    max(p.precio_lista)                                   as precio_lista_max,
    count(*) filter (where p.precio_promo1 is not null)   as sucursales_promo1,
    median(p.precio_promo1)                               as precio_promo1_mediana,
    count(*) filter (where p.precio_promo2 is not null)   as sucursales_promo2,
    median(p.precio_promo2)                               as precio_promo2_mediana
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
  -- Fechas como constantes: así DuckDB lee solo esas carpetas de Parquet y no todas
  and p.fecha in ({% for f in fechas %}date '{{ f }}'{{ ", " if not loop.last }}{% endfor %})
  and s.fecha in ({% for f in fechas %}date '{{ f }}'{{ ", " if not loop.last }}{% endfor %})
{% else %}
  and false  -- no hay fechas nuevas: el modelo no inserta nada
{% endif %}
group by all