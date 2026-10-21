-- Cobertura de cada cadena en cada provincia y día: sucursales que informaron contra las habituales,
-- que son la mediana de los `dias_referencia_cobertura` días anteriores (28 por defecto). Solo días
-- anteriores: un día no se compara consigo mismo ni con el futuro.
--
-- cobertura_baja marca los días por debajo de `umbral_cobertura` (80 %). Medido del 9/10 al 21/10:
-- de 1.184 combinaciones, 1.180 estuvieron en 95 % o más; las 4 de abajo, domingos de la
-- Cooperativa Obrera, y entre 70 % y 90 % no hubo ningún caso. El primer día de cada cadena y
-- provincia no tiene con qué compararse y no se marca.
{% set dias = var('dias_referencia_cobertura', 28) %}
{% set umbral = var('umbral_cobertura', 0.8) %}

with referencia as (
    select
        *,
        median(sucursales) over (
            partition by id_comercio, provincia
            order by fecha
            range between interval {{ dias }} days preceding and interval 1 day preceding
        ) as habituales
    from {{ ref('int_cobertura_dia') }}
)

select
    fecha,
    id_comercio,
    provincia,
    sucursales,
    habituales,
    round(sucursales / habituales, 3)                         as cobertura,
    coalesce(sucursales / habituales < {{ umbral }}, false)   as cobertura_baja
from referencia