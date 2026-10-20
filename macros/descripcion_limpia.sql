{#
  La descripción con espacios simples y sin el código de envase que agrega la cadena 9 al final
  ("BOT-250-ml.", "PAQ-100-gr.", "CJA-6-un."). Es ENVASE-cantidad-unidad y a veces aparece repetido.
  Casi siempre va separado por un espacio; cuando la cadena corta el nombre, queda pegado al
  texto ("MalbecBOT-750-cc."). Ese caso solo se saca si está al final y el envase tiene 3 letras
  mayúsculas, para no comerse letras del nombre. Si no queda nada, devuelve null.
#}
{% macro descripcion_limpia(descripcion) %}
    nullif(
        trim(regexp_replace(
            regexp_replace(
                regexp_replace({{ descripcion }}, '(^|\s+)[A-Za-z]{2,4}-[0-9]+([.,][0-9]+)?-[A-Za-z]+\.?', '', 'g'),
                '[A-Z]{3}-[0-9]+([.,][0-9]+)?-[A-Za-z]+\.?\s*$', ''),
            '\s+', ' ', 'g')),
        '')
{% endmacro %}