-- Ninguna marca puede ser un valor de "sin marca" ni quedar vacía: tiene que ser null.
select clave, marca
from {{ ref('dim_productos') }}
where marca in ('S/D', 'SD', 'GENERICO', 'SIN MARCA', '')