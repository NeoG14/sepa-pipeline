-- Los productos con que se compara cada provincia cada día: los códigos de barras que tienen TODAS
-- las cadenas de la provincia ese día con un precio representativo (informado en al menos el 5 % de
-- las sucursales de la cadena; ver int_canasta_provincia_precios), con su mediana entre cadenas.
-- fct_canasta_provincia calcula el ranking con esta misma tabla, y el sitio la muestra como la lista
-- de productos de la comparación: así la lista y el "591 productos" del titular salen del mismo cálculo.
with precios as (
    select * from {{ ref('int_canasta_provincia_precios') }}
),

-- Las cadenas de la provincia ese día: todas las que informan algún código de barras, aunque un
-- producto en particular no sea representativo (si no, el producto parecería "de todas" sin serlo)
cadenas as (
    select fecha, provincia, count(distinct id_comercio) as cadenas
    from precios
    group by fecha, provincia
)

select p.fecha, p.provincia, p.clave, median(p.precio) as mediana
from precios p
join cadenas c using (fecha, provincia)
where p.representativo
group by p.fecha, p.provincia, p.clave, c.cadenas
having count(*) = c.cadenas
