# Data dictionary — bronze layer

Raw copy of each official source, loaded by `src/extractor_to_bronze.py`. Other layers:
[silver](data_dictionary_silver.md) · [gold](data_dictionary_gold.md). Every cleaning decision
applied later is documented in [`decisiones_limpieza.md`](decisiones_limpieza.md).

**Bronze rules**

- All source columns stored as `TEXT`, unmodified. Column names normalized to snake_case
  without accents (`2023<R>` → `2023_r`, `REF_AREA: Reference area` → `ref_area`).
- Each run replaces the tables (inside a transaction; a failed download never leaves a table
  half-loaded).
- The only byte-level change: CRLF → LF line endings before `COPY` (D05); no value changes.

**Lineage columns (all tables)**

| Column | Type | Description |
| --- | --- | --- |
| `_ingested_at` | TIMESTAMPTZ | Start of the batch (Airflow `logical_date`), same for all tables |
| `_source_url` | TEXT | Exact download URL |
| `_run_id` | TEXT | UUID of the run (uuid5 of the Airflow DAG run) |
| `_archivo` | TEXT | File inside the ZIP (ENDUTIH and dictionaries) |

---

## INEGI ENDUTIH — microdata (access and use indicators)

Encuesta Nacional sobre Disponibilidad y Uso de Tecnologías de la Información en los Hogares,
open data, 2020–2024. One table per file and year, with **exactly the columns of that year's file**
(question numbering changes between years; see D06).

| Table | Source file | Grain | Rows (2020 / 2024) | Columns |
| --- | --- | --- | --- | --- |
| `endutih_hogares_<anio>` | `tr_endutih_hogar(es)_anual_<anio>.csv` | household | 58,154 / 58,080 | 84–104 |
| `endutih_usuarios_<anio>` | `tr_endutih_usuario(s)_anual_<anio>.csv` | selected person 6+ (one per household) | 58,154 / 58,080 | 226–231 |
| `endutih_usuarios2_<anio>` | `tr_endutih_usuario(s)2_anual_<anio>.csv` | same person, mobile-phone module | 58,154 / 58,080 | 80–95 |
| `endutih_diccionario` | `diccionario_de_datos_*.csv` | column × table × year | 2,065 | — |
| `endutih_cat_entidad` | `catalogo/tc_endutih_entidad.csv` (2024 ZIP) | state | 32 | — |

Columns used downstream (names as in the files):

| Column | Meaning |
| --- | --- |
| `upm`, `viv_sel`, `hogar`, `num_ren` | Household / person keys |
| `ent` (2020–2023), `cve_ent` (2024) | State code |
| `est_dis`, `upm_dis` | Design stratum and primary sampling unit (for standard errors) |
| `fac_hog`, `fac_per` | Expansion factors (households / persons) |
| `tloc`, `edad`, `sexo` | Locality size, age, sex |
| `p4_*` | Household equipment and connection (see `silver.endutih_mapeo_variables`) |
| `p6_1`, `p7_*`, `p8_*` | Computer, internet and mobile-phone use |

Source: `https://www.inegi.org.mx/contenidos/programas/{dutih|endutih}/<anio>/datosabiertos/conjunto_de_datos_endutih_<anio>_csv.zip`.

## INEGI — Valor Agregado Bruto del Comercio Electrónico (value indicator)

### `bronze.vabcoel`

Satellite estimate of the national accounts (SCNM, base 2018), national only, 2013–2024.
**Rows:** 43 (7 tabulations). Wide: one row per descriptor, one column per year.

| Column | Description |
| --- | --- |
| `descriptores` | `unit|concept|component<note>`, e.g. `Millones de pesos a precios corrientes|Valor agregado bruto|Comercio al por mayor` |
| `2013` … `2022`, `2023_r`, `2024_p` | Value per year (`_r` revised, `_p` preliminary); `NA` = not applicable |
| `archivo` | Tabulation file (corrientes, constantes, índice de precios, distribución, participaciones) |
| `titulo` | Title from `indice.csv` |

Source: `https://www.inegi.org.mx/contenidos/programas/vabcoel/2018/datosabiertos/conjunto_de_datos_vabcoel2018_csv.zip`.

## INEGI — PIB por entidad federativa (value indicator by state)

### `bronze.pibe`

Gross value added by state, base 2018, 2003–2023 (2022 revised, 2023 preliminary). Only 3 of the
79 tabulations (D03). **Rows:** 1,089 = 3 files × 11 presentations × 33 areas.

| Column | Description |
| --- | --- |
| `descriptores` | `presentation|B.1bV---Valor agregado bruto|<state><C1>` |
| `2003` … `2021`, `2022_r`, `2023_p` | Value per year |
| `archivo` | `..._b.1bv2023_p.csv` (total GVA), `..._512023_p.csv` (sector 51, information in mass media), `..._212023_p.csv` (sector 21, mining) |

Source: `https://www.inegi.org.mx/contenidos/programas/pibent/2018/datosabiertos/pibe_datos_abiertos_csv.zip`.

## OECD — ICT Access and Usage by Households and Individuals (international context)

### `bronze.oecd_ict_hogares` · `bronze.oecd_ict_individuos`

SDMX-CSV with labels, filtered to national totals (D04). **Rows:** 1,105 / 2,551, 44 countries
and aggregates, 2015–2025.

| Column | Description |
| --- | --- |
| `ref_area` | `MEX: Mexico` |
| `measure` | `B1_HH: Households with internet access at home`, `C5B_I: Individuals using the internet - last 3 m`, ... |
| `unit_measure` | `PT_HH: Percentage of households` / `PT_POP: Percentage of population` |
| `age`, `sex`, `education_level`, `income_group`, `emp_status`, `geo_area` | Breakdown dimensions (all totals; age 16–74 for individuals) |
| `time_period`, `obs_value` | Year and value |
| `obs_status` | `A: Normal value`, `B: Time series break`, `D: Definition differs`, `U: Low reliability` |

Source: `https://sdmx.oecd.org/public/rest/data/OECD.STI.DEP,DSD_ICT_HH_IND@DF_HH|DF_IND,/...` (exact keys in the extractor).
