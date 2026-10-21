-- Ningún precio de lista puede ser cero o negativo: rompería las medianas sin que se note.
-- Medido el 20/10: 0 casos en 15,1 millones de filas.
select fecha, id_comercio, id_producto, provincia, precio_lista_min
from {{ ref('int_precios_dia') }}
where precio_lista_min <= 0