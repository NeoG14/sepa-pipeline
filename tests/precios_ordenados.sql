-- Falla si en algún registro el mínimo supera a la mediana o la mediana supera al máximo.
select *
from {{ ref('int_precios_dia') }}
where precio_lista_min > precio_lista_mediana
   or precio_lista_mediana > precio_lista_max