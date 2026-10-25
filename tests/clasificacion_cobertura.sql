-- Aviso (no error) si la cobertura de la clasificación en los productos de 2 cadenas o más baja del
-- umbral. En la prueba final dio 92 % en comparables; el aviso salta bastante antes de que se note
-- en el sitio. Si salta, mirar qué productos nuevos quedan "sin clasificar" y pensar en reentrenar
-- (el análisis de errores del paso 6 lista los motivos más comunes).
{{ config(severity = 'warn') }}
{% set umbral = var('umbral_cobertura_rubros', 0.85) %}

select count(*) filter (where rubro is not null) / count(*)::double as cobertura, {{ umbral }} as umbral
from {{ ref('dim_productos') }}
where es_ean and cadenas >= 2
having count(*) filter (where rubro is not null) / count(*)::double < {{ umbral }}
