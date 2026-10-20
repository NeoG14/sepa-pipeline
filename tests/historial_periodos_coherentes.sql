-- Falla si un período termina antes de empezar, si una versión vieja no tiene fecha de fin,
-- si una clave tiene más (o menos) de una última versión, o si la última fecha vista es
-- anterior al inicio de la última versión.
with por_clave as (
    select id_comercio, id_producto, provincia,
           count(*) filter (where estado <> 'reemplazado') as ultimas
    from {{ ref('fct_precios_historial') }}
    group by all
)
select 'periodo invertido' as problema, id_comercio, id_producto, provincia
from {{ ref('fct_precios_historial') }}
where fecha_hasta < fecha_desde
union all
select 'version vieja sin fin', id_comercio, id_producto, provincia
from {{ ref('fct_precios_historial') }}
where estado = 'reemplazado' and fecha_hasta is null
union all
select 'ultima vista antes del inicio', id_comercio, id_producto, provincia
from {{ ref('fct_precios_historial') }}
where estado <> 'reemplazado' and ultima_fecha_vista < fecha_desde
union all
select 'no tiene exactamente una ultima version', id_comercio, id_producto, provincia
from por_clave
where ultimas <> 1
