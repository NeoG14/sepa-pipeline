-- Aviso (no error) si una cadena informa en la fecha más nueva bastante más o menos filas que el
-- mismo día de la semana en las semanas anteriores, o si directamente no aparece.
--
-- Se compara contra el mismo día de la semana porque hay patrones semanales que son normales:
-- la cadena 13 informa ~22 % menos los domingos y la 15 ~9 % menos los martes. Contra los últimos
-- 7 días, el test avisaría todas las semanas. Es un aviso porque el problema es del portal: el
-- build tiene que seguir, y la canasta lo cubre arrastrando el último precio.
{{ config(severity = 'warn') }}
{% set umbral = var('umbral_volumen', 0.05) %}

with filas as (
    select fecha, id_comercio, count(*) as filas
    from {{ ref('int_precios_dia') }}
    group by fecha, id_comercio
),

ultima as (
    select max(fecha) as fecha from filas
),

referencia as (
    select f.id_comercio, median(f.filas) as referencia
    from filas f, ultima u
    where f.fecha < u.fecha
      and dayofweek(f.fecha) = dayofweek(u.fecha)
    group by f.id_comercio
)

select
    r.id_comercio,
    u.fecha,
    coalesce(f.filas, 0)                                                   as filas,
    r.referencia,
    round(100.0 * (coalesce(f.filas, 0) - r.referencia) / r.referencia, 1) as desvio
from referencia r
cross join ultima u
left join filas f on f.id_comercio = r.id_comercio and f.fecha = u.fecha
where abs(coalesce(f.filas, 0) - r.referencia) / r.referencia > {{ umbral }}