# Data dictionary — gold layer

Dimensional model (star schema), views and analysis results. Model diagram:
[`warehouse_model.md`](warehouse_model.md) / [`warehouse_model.png`](warehouse_model.png).
Other layers: [bronze](data_dictionary_bronze.md) · [silver](data_dictionary_silver.md).

| Object | Loaded by | Defined in |
| --- | --- | --- |
| `dim_entidad`, `dim_tiempo`, `dim_pais`, `fact_valor_entidad`, `fact_comercio_electronico`, `fact_oecd_tic` | `src/silver_to_gold.py` → `sql/gold/gold.sql` | `sql/init.sql` |
| `dim_indicador`, `fact_encuesta_tic` | `src/silver_to_gold.py` (Python: survey estimation) | `sql/init.sql` |
| Views `kpi_entidad_anio`, `valor_entidad_anio`, `comercio_electronico_anio` | `sql/gold/gold.sql` | `sql/gold/gold.sql` |
| Tables `resultado_*` | `src/gold_analytics.py` | `sql/init.sql` |

Facts carry lineage: `fuente`, `version_fuente` (from silver), `fecha_carga`, `run_id` (this run;
joins with `gold.etl_log`).

---

## Dimensions

### `gold.dim_entidad` — 33 rows

| Column | Type | Description |
| --- | --- | --- |
| `cve_ent` | CHAR(2) PK | `'00'` national, `'01'`–`'32'` states |
| `nombre` | TEXT | Name (`México (nacional)` for `'00'`) |
| `es_foco` | BOOLEAN | Yucatán, Tabasco and national |

### `gold.dim_tiempo` — 23 rows (2003–2025)

| Column | Type | Description |
| --- | --- | --- |
| `anio` | SMALLINT PK | Year (union of all sources' years) |
| `sexenio` | TEXT | Federal administration period, e.g. `2018-2024` |

### `gold.dim_indicador` — 23 rows

| Column | Type | Description |
| --- | --- | --- |
| `id_indicador` | TEXT PK | See table below |
| `nombre`, `descripcion` | TEXT | Label and definition (with ENDUTIH question) |
| `dimension` | TEXT | `acceso`, `uso`, `valor`, `brecha` |
| `unidad`, `universo` | TEXT | e.g. `% de los usuarios de internet` / `Usuarios de internet de 6+` |
| `fuente` | TEXT | `INEGI ENDUTIH`, `INEGI PIBE`, `INEGI VABCOEL` |
| `orden` | SMALLINT | Display order |

Indicators:

| ID | Dimension | Universe (denominator) |
| --- | --- | --- |
| `hog_internet`, `hog_computadora`, `hog_internet_fija`, `hog_celular` | acceso | Households |
| `pob_smartphone` | acceso | Persons 6+ |
| `pob_internet`, `pob_computadora`, `pob_celular`, `pob_redes_sociales`, `pob_compra`, `pob_banca` | uso | Persons 6+ |
| `usu_compra`, `usu_vende`, `usu_paga`, `usu_banca` | uso | Internet users 6+ |
| `sin_internet_recursos`, `sin_internet_no_interesa`, `sin_internet_no_sabe`, `sin_internet_sin_proveedor` | brecha | Households without internet |
| `vab51_participacion`, `vab51_participacion_no_minero`, `vab51_crecimiento_real` | valor | State economy (PIB estatal) |
| `vabcoel_pct_pib` | valor | National economy |

### `gold.dim_pais` — 45 rows

| Column | Type | Description |
| --- | --- | --- |
| `cod_pais` | TEXT PK | ISO-3 code or aggregate (`OECD`, `EU27`, `EU28`) |
| `nombre` | TEXT | Name (English, as published by OECD) |

---

## Facts

### `gold.fact_encuesta_tic` — 3,160 rows

**Grain:** year × state × indicator × age group. ENDUTIH 2020–2024; `grupo_edad = 'total'` for
the 33 areas, `'16_74'` national only (comparable with OECD).

| Column | Type | Description |
| --- | --- | --- |
| `anio`, `cve_ent`, `id_indicador`, `grupo_edad` | PK / FK | |
| `estimacion` | DOUBLE | Weighted proportion, percent: Σ w·d·y / Σ w·d |
| `error_estandar` | DOUBLE | Taylor-linearized SE, strata `est_dis`, PSUs `upm_dis`, with replacement |
| `cv` | DOUBLE | Coefficient of variation, percent |
| `li_90`, `ls_90` | DOUBLE | 90% confidence interval (INEGI's level), clipped to [0, 100] |
| `calidad` | TEXT | `alta` (CV < 15), `moderada` (15–30), `baja` (> 30) |
| `n_muestra` | INTEGER | Sample records in the denominator |
| `numerador_expandido`, `universo_expandido` | BIGINT | Expanded totals (households or persons) |

### `gold.fact_valor_entidad` — 4,158 rows

**Grain:** year × state × concept × prices. Same columns as `silver.pib_entidad`.

### `gold.fact_comercio_electronico` — 228 rows

**Grain:** year × component × measure (national). Same columns as `silver.vabcoel`.

### `gold.fact_oecd_tic` — 3,656 rows

**Grain:** year × country × measure. Same columns as `silver.oecd_ict` (FK to `dim_pais`).

---

## Views

### `gold.valor_entidad_anio` — year × state

| Column | Formula |
| --- | --- |
| `vab_total`, `vab_51`, `vab_21` | Current prices, millions of pesos |
| `vab_51_real`, `vab_total_real` | 2018 prices |
| `participacion_51` | 100 × VAB 51 / VAB total |
| `participacion_51_no_minero` | 100 × VAB 51 / (VAB total − VAB 21) — D19 |
| `participacion_21` | 100 × VAB 21 / VAB total |
| `crecimiento_real_51`, `crecimiento_real_total` | Annual % change at 2018 prices |

### `gold.comercio_electronico_anio` — year

`vab_coel_mdp`, `vab_coel_real_mdp`, `pct_pib`, `pct_vab`, `mayor_mdp`, `menor_mdp`,
`otros_servicios_mdp`, `pct_del_comercio_al_por_menor`, `estatus_cifra`.

### `gold.kpi_entidad_anio` — year × state (2020–2024)

One column per survey indicator (`grupo_edad = 'total'`) plus `participacion_51`,
`participacion_51_no_minero` and `crecimiento_real_51` of the same year (NULL in 2024: no state
GDP yet).

---

## Analysis results (`src/gold_analytics.py`)

| Table | Grain | Content |
| --- | --- | --- |
| `resultado_brecha` | year × indicator × pair | Difference (pp) Yucatán−Tabasco, Yucatán−national, Tabasco−national; z-test at 90%. vs national: V(e−n) = V(e) + V(n) − 2·s·V(e), s = state share of the national universe |
| `resultado_tendencia` | focus state × indicator | First vs last ENDUTIH year (independent samples), p-value, OLS slope in pp/year |
| `resultado_ranking` | year × indicator × state | Rank among the 32 states (1 = highest), survey and sector-51 indicators |
| `resultado_validacion_oecd` | year × OECD measure | ENDUTIH national estimate vs Mexico's OECD figure, difference and whether it falls in the 90% CI |
| `etl_log` | run × table | Rows loaded and estimates by quality class |
