-- Falla si dos versiones seguidas de una misma clave tienen los mismos valores:
-- el historial solo tiene que guardar cambios.
with ordenado as (
    select *,
        lag(precio_lista_mediana) over w as a1, lag(precio_lista_min) over w as a2,
        lag(precio_lista_max) over w as a3, lag(sucursales_promo1) over w as a4,
        lag(precio_promo1_mediana) over w as a5, lag(sucursales_promo2) over w as a6,
        lag(precio_promo2_mediana) over w as a7,
        row_number() over w as orden
    from {{ ref('fct_precios_cambios') }}
    window w as (partition by id_comercio, id_producto, provincia order by fecha_desde)
)
select *
from ordenado
where orden > 1
  and precio_lista_mediana is not distinct from a1 and precio_lista_min is not distinct from a2
  and precio_lista_max is not distinct from a3 and sucursales_promo1 is not distinct from a4
  and precio_promo1_mediana is not distinct from a5 and sucursales_promo2 is not distinct from a6
  and precio_promo2_mediana is not distinct from a7
