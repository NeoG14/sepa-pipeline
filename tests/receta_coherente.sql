-- Devuelve las filas que están mal: una receta con total fuera de lo razonable (entre $ 2.000 y $ 200.000 para
-- 4 porciones), con más estimado que total, o repetida para la misma provincia y cadena.
select provincia, id_comercio, receta, total, costo_estimado
from {{ ref('fct_receta_provincia') }}
where (total is not null and (total not between 2000 and 200000 or costo_estimado > total))
   or (provincia, id_comercio, receta) in (
        select provincia, id_comercio, receta from {{ ref('fct_receta_provincia') }}
        group by all having count(*) > 1)
