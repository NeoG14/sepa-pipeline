-- La prueba más importante del historial: con él se tiene que poder reconstruir cada día del
-- agregado diario. Para cada fila de int_precios_dia busca la versión vigente ese día
-- (la última con fecha_desde <= fecha) y falla si falta o si algún valor no coincide.
with vigente as (
    select d.*,
           h.fecha_desde,
           h.precio_lista_mediana  as h1, h.precio_lista_min      as h2, h.precio_lista_max as h3,
           h.sucursales_promo1     as h4, h.precio_promo1_mediana as h5,
           h.sucursales_promo2     as h6, h.precio_promo2_mediana as h7
    from {{ ref('int_precios_dia') }} as d
    left join {{ ref('fct_precios_cambios') }} as h
      on  h.id_comercio = d.id_comercio
      and h.id_producto = d.id_producto
      and h.provincia = d.provincia
      and h.fecha_desde <= d.fecha
    qualify row_number() over (
        partition by d.fecha, d.id_comercio, d.id_producto, d.provincia order by h.fecha_desde desc
    ) = 1
)
select *
from vigente
where fecha_desde is null
   or precio_lista_mediana is distinct from h1 or precio_lista_min is distinct from h2
   or precio_lista_max is distinct from h3 or sucursales_promo1 is distinct from h4
   or precio_promo1_mediana is distinct from h5 or sucursales_promo2 is distinct from h6
   or precio_promo2_mediana is distinct from h7
