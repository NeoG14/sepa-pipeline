-- Agregado diario: un registro por fecha, comercio, producto y provincia.
-- Solo sucursales físicas con provincia, y solo precios de lista informados.
-- Es la base del historial y de la canasta.
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
group by all