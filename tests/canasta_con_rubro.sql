-- Los productos de la canasta básica tienen que tener rubro: si no, los modelos por rubro los
-- dejarían afuera. La clave del producto es el EAN sin ceros (macro clave_producto).
select c.ean, c.nombre, d.rubro, d.fuente_rubro
from {{ ref('canasta') }} c
left join {{ ref('dim_productos') }} d on d.clave = ltrim(c.ean, '0')
where d.rubro is null
