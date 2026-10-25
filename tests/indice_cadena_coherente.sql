-- Una fila por fecha, provincia y cadena; el cambio de un día al siguiente es razonable (entre -10 % y +10 %: una
-- cadena que sube todo un 10 % de un día para otro es un error de datos) y tiene productos para promediar.
-- Devuelve las filas que fallan; vacío = bien.
select 'repetido' as problema, fecha, provincia, id_comercio, count(*)::double as valor
from {{ ref('fct_indice_cadena') }}
group by fecha, provincia, id_comercio
having count(*) > 1

union all
select 'cambio fuera de rango', fecha, provincia, id_comercio, factor
from {{ ref('fct_indice_cadena') }}
where factor not between 0.9 and 1.1

union all
select 'sin productos', fecha, provincia, id_comercio, productos::double
from {{ ref('fct_indice_cadena') }}
where productos < 1 or factor is null
