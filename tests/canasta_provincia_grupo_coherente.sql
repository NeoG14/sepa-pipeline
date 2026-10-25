-- El ranking por grupo es un pedazo del ranking general de la provincia, no un cálculo aparte:
--  1. cada grupo tiene las mismas cadenas que el ranking general ese día;
--  2. ningún grupo tiene más productos que la comparación entera;
--  3. un grupo no puede tener cadenas con distinta cantidad de productos (todas comparan los mismos).
-- Devuelve las filas que fallan; vacío = bien.
with por_grupo as (
    select * from {{ ref('fct_canasta_provincia_grupo') }}
),
general as (
    select g.fecha, g.provincia, g.id_comercio, g.cadenas, g.productos_comparados
    from {{ ref('fct_canasta_provincia') }} g
    join (select provincia, max(fecha) as fecha from por_grupo group by provincia) u using (provincia, fecha)
)
select 'faltan cadenas' as problema, pg.provincia, pg.grupo, null::int as valor
from por_grupo pg
group by pg.provincia, pg.grupo
having count(*) <> (select max(cadenas) from general where general.provincia = pg.provincia)

union all
select 'más productos que la comparación', pg.provincia, pg.grupo, pg.productos_comparados
from por_grupo pg
join general using (provincia, id_comercio)
where pg.productos_comparados > general.productos_comparados

union all
select 'cadenas con distinta cantidad', provincia, grupo, max(productos_comparados)
from por_grupo
group by provincia, grupo
having min(productos_comparados) <> max(productos_comparados)
