-- El costo de cada ingrediente de cada receta, por provincia y cadena, el último día de cada provincia.
--
-- Qué lleva cada receta lo dice la seed `recetas` (cantidad en kg o litros). De dónde sale el precio:
--  - fuente `kilo`: el precio por kilo de fct_precio_kilo_provincia. Si la línea tiene `opciones` ("Paleta|Roast
--    beef|Osobuco|Falda"), cada cadena usa la opción más barata que informa.
--  - fuente `envasado`: el producto equivalente más barato de la cadena (seed `ingrediente_producto`, que arma
--    scripts/clasificar_ingredientes.py), con la misma regla de cobertura (5 % de las sucursales) y el mismo
--    control de errores de carga (entre un cuarto y cuatro veces la mediana del ingrediente) que el precio por kilo.
-- Si una cadena no informa el ingrediente, se estima con la mediana de las demás cadenas de la provincia, pero
-- solo si al menos `cadenas_minimas_estimacion` (3) cadenas lo informan: con dos, la "mediana" es el promedio de
-- dos precios y no dice nada. El costo queda marcado como estimado.
{% set minima = var('cobertura_minima_producto', 0.05) %}
{% set cadenas_minimas = var('cadenas_minimas_estimacion', 3) %}

with ultimo_dia as (
    select provincia, max(fecha) as fecha
    from {{ ref('int_cobertura_dia') }}
    group by provincia
),

cadenas as (
    select distinct c.provincia, c.id_comercio, c.fecha
    from {{ ref('int_cobertura_dia') }} c
    join ultimo_dia u on u.provincia = c.provincia and u.fecha = c.fecha
),

productos_envasados as (
    select p.provincia, p.id_comercio, s.ingrediente,
           p.precio_lista_mediana / s.tamano as precio_unidad
    from {{ ref('int_precios_dia') }} p
    join {{ ref('ingrediente_producto') }} s
      on s.id_comercio = p.id_comercio and s.id_producto = p.id_producto
    join {{ ref('int_cobertura_dia') }} c
      on c.fecha = p.fecha and c.id_comercio = p.id_comercio and c.provincia = p.provincia
    join ultimo_dia u on u.provincia = p.provincia and u.fecha = p.fecha
    where p.sucursales >= {{ minima }} * c.sucursales
),

medianas as (
    select provincia, ingrediente, median(precio_unidad) as mediana
    from productos_envasados
    group by all
),

envasados as (
    select e.provincia, e.id_comercio, e.ingrediente, min(e.precio_unidad) as precio_unidad
    from productos_envasados e
    join medianas m using (provincia, ingrediente)
    where e.precio_unidad between m.mediana / 4 and m.mediana * 4
    group by all
),

lineas as (
    select receta, porciones, ingrediente, cantidad, fuente,
           case when coalesce(opciones, '') = '' then [ingrediente] else string_split(opciones, '|') end as productos
    from {{ ref('recetas') }}
),

opciones as (
    select receta, ingrediente, unnest(productos) as producto
    from lineas
    where fuente = 'kilo'
),

frescos as (
    select o.receta, o.ingrediente, k.provincia, k.id_comercio, min(k.precio_kg) as precio_unidad,
           arg_min(o.producto, k.precio_kg) as producto_elegido
    from opciones o
    join {{ ref('fct_precio_kilo_provincia') }} k on k.producto = o.producto
    group by all
),

con_precio as (
    select c.fecha, c.provincia, c.id_comercio, l.receta, l.porciones, l.ingrediente, l.cantidad,
           coalesce(e.precio_unidad, f.precio_unidad) as precio_unidad,
           f.producto_elegido
    from lineas l
    cross join cadenas c
    left join envasados e
      on l.fuente = 'envasado' and e.provincia = c.provincia and e.id_comercio = c.id_comercio and e.ingrediente = l.ingrediente
    left join frescos f
      on l.fuente = 'kilo' and f.provincia = c.provincia and f.id_comercio = c.id_comercio
     and f.receta = l.receta and f.ingrediente = l.ingrediente
),

con_estimado as (
    select *,
           count(precio_unidad) over (partition by provincia, receta, ingrediente) as cadenas_con_precio,
           median(precio_unidad) over (partition by provincia, receta, ingrediente) as mediana
    from con_precio
)

select fecha, provincia, id_comercio, receta, porciones, ingrediente, cantidad, producto_elegido,
       coalesce(precio_unidad, case when cadenas_con_precio >= {{ cadenas_minimas }} then mediana end) as precio_unidad,
       precio_unidad is null                                                       as estimado,
       cantidad * coalesce(precio_unidad, case when cadenas_con_precio >= {{ cadenas_minimas }} then mediana end) as costo
from con_estimado
