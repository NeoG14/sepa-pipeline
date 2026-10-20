-- Productos tal como vienen de la ingesta (una fila por fecha, comercio y código), con la clave
-- comparable entre cadenas, la descripción sin el código de envase de la cadena 9 (que queda en
-- envase y presentacion) y la marca normalizada.
select
    fecha,
    id_comercio,
    id_producto,
    {{ clave_producto('id_producto', 'id_comercio') }} as clave,
    {{ descripcion_limpia('descripcion') }} as descripcion,
    {{ envase_cadena('descripcion') }} as envase,
    {{ presentacion_cadena('descripcion') }} as presentacion,
    {{ marca_limpia('marca') }} as marca
from {{ source('sepa', 'productos') }}