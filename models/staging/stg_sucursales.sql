-- Sucursales por fecha, con la provincia ya normalizada a código ISO por la ingesta.
select
    fecha,
    id_comercio,
    id_bandera,
    id_sucursal,
    provincia,
    sucursales_tipo
from {{ source('sepa', 'sucursales') }}