-- Cuánto sale cada receta en cada cadena y provincia el último día: el total, el costo por porción y cuánto
-- del total es estimado (ingredientes que la cadena no informa y se completan con la mediana de las otras).
-- `total` es null si falta algún ingrediente que ninguna otra cadena alcanza a estimar.
select
    fecha, provincia, id_comercio, receta,
    any_value(porciones)                                       as porciones,
    case when count(*) filter (where costo is null) = 0 then sum(costo) end                         as total,
    case when count(*) filter (where costo is null) = 0 then sum(costo) / any_value(porciones) end  as por_porcion,
    count(*)                                                   as ingredientes,
    count(*) filter (where estimado)                           as estimados,
    coalesce(sum(costo) filter (where estimado), 0)            as costo_estimado
from {{ ref('int_receta_linea') }}
group by fecha, provincia, id_comercio, receta
