-- La canasta nacional tiene que cerrar: nunca más productos que los de la canasta, y el total
-- existe solo cuando está completa.
with n as (select count(distinct ltrim(ean, '0')) as productos from {{ ref('canasta') }})
select f.*
from {{ ref('fct_canasta_nacional') }} f, n
where f.productos_observados + f.productos_arrastrados > n.productos
   or (f.completa and f.total is null)
   or (not f.completa and f.total is not null)