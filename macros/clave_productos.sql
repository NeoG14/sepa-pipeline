{#
  La clave de un producto, la misma regla que usan medir_canasta, candidatos_canasta y medir_sitio:
  si el código es comparable (solo dígitos, 8 o más sin los ceros de la izquierda y no es un
  código de 13 dígitos que empiece con 2), la clave es el EAN sin ceros. Si no, es el código
  interno de una cadena: "comercio-código", que no se mezcla con el de otra cadena.
#}
{% macro clave_producto(codigo, comercio) %}
    case
        when regexp_full_match({{ codigo }}, '\d+')
         and length(ltrim({{ codigo }}, '0')) >= 8
         and not (length({{ codigo }}) = 13 and {{ codigo }} like '2%')
        then ltrim({{ codigo }}, '0')
        else {{ comercio }} || '-' || {{ codigo }}
    end
{% endmacro %}