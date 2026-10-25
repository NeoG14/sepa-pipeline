{#
  Devuelve los pares [fecha, fecha anterior] que fct_indice_cadena tiene que calcular en esta corrida, como mucho `maximo`.

  - La fecha anterior es la anterior con datos en el agregado diario (int_precios_dia), que guarda ~21 días.
  - En una corrida incremental, saca los pares que el modelo ya tiene. Un día que llega tarde (como el 16/10) se calcula
    cuando llega, y el día siguiente se recalcula porque su fecha anterior cambió.
  - El tope existe por la memoria: calcular los 20 pares de la primera corrida juntos agotó la memoria (Out of Memory,
    en una PC con la base de ~15 millones de filas del agregado). Con 3 por corrida alcanza; la primera vez se corre
    el modelo varias veces hasta completar, y después es un día por corrida.
  - Las fechas salen como constantes para que DuckDB lea solo esos días del agregado y no los 21.
#}
{% macro pares_indice(maximo) %}
    {% if not execute %}
        {{ return([]) }}
    {% endif %}
    {% set consulta %}
        with dias as (
            select fecha, lag(fecha) over (order by fecha) as anterior
            from (select distinct fecha from {{ ref('int_precios_dia') }})
        )
        select cast(d.fecha as varchar), cast(d.anterior as varchar)
        from dias d
        {% if is_incremental() %}
        left join (select distinct fecha, fecha_anterior from {{ this }}) t on t.fecha = d.fecha
        {% endif %}
        where d.anterior is not null
        {% if is_incremental() %}
          and (t.fecha is null or t.fecha_anterior <> d.anterior)
        {% endif %}
        order by d.fecha
        limit {{ maximo }}
    {% endset %}
    {{ return(run_query(consulta).rows | map('list') | list) }}
{% endmacro %}
