-- Canasta por provincia: ranking del día de las cadenas de cada provincia, con un índice de precios.
--
-- Productos: los de fct_canasta_provincia_productos, todos los códigos de barras que tienen TODAS las
-- cadenas de la provincia ese día con un precio representativo (el 21/10: 591 en Buenos Aires, con 7
-- cadenas, y miles donde hay 2). Antes eran solo los de la canasta fija de 31 que tenían todas (de 19 a 31): muy pocos para
-- ordenar las cadenas del medio. Medido con scripts/medir_canasta_provincial.py.
--
-- Índice: en cada producto, el precio de la cadena dividido por la mediana de ese producto entre las
-- cadenas de la provincia; después, la media geométrica por cadena. Cada producto pesa lo mismo, sea
-- caro o barato, y un error en un solo producto mueve poco el resultado. 1 = la mediana; 0,973 =
-- 2,7 % por debajo. `diferencia` es cuánto más cara que la más barata (0 = la más barata). `total`,
-- la suma de los precios, queda como referencia: no ordena.
--
-- El conjunto de productos cambia por provincia y por día (los martes DIA informa menos): sirve para
-- comparar cadenas dentro de una provincia en una fecha, no provincias entre sí ni una serie de
-- tiempo; para eso está la canasta nacional fija. Se arma con los días que guarda el agregado diario.
with precios as (
    select * from {{ ref('int_canasta_provincia_precios') }}
),

cadenas as (
    select fecha, provincia, count(distinct id_comercio) as cadenas
    from precios
    group by fecha, provincia
),

por_cadena as (
    select p.fecha, p.provincia, p.id_comercio,
           count(*)                            as productos_comparados,
           exp(avg(ln(p.precio / m.mediana)))  as indice,
           sum(p.precio)                       as total
    from precios p
    join {{ ref('fct_canasta_provincia_productos') }} m using (fecha, provincia, clave)
    group by p.fecha, p.provincia, p.id_comercio
)

select
    p.fecha,
    p.provincia,
    p.id_comercio,
    c.cadenas,
    p.productos_comparados,
    round(p.indice, 6)                                                               as indice,
    round(p.indice / min(p.indice) over (partition by p.fecha, p.provincia) - 1, 6)  as diferencia,
    round(p.total, 2)                                                                as total,
    rank() over (partition by p.fecha, p.provincia order by p.indice)                as puesto
from por_cadena p
join cadenas c using (fecha, provincia)
