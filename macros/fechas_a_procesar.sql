{#
  Devuelve la lista de fechas que el agregado diario tiene que calcular en esta corrida.

  - Solo mira las últimas `dias` fechas del calendario, contando desde la fecha más nueva
    de los Parquet (con dias=21: esa fecha y las 20 anteriores).
  - En una corrida incremental, saca las fechas que el modelo ya tiene: así cada día procesa
    solo lo nuevo, aunque llegue tarde (como el 16/10, publicado tres días después).
  - La lista sale de stg_sucursales porque esos Parquet son chicos: leerlos es rápido.
#}
{% macro fechas_a_procesar(dias) %}
    {% if not execute %}
        {{ return([]) }}
    {% endif %}
    {% set consulta %}
        select distinct fecha
        from {{ ref('stg_sucursales') }}
        where fecha > (select max(fecha) - {{ dias }} from {{ ref('stg_sucursales') }})
        {% if is_incremental() %}
          and fecha not in (select distinct fecha from {{ this }})
        {% endif %}
        order by fecha
    {% endset %}
    {{ return(run_query(consulta).columns[0].values() | map('string') | list) }}
{% endmacro %}