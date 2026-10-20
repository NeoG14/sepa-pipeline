-- Precios tal como vienen de la ingesta, con solo las columnas que usa el proyecto.
select
    fecha,
    id_comercio,
    id_bandera,
    id_sucursal,
    id_producto,
    precio_lista,
    precio_promo1,
    precio_promo2
from {{ source('sepa', 'precios') }}