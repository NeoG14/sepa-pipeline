-- Historial listo para usar: cada versión de precio con hasta cuándo vale y su estado.
--
--   fecha_desde          primer día de esa versión
--   fecha_hasta          último día: el anterior al próximo cambio; en la última versión,
--                        vacío si sigue vigente, o la última fecha en que se vio si ya no está
--   estado               'reemplazado'   una versión vieja, que cambió después
--                        'vigente'       la última versión, vista hace 7 días o menos
--                        'no disponible' la última versión, sin aparecer hace más de 7 días
--
-- Las ausencias se ignoran: si un producto falta unos días y vuelve con el mismo precio,
-- la versión sigue siendo la misma. Los días se cuentan contra la fecha más nueva de los
-- datos, no contra hoy: si la PC estuvo apagada, nada pasa a "no disponible" por eso.
{{ config(materialized = 'view') }}

{% set dias_disponible = var('dias_hasta_no_disponible', 7) %}

with versiones as (
    select
        *,
        lead(fecha_desde) over (
            partition by id_comercio, id_producto, provincia order by fecha_desde
        ) as proximo_cambio
    from {{ ref('fct_precios_cambios') }}
),

referencia as (
    select max(fecha) as ultima_fecha_datos from {{ ref('int_precios_dia') }}
)

select
    v.id_comercio,
    v.id_producto,
    v.provincia,
    v.fecha_desde,
    case
        when v.proximo_cambio is not null then v.proximo_cambio - 1
        when r.ultima_fecha_datos - u.ultima_fecha_vista > {{ dias_disponible }} then u.ultima_fecha_vista
    end as fecha_hasta,
    case
        when v.proximo_cambio is not null then 'reemplazado'
        when r.ultima_fecha_datos - u.ultima_fecha_vista > {{ dias_disponible }} then 'no disponible'
        else 'vigente'
    end as estado,
    u.ultima_fecha_vista,
    v.sucursales,
    v.precio_lista_mediana,
    v.precio_lista_min,
    v.precio_lista_max,
    v.sucursales_promo1,
    v.precio_promo1_mediana,
    v.sucursales_promo2,
    v.precio_promo2_mediana
from versiones as v
join {{ ref('int_ultima_vista') }} as u using (id_comercio, id_producto, provincia)
cross join referencia as r
