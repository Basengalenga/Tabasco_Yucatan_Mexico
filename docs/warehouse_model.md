# Warehouse model (gold layer)

Star schema of `economia_digital_dw.gold`, loaded by `src/silver_to_gold.py` (`sql/gold/gold.sql`
plus the design-based survey estimates computed in Python). DDL in `sql/init.sql`. Static image:
[`warehouse_model.png`](warehouse_model.png) (source: [`warehouse_model.dot`](warehouse_model.dot)).
Column details: [`data_dictionary_gold.md`](data_dictionary_gold.md).

```mermaid
erDiagram
    dim_entidad ||--o{ fact_encuesta_tic : "cve_ent"
    dim_tiempo ||--o{ fact_encuesta_tic : "anio"
    dim_indicador ||--o{ fact_encuesta_tic : "id_indicador"
    dim_entidad ||--o{ fact_valor_entidad : "cve_ent"
    dim_tiempo ||--o{ fact_valor_entidad : "anio"
    dim_tiempo ||--o{ fact_comercio_electronico : "anio"
    dim_tiempo ||--o{ fact_oecd_tic : "anio"
    dim_pais ||--o{ fact_oecd_tic : "cod_pais"

    dim_entidad {
        CHAR2 cve_ent PK "00 = national"
        TEXT nombre
        BOOLEAN es_foco "00, 27, 31"
    }
    dim_tiempo {
        SMALLINT anio PK
        TEXT sexenio
    }
    dim_indicador {
        TEXT id_indicador PK
        TEXT nombre
        TEXT dimension "acceso, uso, valor, brecha"
        TEXT unidad
        TEXT universo
        TEXT fuente
    }
    dim_pais {
        TEXT cod_pais PK
        TEXT nombre
    }
    fact_encuesta_tic {
        SMALLINT anio PK,FK
        CHAR2 cve_ent PK,FK
        TEXT id_indicador PK,FK
        TEXT grupo_edad PK "total, 16_74"
        DOUBLE estimacion "percent"
        DOUBLE error_estandar
        DOUBLE cv
        DOUBLE li_90
        DOUBLE ls_90
        TEXT calidad
        INTEGER n_muestra
        BIGINT universo_expandido
    }
    fact_valor_entidad {
        SMALLINT anio PK,FK
        CHAR2 cve_ent PK,FK
        TEXT concepto PK "vab_total, vab_51, vab_21"
        TEXT precios PK "corrientes, constantes_2018"
        DOUBLE valor_mdp
        TEXT estatus_cifra
    }
    fact_comercio_electronico {
        SMALLINT anio PK,FK
        TEXT componente PK
        TEXT medida PK
        DOUBLE valor
        TEXT estatus_cifra
    }
    fact_oecd_tic {
        SMALLINT anio PK,FK
        TEXT cod_pais PK,FK
        TEXT medida PK
        TEXT unidad
        DOUBLE valor
        TEXT estatus_obs
    }
```

## Grains

| Table / view | Type | Grain |
| --- | --- | --- |
| `dim_entidad` | dimension | state (32) + national `'00'` |
| `dim_tiempo` | dimension | year, 2003–2025 (union of all sources) |
| `dim_indicador` | dimension | indicator (19 survey + 4 value) |
| `dim_pais` | dimension | OECD country or aggregate (OECD, EU27, EU28) |
| `fact_encuesta_tic` | fact | year × state × indicator × age group (ENDUTIH 2020–2024) |
| `fact_valor_entidad` | fact | year × state × concept × prices (PIB estatal 2003–2023) |
| `fact_comercio_electronico` | fact | year × component × measure (national, 2013–2024) |
| `fact_oecd_tic` | fact | year × country × measure (2015–2025) |
| `kpi_entidad_anio` | view | year × state, survey indicators in columns + sector-51 value |
| `valor_entidad_anio` | view | year × state, sector-51 share (with and without mining), real growth |
| `comercio_electronico_anio` | view | year, national e-commerce GVA wide |
| `resultado_*` | results | see [`data_dictionary_gold.md`](data_dictionary_gold.md) |

**Why survey facts store estimates, not microdata.** Gold keeps one row per estimate with its
standard error, so every consumer (API, dashboard, figures) shows the same number with the same
uncertainty. The microdata stays in silver (`endutih_hogar`, `endutih_persona`), from which
`validaciones/gold.sql` recomputes the point estimates.
