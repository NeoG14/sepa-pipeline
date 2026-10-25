-- En cada provincia y fecha, la diferencia contra la más barata nunca es negativa y la primera del
-- ranking tiene diferencia 0.
select fecha, provincia
from {{ ref('fct_canasta_provincia') }}
group by fecha, provincia
having min(diferencia) < 0
    or max(diferencia) filter (where puesto = 1) <> 0
