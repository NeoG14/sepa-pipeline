-- Precio de cada cadena y producto (solo códigos de barras) por provincia y día, para la canasta
-- provincial, con la regla de cobertura en un solo lugar.
--
-- `representativo`: la cadena informa el producto en al menos `cobertura_minima_producto` (5 %) de
-- las sucursales que tiene en la provincia ese día (int_cobertura_dia). Si no, su mediana sale de
-- muy pocas sucursales y no es el precio que se encuentra en la cadena: el 21/10, Cencosud informaba
-- los bizcochos Don Satur en 2 de sus 70 sucursales de Buenos Aires a $ 300 (probable remate), contra
-- ~$ 1.500 en las demás cadenas. Con 5 %, la comparación de Buenos Aires pasa de 631 a 591 productos
-- y la del país de 41.670 a 41.332 (medido con scripts/medir_cobertura_producto.py).
-- Es una vista: son todos los precios de los 21 días del agregado (decenas de millones de filas);
-- guardarla como tabla ocuparía mucho disco para algo que solo leen los dos modelos de la canasta.
{{ config(materialized='view') }}
{% set minima = var('cobertura_minima_producto', 0.05) %}

with precios as (
    -- Una fila por cadena y producto: si una cadena informa el mismo EAN con y sin ceros adelante,
    -- se juntan (si no, contaría dos veces el mismo producto)
    select fecha, provincia, id_comercio,
           {{ clave_producto('id_producto', 'id_comercio') }} as clave,
           median(precio_lista_mediana)::double as precio,
           sum(sucursales)                      as sucursales
    from {{ ref('int_precios_dia') }}
    group by all
)

select p.fecha, p.provincia, p.id_comercio, p.clave, p.precio, p.sucursales,
       c.sucursales                               as sucursales_cadena,
       p.sucursales >= {{ minima }} * c.sucursales as representativo
from precios p
join {{ ref('int_cobertura_dia') }} c using (fecha, id_comercio, provincia)
-- Los códigos internos ("comercio-código") no se comparten entre cadenas
where p.clave not like '%-%'
