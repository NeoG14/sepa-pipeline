-- Ranking de cadenas por grupo de producto (almacén, limpieza, higiene personal...) en cada provincia,
-- solo para el último día de cada una.
--
-- Es el mismo cálculo que fct_canasta_provincia (precio de la cadena / mediana del producto entre las
-- cadenas de la provincia, media geométrica por cadena), pero agrupando los productos de la comparación
-- por su grupo. Los productos son los de fct_canasta_provincia_productos, así que cada grupo es un
-- pedazo de la misma comparación y no suma productos nuevos.
--
-- Solo se guardan los grupos con al menos `minimo_productos_grupo` productos por cadena en esa
-- provincia (30, medido en scripts/medir_grupos_comparacion.py): con menos, el orden se mueve de un
-- día a otro por la muestra. Quedan afuera los productos sin rubro y "No supermercado".
--
-- Solo el último día, porque el conjunto de productos cambia por provincia y por día: dos días no son
-- comparables entre sí. `diferencia` es cuánto más cara que la más barata (0 = la más barata); el
-- sitio agrupa como "las más baratas" a las que están a menos de 0,02.
with ultimo_dia as (
    select provincia, max(fecha) as fecha
    from {{ ref('fct_canasta_provincia_productos') }}
    group by provincia
),

productos as (
    select m.fecha, m.provincia, m.clave, m.mediana, d.grupo
    from {{ ref('fct_canasta_provincia_productos') }} m
    join ultimo_dia using (fecha, provincia)
    join {{ ref('dim_productos') }} d using (clave)
    where d.grupo is not null
            and d.grupo not in ('No supermercado', 'Frutas y verduras', 'Carnes y pescados', 'Panadería y rotisería')
),

por_cadena as (
    select p.fecha, p.provincia, pr.grupo, p.id_comercio,
           count(*)                            as productos_comparados,
           exp(avg(ln(p.precio / pr.mediana))) as indice
    from {{ ref('int_canasta_provincia_precios') }} p
    join productos pr using (fecha, provincia, clave)
    group by p.fecha, p.provincia, pr.grupo, p.id_comercio
    having count(*) >= {{ var('minimo_productos_grupo', 30) }}
)

select
    fecha,
    provincia,
    grupo,
    id_comercio,
    productos_comparados,
    round(indice, 6)                                                                         as indice,
    round(indice / min(indice) over (partition by fecha, provincia, grupo) - 1, 6)            as diferencia,
    rank() over (partition by fecha, provincia, grupo order by indice)                       as puesto
from por_cadena
