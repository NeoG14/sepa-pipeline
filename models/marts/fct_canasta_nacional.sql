-- Canasta nacional: un registro por fecha y cadena, con el total de los productos de la canasta.
--
-- Si un producto no aparece un día, se usa su último precio visto hasta `dias_arrastre_canasta`
-- días atrás (7 por defecto). Pasa seguido: la cadena 15 informa unas 3.000 filas menos los
-- martes y le faltan 4 productos de la canasta. Si falta más tiempo, la canasta de ese día queda
-- incompleta y el total queda vacío: nunca se publica un total parcial como si fuera completo.
{% set dias_arrastre = var('dias_arrastre_canasta', 7) %}

with observados as (
    select * from {{ ref('int_canasta_precios_dia') }}
),

productos as (
    select distinct ltrim(ean, '0') as clave from {{ ref('canasta') }}
),

-- Todas las combinaciones que deberían tener precio: cada fecha, cada cadena, cada producto.
grilla as (
    select f.fecha, c.id_comercio, p.clave
    from (select distinct fecha from observados) f
    cross join (select distinct id_comercio from observados) c
    cross join productos p
),

-- Para cada combinación, el último precio visto en esa fecha o antes (ASOF JOIN).
con_precio as (
    select
        g.fecha,
        g.id_comercio,
        g.clave,
        o.fecha                                   as fecha_precio,
        o.precio_lista_mediana,
        date_diff('day', o.fecha, g.fecha)        as dias_desde_precio
    from grilla g
    asof left join observados o
      on  o.id_comercio = g.id_comercio
      and o.clave = g.clave
      and g.fecha >= o.fecha
),

resumen as (
    select
        fecha,
        id_comercio,
        count(*) filter (where dias_desde_precio = 0)                              as productos_observados,
        count(*) filter (where dias_desde_precio between 1 and {{ dias_arrastre }}) as productos_arrastrados,
        sum(precio_lista_mediana) filter (where dias_desde_precio <= {{ dias_arrastre }}) as suma
    from con_precio
    group by fecha, id_comercio
)

select
    fecha,
    id_comercio,
    productos_observados,
    productos_arrastrados,
    productos_observados + productos_arrastrados = (select count(*) from productos) as completa,
    case when productos_observados + productos_arrastrados = (select count(*) from productos)
         then suma end                                                         as total
from resumen