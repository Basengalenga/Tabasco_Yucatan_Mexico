# Data dictionary — silver layer

Clean, typed and harmonized data, one table per source. Loaded by `src/bronze_to_silver.py`;
DDL in `sql/init.sql`; post-load checks in `validaciones/silver.sql`. Other layers:
[bronze](data_dictionary_bronze.md) · [gold](data_dictionary_gold.md). Decision IDs (`Dxx`)
refer to [`decisiones_limpieza.md`](decisiones_limpieza.md).

**Silver rules**

- Geographic key: `cve_ent CHAR(2)`; `'00'` = national (D08).
- ENDUTIH answers `1 = Sí / 2 = No` → `BOOLEAN`; any other code stops the pipeline.
- Every table is reloaded with TRUNCATE + INSERT in a single transaction.
- Lineage columns in every table except `etl_log`: `fuente`, `version_fuente`, `fecha_carga`.

---

## `silver.cat_entidad`

**Grain:** state. **Rows:** 33. **From:** `bronze.endutih_cat_entidad` + national row.

| Column | Type | Description |
| --- | --- | --- |
| `cve_ent` | CHAR(2) PK | State code; `'00'` national |
| `nombre` | TEXT | Official name (`Estados Unidos Mexicanos` for `'00'`) |
| `nombre_normalizado` | TEXT UNIQUE | Lower case, no accents (used only to key the state GDP, D16) |
| `es_foco` | BOOLEAN | TRUE for `'00'`, `'27'` Tabasco, `'31'` Yucatán |

## `silver.endutih_mapeo_variables`

**Grain:** year × concept × column. **Rows:** 80. Which source column measures each concept each
year, with the INEGI dictionary text that validated it (D06).

| Column | Type | Description |
| --- | --- | --- |
| `anio` | SMALLINT | Survey year |
| `concepto` | TEXT | `internet`, `computadora`, `compra_internet`, ... |
| `tabla_bronze` | TEXT | e.g. `endutih_usuarios_2023` |
| `columna` | TEXT | e.g. `p7_21` |
| `descripcion_diccionario` | TEXT | Question text from the INEGI data dictionary |

## `silver.endutih_hogar`

**Grain:** interviewed household × year. **Rows:** 292,981 (2020–2024). **From:**
`bronze.endutih_hogares_<anio>`.

| Column | Type | Description |
| --- | --- | --- |
| `anio`, `upm`, `viv_sel`, `hogar` | PK | Year and household keys (zero-padded, D07) |
| `cve_ent` | CHAR(2) FK | State |
| `est_dis`, `upm_dis` | TEXT | Design stratum and PSU |
| `tloc` | SMALLINT | Locality size (1 = 100k+ inhabitants … 4 = rural) |
| `fac_hog` | INTEGER > 0 | Household expansion factor |
| `tiene_computadora` | BOOLEAN | Desktop **or** laptop **or** tablet (D11) |
| `tiene_internet` | BOOLEAN | Internet connection at home (P4_4) |
| `internet_fija` | BOOLEAN NULL | Fixed or fixed+mobile connection; FALSE without internet; NULL = "no sabe" (D12) |
| `tiene_celular` | BOOLEAN | Any member has a mobile phone (P4_1_6) |
| `razon_sin_internet` | SMALLINT NULL | Main reason without internet, P4_8 code 1–10 (1 lack of money, 2 not interested, 3 don't know how to use it, 6 no provider…); NULL when connected |

## `silver.endutih_persona`

**Grain:** selected informant aged 6+ × year (one per household). **Rows:** 292,981. **From:**
`bronze.endutih_usuarios_<anio>` joined 1:1 with `bronze.endutih_usuarios2_<anio>`.

| Column | Type | Description |
| --- | --- | --- |
| `anio`, `upm`, `viv_sel`, `hogar`, `num_ren` | PK | Year and person keys |
| `cve_ent`, `est_dis`, `upm_dis`, `tloc` | | As in households |
| `fac_per` | INTEGER > 0 | Person expansion factor |
| `edad`, `sexo` | SMALLINT | Age (≥ 6, validated), sex (1 man, 2 woman) |
| `usa_internet` | BOOLEAN | Used internet in the last 3 months (P7_1) |
| `usa_computadora` | BOOLEAN | Used a computer/laptop/tablet in the last 3 months (P6_1) |
| `usa_celular` | BOOLEAN | Used a mobile phone in the last 3 months (P8_3) |
| `usa_smartphone` | BOOLEAN | The phone used is a smartphone; FALSE if no phone (D18) |
| `usa_redes_sociales` | BOOLEAN | Used social networks, last 3 months; FALSE for non-users (D13) |
| `compra_internet` | BOOLEAN | Bought online, last 12 months (D13) |
| `vende_internet` | BOOLEAN | Sold online, last 12 months (D13) |
| `paga_internet` | BOOLEAN | Paid online, last 12 months (D13) |
| `banca_electronica` | BOOLEAN | Used e-banking, last 3 months (D13) |

## `silver.vabcoel`

**Grain:** year × component × measure. **Rows:** 228 (2013–2024). **From:** `bronze.vabcoel`
(derived rows dropped, D10; component hierarchy fixed, D14).

| Column | Type | Description |
| --- | --- | --- |
| `anio` | SMALLINT | Year |
| `componente` | TEXT | `total`, `comercio_al_por_mayor`, `comercio_al_por_menor`, `otros_servicios` |
| `medida` | TEXT | `mdp_corrientes`, `mdp_constantes_2018`, `pct_pib`, `pct_vab`, `pct_vab_actividad` |
| `valor` | DOUBLE | Millions of pesos or percent |
| `estatus_cifra` | TEXT | `definitiva`, `revisada` (2023), `preliminar` (2024) |

## `silver.pib_entidad`

**Grain:** year × state × concept × prices. **Rows:** 4,158 (2003–2023 × 33 × 3 × 2). **From:**
`bronze.pibe` (derived presentations dropped, D15; keyed by name, D16).

| Column | Type | Description |
| --- | --- | --- |
| `anio`, `cve_ent` | PK | Year and state (`'00'` national) |
| `concepto` | TEXT | `vab_total`, `vab_51` (information in mass media), `vab_21` (mining) |
| `precios` | TEXT | `corrientes`, `constantes_2018` |
| `valor_mdp` | DOUBLE | Millions of pesos |
| `estatus_cifra` | TEXT | `definitiva`, `revisada` (2022), `preliminar` (2023) |

## `silver.oecd_ict`

**Grain:** year × country × measure. **Rows:** 3,656. **From:** `bronze.oecd_ict_hogares` +
`bronze.oecd_ict_individuos` (D17).

| Column | Type | Description |
| --- | --- | --- |
| `anio`, `cod_pais`, `medida` | PK | Year, ISO-3 / aggregate code (`OECD`, `EU27`), measure code |
| `pais`, `desc_medida` | TEXT | Labels |
| `unidad` | TEXT | `pct_hogares` or `pct_personas_16_74` |
| `valor` | DOUBLE 0–100 | Percent |
| `estatus_obs` | TEXT NULL | OECD observation status (normal, series break, definition differs, low reliability) |

## `silver.etl_log`

**Grain:** run × table × metric. Counts of every discard, recoding and cleaning decision.

| Column | Type | Description |
| --- | --- | --- |
| `run_id` | UUID | Silver run |
| `tabla`, `metrica` | TEXT | e.g. `endutih_hogar` / `tipo_conexion_no_sabe_a_null_2024` |
| `valor` | BIGINT | Records affected |
| `detalle` | TEXT | Human-readable explanation |
| `fecha_carga` | TIMESTAMPTZ | Run time |
