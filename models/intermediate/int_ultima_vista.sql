-- Última fecha en que se vio cada clave (comercio, producto, provincia) en el agregado diario.
-- Hace falta porque el historial guarda solo los cambios: un producto puede seguir
-- apareciendo durante meses con el mismo precio sin sumar filas al historial.
--
-- Es incremental: cada corrida actualiza las claves que aparecen en el agregado diario
-- (los últimos 21 días). Las que no aparecen conservan su última fecha.
-- full_refresh = false por lo mismo que el historial: el agregado diario no guarda lo viejo.
{{ config(
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = ['id_comercio', 'id_producto', 'provincia'],
    full_refresh = false
) }}

select
    id_comercio,
    id_producto,
    provincia,
    max(fecha) as ultima_fecha_vista
from {{ ref('int_precios_dia') }}
group by all
