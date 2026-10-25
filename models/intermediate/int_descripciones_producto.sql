-- Lo que el clasificador de rubros lee de cada producto: la marca y la última descripción de
-- cada cadena, ordenadas por cadena. Es la misma consulta con la que se armaron las etiquetas
-- para entrenar (scripts/armar_entrenamiento.py): si cambia acá, el modelo ve un texto distinto
-- del que aprendió.
with ultima as (
    select clave, id_comercio, arg_max(descripcion, fecha) as descripcion
    from {{ ref('stg_productos') }}
    group by all
)

select
    u.clave,
    p.marca,
    p.cadenas,
    list(u.descripcion order by u.id_comercio) filter (where u.descripcion is not null) as descripciones
from ultima u
join {{ ref('int_productos') }} p using (clave)
group by all
