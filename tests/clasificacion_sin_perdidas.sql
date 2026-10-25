-- Todo producto de dim_productos tiene que tener una fila en la clasificación (aunque sea "sin
-- clasificar"), y toda corrección manual tiene que apuntar a un producto que existe.
select clave, 'sin fila en la clasificación' as problema
from (select clave from {{ ref('int_productos') }} except select clave from {{ ref('clasificacion_productos') }})
union all
select clave, 'corrección manual de un producto que no existe' as problema
from (select clave from {{ ref('rubros_manuales') }} except select clave from {{ ref('int_productos') }})
