-- Un producto por clave (EAN sin ceros, o "comercio-código" para los códigos internos), con el
-- nombre, la marca, el texto de búsqueda para el sitio y el rubro y grupo de la clasificación
-- (null si no se pudo clasificar). Se arma con todas las fechas, así un producto que ya no se
-- vende conserva su nombre y su historia.
select
    p.clave,
    p.es_ean,
    p.nombre,
    p.marca,
    p.envase,
    p.presentacion,
    p.cadenas,
    p.primera_fecha,
    p.ultima_fecha,
    p.texto_busqueda,
    c.rubro,
    c.grupo,
    c.fuente as fuente_rubro
from {{ ref('int_productos') }} p
left join {{ ref('clasificacion_productos') }} c using (clave)
