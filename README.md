# Economía digital: Yucatán vs Tabasco vs México

Data warehouse (`economia_digital_dw`) que mide la economía digital de **Yucatán**, **Tabasco** y
**México (nacional)** con indicadores de **acceso**, **uso** y **valor** de las tecnologías de la
información, construido con la arquitectura medallion (bronze → silver → gold) sobre PostgreSQL,
orquestado con Airflow y servido por una API (FastAPI) a un dashboard (Streamlit).

Resultados e interpretación: [`hallazgos.md`](hallazgos.md). Decisiones de limpieza y descarte:
[`docs/decisiones_limpieza.md`](docs/decisiones_limpieza.md).

## Objetivo

Comparar Yucatán, Tabasco y el país en 2020–2024 con cifras oficiales descargadas en crudo:

| Dimensión | Pregunta | Indicadores (ejemplos) | Fuente |
| --- | --- | --- | --- |
| **Acceso** | ¿Con qué se conectan? | Hogares con internet, internet fijo, computadora; usuarios de smartphone | INEGI ENDUTIH |
| **Uso** | ¿Qué hacen en línea? | Usuarios de internet; compran, venden, pagan y usan banca en línea | INEGI ENDUTIH |
| **Valor** | ¿Cuánto vale? | VAB del comercio electrónico (% del PIB); peso del sector 51 (información) en la economía de cada estado | INEGI cuentas nacionales (VABCOEL, PIB estatal) |
| Contexto | ¿Dónde está México en el mundo? | Las mismas medidas para 40+ países | OECD ICT Access & Usage |

Las otras 30 entidades se usan solo como contexto (lugar de Yucatán y Tabasco entre las 32).

## Fuentes de datos

Todas oficiales, descargadas en crudo por `src/extractor_to_bronze.py` (las URLs exactas están
ahí y en la columna `_source_url` de cada tabla bronze). No se usan noticias ni sitios de resumen.

| Fuente | Tabla(s) bronze | Grano original | Cobertura |
| --- | --- | --- | --- |
| INEGI, **ENDUTIH** (Encuesta Nacional sobre Disponibilidad y Uso de TIC en Hogares), microdatos de datos abiertos | `endutih_hogares_<anio>`, `endutih_usuarios_<anio>`, `endutih_usuarios2_<anio>`, `endutih_diccionario`, `endutih_cat_entidad` | hogar y persona elegida de 6+ (con factor de expansión y diseño muestral) | 2020–2024, ~58 mil hogares por año, representativa por entidad |
| INEGI, **Valor Agregado Bruto del Comercio Electrónico** (VABCOEL), Sistema de Cuentas Nacionales, base 2018 | `vabcoel` | año × componente × medida | 2013–2024, nacional |
| INEGI, **PIB por entidad federativa**, base 2018 (VAB total, sector 51 y sector 21) | `pibe` | entidad × año | 2003–2023, 32 entidades + nacional |
| **OECD**, ICT Access and Usage by Households and Individuals (SDMX) | `oecd_ict_hogares`, `oecd_ict_individuos` | país × año × medida | 2015–2025, 40+ países |

Fuentes evaluadas y descartadas (ITU DataHub requiere credenciales; el programa `/ed/` de INEGI
resultó ser estadística de divorcios): ver [`docs/decisiones_limpieza.md`](docs/decisiones_limpieza.md#fuentes-evaluadas-y-descartadas).

## Arquitectura

```
fuentes ──> bronze ──> silver ──────> gold ─────────> gold.resultado_* ──> API ──> dashboard
          (crudo,     (limpio,       (estrella +     (brechas, tendencias,
           TEXT)       armonizado     estimaciones    rankings,
                       entre años)    con error       validación OECD)
                                      estándar)
```

| Servicio | Contenedor | Acceso |
| --- | --- | --- |
| PostgreSQL (warehouse) | `ed_dw` | `localhost:5432`, base `economia_digital_dw`, usuario `admin` / `admin123` |
| Airflow | `ed_airflow` | http://localhost:8080, usuario `admin` / `admin123` |
| API (FastAPI) | `ed_api` | solo dentro de la red de Docker (`http://api:8000`) |
| Dashboard (Streamlit) | `ed_dashboard` | http://localhost:8501 |

### Bronze (`src/extractor_to_bronze.py`)

- Una función por fuente; las 4 corren en paralelo en Airflow.
- Todas las columnas como `TEXT`, sin limpiar. Nombres en snake_case sin acentos.
- Microdatos de la ENDUTIH: **una tabla por archivo y año, con las columnas exactas de ese año**
  (la numeración de las preguntas cambia entre levantamientos). Se cargan con `COPY` directo
  desde el ZIP, sin pasar por pandas.
- Metadatos: `_ingested_at`, `_source_url`, `_run_id` (y `_archivo`).
- Fail-fast: primero se descarga todo; luego se escribe en una transacción.
- `CACHE_DESCARGAS` (opcional, solo desarrollo): carpeta donde se reutilizan las descargas.

### Silver (`src/bronze_to_silver.py`)

- **Armonización de preguntas entre años** validada contra el diccionario de datos de INEGI: si
  una columna no dice lo que se espera ("compras por internet", "banca electrónica"...), el
  pipeline se detiene. Ejemplo: "compró por internet" es P7_19 en 2020–2022 y P7_21 en 2023–2024,
  y en 2020–2022 P7_21 es la *frecuencia* de compra (D06).
- Respuestas 1/2 → `BOOLEAN`; saltos de cuestionario explícitos (D13); llaves uniformadas (D07).
- Tabulados de INEGI de ancho a largo, con estatus de la cifra (definitiva, revisada, preliminar).
- Validaciones: suma de entidades = nacional (PIB), componentes = total (VABCOEL), cobertura de
  32 entidades por año, unicidad de llaves.
- Cada descarte y recodificación queda contado en `silver.etl_log` (con detalle legible) y
  documentado en [`docs/decisiones_limpieza.md`](docs/decisiones_limpieza.md) (D01–D19).

### Gold (`src/silver_to_gold.py`, `sql/gold/gold.sql`, `src/gold_analytics.py`)

- **Estimaciones de encuesta con su error.** Cada indicador de la ENDUTIH es una proporción
  ponderada por el factor de expansión, con **error estándar por linealización de Taylor según
  el diseño muestral** de INEGI (estratos `est_dis`, UPM `upm_dis`), intervalo de confianza al 90%
  y calidad por coeficiente de variación (criterio de INEGI: < 15% alta, 15–30% moderada, > 30%
  baja). Universo: hogares, población de 6+, usuarios de internet u hogares sin internet, según
  el indicador.
- Indicadores de valor en vistas SQL: peso del sector 51 en el VAB (también **sin minería**, para
  no castigar a Tabasco por el petróleo), crecimiento real, comercio electrónico en el PIB.
- Análisis (`gold_analytics.py`):
  - **Brechas** Yucatán−Tabasco, Yucatán−México y Tabasco−México con prueba z al 90%. Contra el
    nacional se descuenta la covarianza (la entidad es parte del país).
  - **Tendencias** 2020→2024 con prueba de diferencia entre levantamientos y pendiente por MCO.
  - **Ranking** entre las 32 entidades.
  - **Validación externa contra OECD**: las estimaciones nacionales se recalculan para personas
    de 16 a 74 años (definición OECD) y se comparan con lo que México reporta: **coinciden al
    centésimo en 7 de 8 medidas**.

## Data warehouse

Documentación del modelo en `docs/`:

- Diagrama dimensional: [`docs/warehouse_model.png`](docs/warehouse_model.png) (fuente Graphviz en
  `warehouse_model.dot`; versión Mermaid y granos en [`docs/warehouse_model.md`](docs/warehouse_model.md)).
- Diccionario de datos por capa: [bronze](docs/data_dictionary_bronze.md),
  [silver](docs/data_dictionary_silver.md) y [gold](docs/data_dictionary_gold.md).

| Tabla / vista | Tipo | Grano |
| --- | --- | --- |
| `dim_entidad` | dimensión | entidad (32) + nacional `'00'` |
| `dim_tiempo` | dimensión | año, 2003–2025 |
| `dim_indicador` | dimensión | indicador (acceso, uso, valor, brecha) |
| `dim_pais` | dimensión | país o agregado OECD |
| `fact_encuesta_tic` | hecho | año × entidad × indicador × grupo de edad, con error estándar e IC 90% |
| `fact_valor_entidad` | hecho | año × entidad × concepto (VAB total, 51, 21) × precios |
| `fact_comercio_electronico` | hecho | año × componente × medida (nacional) |
| `fact_oecd_tic` | hecho | año × país × medida |
| `kpi_entidad_anio` | vista | año × entidad, indicadores en columnas |
| `valor_entidad_anio` | vista | año × entidad, valor económico del sector 51 |
| `comercio_electronico_anio` | vista | año, comercio electrónico nacional |
| `resultado_brecha`, `resultado_tendencia`, `resultado_ranking`, `resultado_validacion_oecd` | resultado | ver diccionario de gold |

## Dashboard

http://localhost:8501, siete pestañas:

| Pestaña | Contenido |
| --- | --- |
| Panorama | Tarjetas por entidad con lugar entre las 32, hallazgos clave calculados en vivo, comparación de los 10 indicadores con IC 90% |
| Acceso | Series 2020–2024 con banda de confianza; razones para no tener internet |
| Uso | Series de uso y economía digital; posición entre los 32 estados; acceso vs compras en línea |
| Valor económico | Peso del sector 51 (con y sin minería), VAB real, comercio electrónico por actividad y en el PIB |
| Brechas y significancia | Mapa de calor de diferencias con marca de significancia; cambio 2020→2024 |
| Contexto internacional | Países OECD por medida, México resaltado; validación ENDUTIH vs OECD |
| Calidad de datos | Decisiones de limpieza de la última corrida, calidad de las estimaciones, armonización de preguntas, carga de gold |

Colores fijos por entidad (paleta validada para daltonismo): Yucatán azul, Tabasco naranja,
México verde.

## Supuestos y cautelas

- **Estimaciones por muestreo.** Toda cifra de la ENDUTIH trae intervalo de confianza; dos
  entidades solo se declaran distintas si la prueba lo indica.
- **Panel 2020–2024.** La ENDUTIH 2019 no trae clave de entidad (D01). 2020 se levantó en pandemia.
- **Cifras preliminares**: PIB estatal 2023 y VABCOEL 2024. El VABCOEL solo existe a nivel nacional;
  el valor por entidad se aproxima con el sector 51 del PIB estatal.
- **Tabasco y el petróleo.** La minería es ~45% de su VAB; las participaciones se reportan también
  sin minería.
- **La entidad oculta la variación interna** (Mérida, Villahermosa).

## Cómo reproducirlo

Requisitos: Docker con Docker Compose.

1. Levantar los contenedores:

   ```bash
   docker compose up -d
   ```

   Al crear el volumen de la base, Docker ejecuta `sql/init.sql` (esquemas y tablas de silver y
   gold). Los scripts de silver y gold lo vuelven a aplicar al inicio (es idempotente).

2. El DAG `pipeline_economia_digital_dw` (`schedule="@once"`) corre solo la primera vez que
   Airflow arranca con una base de metadatos nueva; después se puede lanzar a mano desde
   http://localhost:8080:

   ```
   extraer_endutih ─┐
   extraer_vabcoel ─┤
   extraer_pibe    ─┼──> bronze_to_silver ──> silver_to_gold ──> gold_analytics
   extraer_oecd    ─┘
   ```

   Los 4 extractores corren en paralelo (con 2 reintentos, porque los servidores de INEGI a veces
   tardan); si cualquiera falla, silver no se toca. Comparten `_run_id` e `_ingested_at`. La
   corrida completa tarda entre 3 y 10 minutos según la velocidad de INEGI.

3. (Opcional) Validaciones:

   ```bash
   docker exec -i ed_dw psql -U admin -d economia_digital_dw < validaciones/silver.sql
   docker exec -i ed_dw psql -U admin -d economia_digital_dw < validaciones/gold.sql
   ```

4. Abrir el dashboard en http://localhost:8501.

5. (Opcional) Figuras estáticas en `outputs/figures/`, con gold ya cargado:

   ```bash
   docker compose run --rm --no-deps --user "$(id -u):0" \
     -v "$PWD/outputs:/opt/airflow/outputs" \
     --entrypoint python airflow /opt/airflow/src/figuras.py
   ```

   Series con IC 90% por indicador, brechas y ranking por año, sector 51, comercio electrónico y
   validación OECD.

El contenedor `airflow` monta `./dags`, `./src` y `./sql` como solo lectura (`:ro`).

### API

El dashboard no se conecta a PostgreSQL: pide los datos a la API (`api/main.py`), la única que
consulta la base.

| Endpoint | Devuelve |
| --- | --- |
| `GET /health` | Estado de la API |
| `GET /entidades`, `GET /indicadores` | Dimensiones |
| `GET /encuesta` | Estimaciones ENDUTIH (33 entidades × indicador × año) con error estándar, IC y calidad |
| `GET /valor` | `gold.valor_entidad_anio` |
| `GET /comercio-electronico` | `gold.comercio_electronico_anio` |
| `GET /oecd` | `gold.fact_oecd_tic` con nombre de país |
| `GET /resultados/{brecha,tendencia,ranking,validacion-oecd}` | Tablas `gold.resultado_*` |
| `GET /calidad/decisiones` | Bitácora de limpieza de la última corrida de silver |
| `GET /calidad/mapeo-variables` | Armonización de preguntas de la ENDUTIH por año |
| `GET /etl-log` | Las dos últimas corridas de `gold.etl_log` |

Para correr la API y el dashboard fuera de Docker (con la base levantada):

```bash
cd api && pip install -r requirements.txt
DB_URL=postgresql+psycopg2://admin:admin123@localhost:5432/economia_digital_dw uvicorn main:app --port 8000
# en otra terminal
cd dashboard && pip install -r requirements.txt && streamlit run main.py
```

Los scripts de `src/` también aceptan `DB_URL` para correr fuera de Docker.

## Estructura

```
src/extractor_to_bronze.py    # descarga de las 4 fuentes y carga a bronze
src/bronze_to_silver.py       # limpieza, armonización entre años, decisiones registradas
src/silver_to_gold.py         # modelo estrella + estimaciones de encuesta con error estándar
src/gold_analytics.py         # brechas, tendencias, rankings, validación OECD
src/figuras.py                # figuras estáticas desde gold -> outputs/figures/
dags/pipeline_economia_digital_dw.py   # DAG de Airflow
sql/init.sql                  # esquemas y DDL de silver y gold
sql/gold/gold.sql             # carga de gold y vistas (en subcarpeta: Docker no lo ejecuta)
validaciones/silver.sql       # validaciones post-carga de silver
validaciones/gold.sql         # recálculo de indicadores desde silver y hechos
api/main.py                   # API (FastAPI)
dashboard/main.py             # dashboard (Streamlit)
docs/decisiones_limpieza.md   # catálogo de decisiones de limpieza y descarte (D01–D19)
docs/                         # modelo dimensional y diccionarios de datos
hallazgos.md                  # resultados e interpretación
```
