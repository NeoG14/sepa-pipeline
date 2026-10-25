-- La cantidad de productos del ranking de cada provincia es la de su lista de productos: el sitio
-- muestra las dos cosas y tienen que coincidir.
with lista as (
    select fecha, provincia, count(*) as productos
    from {{ ref('fct_canasta_provincia_productos') }}
    group by fecha, provincia
)
select r.fecha, r.provincia, r.productos_comparados, l.productos
from {{ ref('fct_canasta_provincia') }} r
left join lista l using (fecha, provincia)
where l.productos is distinct from r.productos_comparados
