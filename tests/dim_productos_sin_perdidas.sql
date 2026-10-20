-- Todo producto que aparece en los Parquet tiene que estar en dim_productos.
select clave from {{ ref('stg_productos') }}
except
select clave from {{ ref('dim_productos') }}