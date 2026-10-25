-- Cada cadena aparece una sola vez por provincia y producto, el precio por kilo es razonable (entre $ 100 y
-- $ 500.000: un kilo de lo más barato, la naranja, cuesta mil pesos; lo más caro, el jamón crudo, unos 70.000)
-- y el mínimo no supera a la mediana. Devuelve las filas que fallan; vacío = bien.
select 'repetido' as problema, provincia, producto, id_comercio, count(*)::double as valor
from {{ ref('fct_precio_kilo_provincia') }}
group by fecha, provincia, producto, id_comercio
having count(*) > 1

union all
select 'precio fuera de rango', provincia, producto, id_comercio, precio_kg
from {{ ref('fct_precio_kilo_provincia') }}
where precio_kg not between 100 and 500000

union all
select 'mínimo mayor que la mediana', provincia, producto, id_comercio, minimo
from {{ ref('fct_precio_kilo_provincia') }}
where minimo > precio_kg
