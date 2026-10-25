-- El rubro de cada producto. Gana, en este orden:
--   1. la corrección manual (rubros_manuales);
--   2. lo que dijo DeepSeek (seed rubros_llm, que arma scripts/clasificar_catalogo_llm.py);
--   3. la clasificación automática (regla o modelo), para los productos que DeepSeek todavía no vio
--      (los que entraron después de la última corrida del script).
-- DeepSeek va antes que las reglas porque en las 300 de prueba acertó más (91,6 % contra 86,4 % de la
-- combinación reglas + modelo) y con más cobertura (99,7 % contra 85,7 %). Los productos que no resuelve
-- nadie quedan con rubro null y fuente "sin clasificar".
select
    a.clave,
    coalesce(m.rubro, l.rubro, a.rubro)                  as rubro,
    r.grupo,
    case when m.clave is not null then 'manual'
         when l.clave is not null then 'deepseek'
         else a.fuente end                               as fuente,
    a.probabilidad,
    a.rubro_modelo,
    a.version,
    a.fecha
from {{ ref('clasificacion_automatica') }} a
left join {{ ref('rubros_manuales') }} m on m.clave = a.clave
left join {{ ref('rubros_llm') }} l on l.clave = a.clave
left join {{ ref('rubros') }} r on r.rubro = coalesce(m.rubro, l.rubro, a.rubro)
