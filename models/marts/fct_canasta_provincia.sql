-- Canasta por provincia: ranking del día de las cadenas de cada provincia.
--
-- En las provincias no todas las cadenas tienen los 31 productos (el 20/10, 43 de 99
-- combinaciones estaban completas), así que se compara sobre los productos que tienen todas las
-- cadenas de esa provincia ese día. El conjunto cambia por provincia y por día: sirve para
-- comparar cadenas dentro de una provincia en una fecha, no provincias entre sí ni una serie de
-- tiempo. Se arma con los días que guarda el agregado diario (21).
with canasta as (
    select distinct ltrim(ean, '0') as clave from {{ ref('canasta') }}
),

precios as (
    select fecha, provincia, id_comercio, ltrim(id_producto, '0') as clave, precio_lista_mediana
    from {{ ref('int_precios_dia') }}
    where ltrim(id_producto, '0') in (select clave from canasta)
),

cadenas as (
    select fecha, provincia, count(distinct id_comercio) as cadenas
    from precios
    group by fecha, provincia
),

-- Productos que tienen todas las cadenas de la provincia ese día
comunes as (
    select p.fecha, p.provincia, p.clave
    from precios p
    join cadenas c using (fecha, provincia)
    group by p.fecha, p.provincia, p.clave, c.cadenas
    having count(distinct p.id_comercio) = c.cadenas
),

totales as (
    select p.fecha, p.provincia, p.id_comercio,
           count(*)                    as productos_comparados,
           sum(p.precio_lista_mediana) as total
    from precios p
    join comunes using (fecha, provincia, clave)
    group by p.fecha, p.provincia, p.id_comercio
)

select
    t.fecha,
    t.provincia,
    t.id_comercio,
    c.cadenas,
    t.productos_comparados,
    t.total,
    rank() over (partition by t.fecha, t.provincia order by t.total) as puesto
from totales t
join cadenas c using (fecha, provincia)