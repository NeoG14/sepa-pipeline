-- Precio por kilo de los productos cotidianos que se venden al peso (banana, asado, pollo entero...) en cada
-- cadena y provincia, solo para el último día de cada provincia.
--
-- Qué producto es cada pesable lo decide la seed `pesables_producto`, que arma scripts/clasificar_pesables.py
-- reconociendo el nombre: no usa el rubro, que se equivoca con los frescos. Cada fila de la seed trae
-- `factor_kg`, por cuánto se multiplica el precio de lista para tener el del kilo (1 si ya viene por kilo).
--
-- Por cadena y producto se guarda la mediana de los precios de sus pesables de esa categoría (una cadena
-- puede tener varias variedades de manzana roja) y cuántos son. Se descartan:
--  - los precios de una cadena que informa el producto en menos del `cobertura_minima_producto` (5 %) de
--    sus sucursales de la provincia, igual que en la canasta provincial;
--  - los que están a menos de un cuarto o a más de cuatro veces la mediana del producto en la provincia
--    (errores de carga: un chorizo a $ 274 el kilo).
--
-- Ofertas. Hay dos señales y no se pisan (en la medición de 15 días ningún caso las tuvo juntas):
--  - `baja_fuerte`: el precio de lista de hoy es un 20 % menor o más que la mediana de los 14 días anteriores
--    (con al menos 3 días de historia). Es lo que pasa en Coto con el cerdo: el precio de lista ya es el de oferta.
--  - `con_promo`: SEPA informa un precio de promoción en la mitad o más de las sucursales y es al menos
--    un 3 % menor que el de lista. El precio de lista no cambia; la promoción puede tener condiciones.
{% set minima = var('cobertura_minima_producto', 0.05) %}
{% set dias_antes = var('dias_oferta_antes', 14) %}
{% set baja = var('baja_oferta', 0.80) %}

with ultimo_dia as (
    select provincia, max(fecha) as fecha
    from {{ ref('int_cobertura_dia') }}
    group by provincia
),

base as (
    select p.fecha, p.provincia, p.id_comercio, s.producto, s.grupo,
           p.precio_lista_mediana * s.factor_kg                    as precio_kg,
           p.precio_promo1_mediana * s.factor_kg                   as promo_kg,
           p.sucursales_promo1 * 1.0 / p.sucursales                as parte_promo
    from {{ ref('int_precios_dia') }} p
    join {{ ref('pesables_producto') }} s
      on s.id_comercio = p.id_comercio and s.id_producto = p.id_producto
    join {{ ref('int_cobertura_dia') }} c
      on c.fecha = p.fecha and c.id_comercio = p.id_comercio and c.provincia = p.provincia
    where p.sucursales >= {{ minima }} * c.sucursales
),

precios as (
    select b.*
    from base b
    join ultimo_dia u on u.provincia = b.provincia and u.fecha = b.fecha
),

medianas as (
    select fecha, provincia, producto, median(precio_kg) as mediana
    from precios
    group by all
),

hoy as (
    select p.fecha, p.provincia, p.producto, any_value(p.grupo) as grupo, p.id_comercio,
           count(*)                       as productos,
           median(p.precio_kg)            as precio_kg,
           min(p.precio_kg)               as minimo,
           median(p.promo_kg)             as promo_kg,
           max(p.parte_promo)             as parte_promo
    from precios p
    join medianas m using (fecha, provincia, producto)
    where p.precio_kg between m.mediana / 4 and m.mediana * 4
    group by p.fecha, p.provincia, p.producto, p.id_comercio
),

diario as (
    select fecha, provincia, producto, id_comercio, median(precio_kg) as precio_kg
    from base
    group by all
),

antes as (
    select h.provincia, h.producto, h.id_comercio,
           median(d.precio_kg) as antes_kg,
           count(*)            as dias_antes
    from hoy h
    join diario d
      on d.provincia = h.provincia and d.producto = h.producto and d.id_comercio = h.id_comercio
     and d.fecha < h.fecha and d.fecha >= h.fecha - {{ dias_antes }}
    group by all
)

select h.fecha, h.provincia, h.producto, h.grupo, h.id_comercio, h.productos,
       round(h.precio_kg, 0)   as precio_kg,
       round(h.minimo, 0)      as minimo,
       round(a.antes_kg, 0)    as antes_kg,
       coalesce(a.dias_antes, 0) as dias_antes,
       round(h.promo_kg, 0)    as promo_kg,
       coalesce(a.dias_antes >= 3 and h.precio_kg <= a.antes_kg * {{ baja }}, false) as baja_fuerte,
       coalesce(h.parte_promo >= 0.5 and h.promo_kg < h.precio_kg * 0.97, false)     as con_promo
from hoy h
left join antes a using (provincia, producto, id_comercio)
