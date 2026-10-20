{#
  El código de envase que la cadena 9 agrega al final de la descripción: ENVASE-cantidad-unidad
  ("LAT-473-ml."). Se guarda tal como lo informa la cadena, sin interpretarlo ni validarlo,
  porque a veces no coincide con el nombre ("BOT-1-un." en un frasco de 250 ml) ni con lo que dicen
  otras cadenas. Igual que en descripcion_limpia, el código pegado al texto solo se reconoce al
  final y con 3 letras mayúsculas. Si la descripción no lo tiene, devuelven null.
#}
{% macro codigo_envase(descripcion) %}
    coalesce(
        nullif(regexp_extract({{ descripcion }}, '(?:^|\s)([A-Za-z]{2,4}-[0-9]+(?:[.,][0-9]+)?-[A-Za-z]+)', 1), ''),
        nullif(regexp_extract({{ descripcion }}, '([A-Z]{3}-[0-9]+(?:[.,][0-9]+)?-[A-Za-z]+)\.?\s*$', 1), ''))
{% endmacro %}

{% macro envase_cadena(descripcion) %}
    upper(split_part({{ codigo_envase(descripcion) }}, '-', 1))
{% endmacro %}

{% macro presentacion_cadena(descripcion) %}
    nullif(
        split_part({{ codigo_envase(descripcion) }}, '-', 2) || ' ' || lower(split_part({{ codigo_envase(descripcion) }}, '-', 3)),
        ' ')
{% endmacro %}