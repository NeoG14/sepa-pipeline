{#
  La marca normalizada: mayúsculas, sin acentos ni signos y con los espacios simples.
  Los valores que significan "sin marca" (los usan las cadenas 10 y 11) devuelven null.
  La lista se puede cambiar con la variable marcas_sin_dato.
#}
{% macro marca_limpia(marca) %}
    case
        when {{ marca }} is null then null
        when upper(trim({{ marca }})) in (
            {%- for valor in var('marcas_sin_dato', ['S/D', 'GENERICO', 'SIN MARCA']) -%}
                '{{ valor }}'{{ ", " if not loop.last }}
            {%- endfor -%}
        ) then null
        else nullif(
            trim(regexp_replace(
                regexp_replace(strip_accents(upper({{ marca }})), '[^A-Z0-9 ]', '', 'g'),
                ' +', ' ', 'g')),
            '')
    end
{% endmacro %}