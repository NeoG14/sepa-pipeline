-- Un producto por clave (EAN sin ceros, o "comercio-código" para los códigos internos), con el
-- nombre, la marca y el texto de búsqueda para el sitio. Se arma con todas las fechas, así un
-- producto que ya no se vende conserva su nombre y su historia.
-- Es la base de dim_productos, que le suma el rubro: antes se llamaba dim_productos y se separó
-- porque la clasificación necesita la marca y el nombre, y dim_productos necesita la clasificación.
with filas as (
    select * from {{ ref('stg_productos') }}
),

-- Cuántos productos distintos tiene cada marca en todo el catálogo. Sirve para elegir entre
-- variantes: una abreviatura ("PRONT") la usan pocos productos, la marca completa ("PRONTO") muchos.
frecuencia_marca as (
    select marca, count(distinct clave) as productos
    from filas
    where marca is not null
    group by marca
),

-- La marca de cada producto: la variante más frecuente en el catálogo. Si empatan, la más larga.
marca_elegida as (
    select f.clave, f.marca
    from filas f
    join frecuencia_marca fm on fm.marca = f.marca
    qualify row_number() over (
        partition by f.clave
        order by fm.productos desc, length(f.marca) desc, f.marca
    ) = 1
),

productos as (
    select
        clave,
        not contains(clave, '-')                           as es_ean,
        arg_max(descripcion, length(descripcion))          as nombre,
        count(distinct id_comercio)                        as cadenas,
        mode(envase)                                       as envase,
        mode(presentacion)                                 as presentacion,
        min(fecha)                                         as primera_fecha,
        max(fecha)                                         as ultima_fecha,
        string_agg(distinct upper(strip_accents(trim(coalesce(descripcion, '') || ' ' || coalesce(marca, '')))), ' ')
                                                           as texto_busqueda
    from filas
    group by clave
)

select
    p.clave,
    p.es_ean,
    p.nombre,
    m.marca,
    p.envase,
    p.presentacion,
    p.cadenas,
    p.primera_fecha,
    p.ultima_fecha,
    p.texto_busqueda
from productos p
left join marca_elegida m using (clave)
