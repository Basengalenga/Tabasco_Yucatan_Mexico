# merida_urban_intelligence

Data warehouse de Yucatán (`yucatan_dw`) construido con la arquitectura medallion
(bronze → silver → gold) sobre PostgreSQL + PostGIS.

## Para Gio: estado actual y lo que falta

**Estamos en la capa gold.** Bronze y silver ya están cargadas; el código de gold
(carga y análisis espacial) está escrito y falta ejecutarlo.

| Fase | Estado |
| --- | --- |
| Capa bronze | ✅ Lista |
| Capa silver | ✅ Lista |
| Capa gold | 🛠️ Código listo, falta ejecutar |
| API para acceder al warehouse (FastAPI) | ⏳ Pendiente |
| Dashboards (Metabase o Apache Superset, por decidir) | ⏳ Pendiente |
| Orquestación | ⏳ Pendiente |

Sobre la orquestación: si da tiempo, ver si jala Airflow. Si no da chance, basta
con un script que corra el código con las fases del medallion en orden
(bronze → silver → gold).

Todas las tablas de bronze, silver y gold se definen en `sql/init.sql`.

## Capa bronze

El script `src/extractor_to_bronze.py` descarga cada fuente y la carga a su
propia tabla en el esquema `bronze`:

| Tabla | Fuente |
| --- | --- |
| `bronze.incidencia_delictiva` | SESNSP, incidencia delictiva municipal (solo Yucatán, clave 31) |
| `bronze.iter_2020` | INEGI, ITER Censo 2020, Yucatán |
| `bronze.denue` | INEGI DENUE, ediciones 2020–2025 |
| `bronze.marco_geo_municipal` | INEGI Marco Geoestadístico, polígonos municipales |

Reglas de bronze:

- Todas las columnas de la fuente se guardan como `TEXT`.
- Nombres de columna normalizados a snake_case sin acentos.
- Los datos se cargan tal como vienen, sin limpiar ni transformar.
- Se agregan los metadatos `_ingested_at`, `_source_url` y `_run_id`.
- Fail-fast: si cualquier descarga o carga falla, el script se detiene.
- Por ahora cada ejecución reemplaza la tabla completa (decisión temporal
  mientras se define la estrategia de re-ejecuciones).

## Hallazgo: puntos DENUE fuera de los polígonos municipales

Se cruzaron los 809,101 puntos de `bronze.denue` (todas las ediciones) contra
los polígonos de `bronze.marco_geo_municipal` con PostGIS (`ST_Intersects` para
detectar los que caen fuera y `ST_Distance` para medir al polígono más cercano,
en EPSG:6372). Solo 52 puntos quedan fuera:

| Grupo | Puntos | Distancia al polígono más cercano |
| --- | --- | --- |
| Borde | 7 | 2 a 25 m |
| Coordenada basura (10.258, -124.445, en el Pacífico) | 43 | ~3,600 km |
| Fuera del estado (Puebla y Sinaloa) | 2 | > 1,000 km |

**Decisión:** umbral de **30 m**, es decir, 5 m de margen sobre el punto de borde
más alejado (25 m). En silver, los puntos a 30 m o menos se asignan al municipio
más cercano y los demás se descartan.

## Decisión: Arrecife Alacranes fuera del polígono de Progreso

El polígono de Progreso del Marco Geoestadístico incluye el Arrecife Alacranes
(42 partes, ~231 km², a ~120 km de la costa). No es habitable e inflaba el área
de Progreso (~658 km² en lugar de 426 km²), lo que bajaba sus densidades. En silver
se quitan las partes cuyo centroide cae en la caja del arrecife (constante
`CAJA_ALACRANES` en `src/bronze_to_silver.py`). Los demás cayos e islas (Cayo Arenas
en Progreso, las de Celestún y San Felipe) se conservan.

## Capa gold

`src/silver_to_gold.py` aplica `sql/init.sql` y, en una sola transacción, trunca
gold, ejecuta `sql/gold/gold.sql` y valida contra silver: 106 municipios,
106 × 6 filas en el panel, suma de población, incidentes por año y
establecimientos por edición, y que ningún municipio quede sin vecinos.
Después, `src/gold_analytics.py` lee solo de gold y escribe los resultados del
análisis en `gold.resultado_*`. Los dos registran sus conteos en `gold.etl_log`.

### Modelo

| Tabla / vista | Grano |
| --- | --- |
| `dim_municipio` | municipio (cvegeo), con polígono |
| `dim_tiempo` | año-mes, 2020 a 2025 (`id_tiempo` = AAAAMM) |
| `dim_actividad` | clase SCIAN + versión (2018 y 2023), con rama, subsector y sector |
| `dim_delito` | bien jurídico + tipo + subtipo + modalidad |
| `fact_censo` | municipio (Censo 2020) |
| `fact_establecimiento` | establecimiento × edición DENUE |
| `fact_incidencia` | municipio × mes × delito, 2020 a 2025 |
| `vecinos_municipio` | par de municipios contiguos (cada par en ambas direcciones) |
| `kpi_municipio_anio` (vista) | municipio × año, 2020 a 2025 |
| `cociente_localizacion` (vista) | municipio × año × sector (solo sectores presentes) |
| `resultado_correlacion` | año × par de variables × método |
| `resultado_moran_global` | año × indicador |
| `resultado_lisa` | año × indicador × municipio |
| `resultado_moran_bivariado` | año × par de variables |

**`fact_establecimiento` es un snapshot periódico: NO se suma entre ediciones.**
Un mismo establecimiento aparece una vez por edición; sumar ediciones lo cuenta
varias veces. Siempre hay que filtrar una sola edición (como hacen las vistas).

### Supuestos

- La población es la del **Censo 2020 para todos los años** del panel; las tasas
  por habitante de 2021 a 2025 usan ese denominador.
- Para cada año se usa la edición DENUE de noviembre, salvo **2025, que usa la
  edición de mayo** (2025_05), porque no existe la de noviembre.
- Las ediciones 2020 a 2023 usan SCIAN 2018 y las de 2024 y 2025 usan SCIAN 2023.
- Actividad dominante: sector con más negocios; si hay empate, gana el código de
  sector menor.

### Regla de vecindad (Queen)

Dos municipios son vecinos si comparten un borde o solo un vértice (contigüidad
Queen). Se calcula con `ST_Intersects` y no con `ST_Touches`: 45 de los 288 pares
contiguos se enciman unos m² (máx. 3.61 m², imprecisión del Marco Geoestadístico),
y `ST_Touches` los descartaba; Kanasín se quedaba sin vecinos. Ningún par de
municipios separados está a menos de 1 m, así que no se agregan falsos vecinos.

Implicaciones:

- Los pesos espaciales se estandarizan por fila: el rezago espacial de un municipio
  es el promedio de sus vecinos, sin importar cuántos tenga.
- Contar como vecinos a municipios que solo comparten un vértice amplía un poco la
  vecindad respecto a Rook (solo bordes).
- Municipios con pocos vecinos (en la costa o en el borde del estado) tienen un
  rezago espacial basado en menos observaciones; no se consideran los municipios
  de Campeche ni de Quintana Roo.

### Cautelas

- **Mérida es un outlier** (mucha más población, negocios e incidentes que el
  resto) y puede dominar la correlación de Pearson; Spearman, por rangos, es más
  robusta.
- Las **tasas son inestables en municipios de baja población**: pocos incidentes
  mueven mucho la tasa por 1,000 habitantes.
- **Asociación espacial no implica causalidad.**

### Hallazgos

Ver [`hallazgos.md`](hallazgos.md).

## Cómo levantarlo

1. Levantar la base de datos (PostGIS en `localhost:5432`, base `yucatan_dw`,
   usuario `admin` / `admin123`):

   ```bash
   docker compose up -d
   ```

2. Instalar dependencias:

   ```bash
   pip install -r requirements.txt
   ```

3. Correr los scripts en este orden (cada uno depende del anterior):

   ```bash
   python src/extractor_to_bronze.py   # fuentes -> bronze
   python src/bronze_to_silver.py      # bronze -> silver
   python src/silver_to_gold.py        # silver -> gold (modelo estrella y vistas)
   python src/gold_analytics.py        # gold -> gold.resultado_* (análisis espacial)
   ```

## Estructura

```
src/extractor_to_bronze.py    # extracción y carga a bronze
src/bronze_to_silver.py       # bronze -> silver
src/silver_to_gold.py         # silver -> gold (ejecuta sql/gold/gold.sql y valida)
src/gold_analytics.py         # correlaciones, Moran, LISA -> gold.resultado_*
sql/init.sql                  # extensión PostGIS, esquemas y DDL de todas las tablas
sql/gold/gold.sql             # carga de gold y vistas (en subcarpeta: Docker no lo ejecuta)
validaciones/silver.sql       # validaciones post-carga de silver
docker-compose.yml            # contenedor de PostGIS
requirements.txt              # dependencias de Python
```
