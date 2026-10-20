-- En cada provincia y fecha, todas las cadenas se comparan sobre la misma cantidad de productos.
select fecha, provincia
from {{ ref('fct_canasta_provincia') }}
group by fecha, provincia
having count(distinct productos_comparados) > 1