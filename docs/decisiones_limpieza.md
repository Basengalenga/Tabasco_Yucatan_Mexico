# Decisiones de limpieza y descarte de datos

Cada decisión que elimina, recodifica o reinterpreta datos de las fuentes está aquí, con su
justificación y su efecto medido. Los identificadores `Dxx` aparecen en los comentarios del
código (`src/extractor_to_bronze.py`, `src/bronze_to_silver.py`) y los conteos de cada corrida
quedan en `silver.etl_log` (métrica + registros + detalle), visibles en la pestaña
**Calidad de datos** del dashboard.

Principio general: **bronze nunca se limpia** (es la copia cruda de la fuente); toda limpieza
ocurre en silver y es reproducible. Cuando un dato no cumple una regla esperada, el pipeline
**se detiene** en lugar de adivinar (fail-fast); solo se recodifica lo que está documentado aquí.

## Resumen

| ID | Fuente | Decisión | Efecto (corrida de referencia) |
| --- | --- | --- | --- |
| D01 | ENDUTIH | Se excluye el levantamiento 2019 | 1 año fuera; panel 2020–2024 |
| D02 | ENDUTIH | No se cargan las tablas de residentes ni de viviendas | 2 de 5 tablas por año fuera |
| D03 | PIB estatal | Solo 3 de los 79 tabulados del ZIP | VAB total, sector 51 y sector 21 |
| D04 | OECD | Consulta filtrada al total nacional y 11 medidas | ~4 MB en lugar de ~180 MB |
| D05 | ENDUTIH | Finales de línea uniformados a LF antes de `COPY` | Archivo de hogares 2023 |
| D06 | ENDUTIH | Mapeo de preguntas por año, validado contra el diccionario | 80 columnas validadas |
| D07 | ENDUTIH | Llaves rellenadas con ceros a la izquierda; `ent` / `cve_ent` | Ver tabla de D07 |
| D08 | Catálogo | Se agrega la fila nacional `cve_ent = '00'` | 1 fila |
| D09 | ENDUTIH | Diccionario 2020: `campo` en lugar de `columna` | 415 renglones |
| D10 | VABCOEL | Se descartan renglones derivados | 24 de 43 renglones |
| D11 | ENDUTIH | "Computadora" = escritorio o laptop o tablet | Definición INEGI/OECD |
| D12 | ENDUTIH | Tipo de conexión "no sabe" → `NULL` | 65–100 hogares por año |
| D13 | ENDUTIH | Vacíos por salto de cuestionario → `FALSE` | 10,840–18,045 personas por año |
| D14 | VABCOEL | Jerarquía de "Otros servicios" corregida | 5 renglones |
| D15 | PIB estatal | Se descartan presentaciones derivadas | 891 de 1,089 renglones |
| D16 | PIB estatal | Unión por nombre normalizado, validada 33/33 | 0 sin clave |
| D17 | OECD | Observaciones sin valor fuera; bandera de estatus conservada | 0 sin valor; 487 con bandera |
| D18 | ENDUTIH | Smartphone vacío para quien no usa celular → `FALSE` | Salto de P8_4_2 |
| D19 | Gold | Peso del sector 51 también sin minería en el denominador | Indicador adicional |

## Fuentes evaluadas y descartadas

| Fuente | Motivo |
| --- | --- |
| ITU DataHub (API) | Responde 403 *Missing Authentication Token*: no se puede automatizar sin credenciales. Se usó la base ICT de **OECD**, que publica las mismas medidas armonizadas para México (y México las reporta desde la ENDUTIH). |
| INEGI `/programas/ed/` | El nombre sugiere "economía digital", pero el ZIP es la **Estadística de Divorcios**. Se descartó tras inspeccionarlo. |
| Marco Geoestadístico nacional (257 MB) | Solo servía para un mapa de 32 estados; el alcance es Yucatán vs Tabasco vs México. |
| Noticias y sitios de resumen | No son fuentes oficiales (regla del proyecto). Los valores de referencia del dashboard salen de los datos crudos. |

## Detalle

### D01 · ENDUTIH 2019 fuera del panel

El archivo de datos abiertos de 2019 **no trae la clave de entidad** (`ENT`) y tiene 21,620
hogares (contra ~58 mil de 2020–2024). Identificar Yucatán y Tabasco exigiría inferir la entidad
de los dos primeros dígitos de la UPM, algo que INEGI no documenta como llave. Además, 2020 fue
el primer levantamiento con representatividad estatal en el esquema actual. Se trabaja 2020–2024
(5 años, mismo diseño).

### D02 · Sin residentes ni viviendas

Los indicadores del proyecto salen del **hogar** (equipamiento y conexión) y del **informante
elegido** de 6 años y más (uso). Las tablas de residentes y viviendas no aportan ninguna variable
usada; cargarlas duplicaría ~1 millón de renglones sin uso.

### D03 · PIB estatal: 3 tabulados de 79

El ZIP de PIB por entidad trae un tabulado por actividad y por entidad. Se cargan solo:
`b.1bv` (VAB total), `51` (información en medios masivos) y `21` (minería, para D19).

### D04 · OECD filtrado en la consulta

El flujo `DSD_ICT_HH_IND` completo pesa ~180 MB (todas las desagregaciones por edad, sexo,
ingreso, educación). La consulta SDMX pide solo el total nacional (personas de 16 a 74 años,
todos los hogares) de las medidas que se usan: A1_HH, B1_HH, B21A_HH, B21B_HH, C5B_I, C2B_I,
G1_I, D1T_I, D1U_I, F1_I, D1B_I.

### D05 · Finales de línea mezclados (hogares 2023)

`tr_endutih_hogares_anual_2023.csv` tiene el encabezado con CRLF y los datos con LF.
PostgreSQL `COPY` lo rechaza (*unquoted newline found in data*). Se reemplaza `\r\n` por `\n`
antes de cargar; ningún valor cambia.

### D06 · Las preguntas se renumeran entre años

La misma pregunta cambia de número entre levantamientos, y un número puede significar otra cosa:

| Concepto | 2020–2022 | 2023–2024 |
| --- | --- | --- |
| Redes sociales | P7_13 | P7_15 |
| Ventas por internet | P7_17 | P7_19 |
| Compras por internet | P7_19 | **P7_21** |
| Pagos por internet | P7_27 | P7_28 |
| Banca electrónica | P7_32 | P7_33 |
| Computadora en el hogar | P4_2_1, P4_2_2, P4_2_3 | P4_2_1_1, P4_2_2_1, P4_2_3_1 |

En 2020–2022, **P7_21 es la frecuencia de compra**, no si compró: usar "P7_21" para todos los
años mezclaría dos preguntas distintas sin error visible. Por eso cada concepto se mapea por año
(`MAPEO_HOGAR`, `MAPEO_PERSONA`) y **cada columna se valida contra el texto del diccionario de
datos de INEGI**: la descripción debe contener una palabra clave ("compras por internet",
"banca electronica"...). Si INEGI renumera en un año futuro, el pipeline se detiene. El mapeo
validado queda en `silver.endutih_mapeo_variables`.

### D07 · Llaves sin ceros a la izquierda

Los archivos no son consistentes en el formato de sus llaves:

| Llave | Problema | Años |
| --- | --- | --- |
| `ent` | `'1'` en vez de `'01'` (16,369 registros) | 2022 |
| `upm`, `viv_sel`, `num_ren` | Sin ceros a la izquierda | 2022 |
| `hogar` | `'1'` en vez de `'01'` | 2020, 2022, 2024 |
| `est_dis`, `upm_dis` | Ancho variable (4 o 5 dígitos) | 2022, 2024 |
| `ent` → `cve_ent` | La columna cambia de nombre | 2024 |

Se rellenan con ceros (`ent` 2, `upm` 7, `viv_sel` 2, `hogar` 2, `num_ren` 2, `est_dis` 3,
`upm_dis` 5). Se valida que rellenar **nunca fusione dos claves distintas** (p. ej. `'1'` y `'01'`
en el mismo archivo); se verificó en los 10 archivos: 0 colisiones.

### D08 · Fila nacional

Las fuentes reportan el total del país como "Estados Unidos Mexicanos". Se agrega
`cve_ent = '00'` al catálogo para que nacional, Yucatán (31) y Tabasco (27) compartan llave.

### D09 · Diccionario 2020

El diccionario de 2020 llama `CAMPO` / `RANGO_VALIDO` a lo que los demás años llaman
`COLUMNA` / `CODIGO_VALIDO`. Silver usa `coalesce(columna, campo)`.

### D10 · VABCOEL: solo niveles y participaciones

De los 7 tabulados se conservan niveles (millones de pesos corrientes y constantes 2018) y
participaciones (en PIB, en VAB y dentro de cada actividad). Se descartan **24 renglones**
derivables: variación anual (8), estructura porcentual (4), distribución por actividad (4,
idéntica a la estructura) e índice de precios implícitos (8 con su variación). Guardarlos
duplicaría información con redondeos distintos. Se valida que mayor + menor + otros servicios
= total (tolerancia 0.1%).

### D11 · Definición de computadora

Hogar con computadora = escritorio **o** laptop **o** tablet. Es la definición de INEGI y de la
medida OECD A1_HH; la validación cruzada lo confirma (43.94% en ambas fuentes en 2024).

### D12 · Tipo de conexión "no sabe"

P4_5 (`1` solo fija, `2` solo móvil, `3` ambas, `9` no sabe) solo se pregunta a hogares con
internet. Hogar sin internet → `internet_fija = FALSE`; código 9 → `NULL` (65 a 100 hogares por
año) y se excluye del denominador de "hogares con internet fijo". Es la única medida que difiere
de OECD (0.2–0.4 pp), justamente por cómo se trata este "no sabe".

### D13 · Saltos del cuestionario

Las actividades en internet (redes, compras, ventas, pagos, banca) solo se preguntan a quien usó
internet. Para los no usuarios la fuente deja el campo vacío; aquí se interpreta como **no realizó
la actividad** (`FALSE`), de modo que el indicador sobre toda la población es correcto. Dos
reglas lo protegen: un vacío **entre usuarios** detiene el pipeline (sería un faltante real) y
una respuesta **de un no usuario** también (salto mal aplicado). En la corrida de referencia: 0
casos de ambos.

### D14 · "Otros servicios" mal anidado

INEGI publica `Valor agregado bruto|Comercio al por menor|Otros servicios<C1>`, como si fuera
hijo del comercio al por menor. La nota C1 lo define como "actividades de servicios ...
distintas al comercio al por mayor y al por menor". Se toma el último nivel como componente
(`otros_servicios`), y la suma de los tres componentes reproduce el total.

### D15 · PIB estatal: solo niveles

Cada tabulado trae 11 presentaciones por entidad. Se conservan 2 (millones de pesos corrientes y
a precios de 2018) y se descartan 891 renglones de presentaciones derivables (estructura,
variaciones, índices de volumen y de precios, contribuciones). Se valida que la suma de las 32
entidades sea igual al nacional.

### D16 · Unión por nombre en el PIB estatal

Es la única fuente sin clave de entidad. Se une por nombre normalizado (sin acentos ni
mayúsculas) contra el catálogo de INEGI y se exige que las 33 filas (32 + nacional) encuentren
clave, sin ambigüedad (p. ej. "México" = Estado de México, clave 15, distinto de
"Estados Unidos Mexicanos").

### D17 · Estatus de OECD

Se descartan observaciones sin valor (0 en la corrida de referencia) y se conserva la bandera
de estatus (487 observaciones: quiebre de serie, definición distinta, baja confiabilidad) para
mostrarla en el dashboard. OECD publica 2025 para algunos países europeos antes que para México;
el dashboard solo ofrece años en que México tiene dato.

### D18 · Smartphone

P8_4_2 ("el celular que usa es inteligente") solo se pregunta a quien usó celular (P8_3 = 1).
Vacío para los demás → `FALSE` (no usa smartphone). Un vacío entre usuarios de celular detiene
el pipeline.

### D19 · Sector 51 sin minería

El sector 51 (información en medios masivos: telecomunicaciones, internet, edición de software,
radio y TV) es la medida oficial disponible **por entidad** del valor de la economía digital (el
VAB del comercio electrónico solo existe a nivel nacional). Tabasco es un estado petrolero: la
minería es ~45% de su VAB y deprime cualquier participación. Además de VAB 51 / VAB total, gold
calcula VAB 51 / (VAB total − VAB 21) para comparar la estructura no petrolera.

## Cautelas que no son limpieza

- **Estimaciones de encuesta.** Todo indicador de la ENDUTIH es una estimación con error: se
  publica con error estándar (diseño muestral: estratos `est_dis`, UPM `upm_dis`), intervalo al
  90% y calidad por CV. 6 estimaciones de Tabasco y 6 de Yucatán (de 95 por entidad) no son de
  calidad alta, todas en las razones minoritarias para no tener internet.
- **Cifras preliminares.** PIB estatal 2023 y VABCOEL 2024 son preliminares (`estatus_cifra`).
- **VABCOEL 2019.** El comercio al por menor salta +133% en 2019 por la actualización de
  fuentes de INEGI (nota del tabulado), no por un cambio real de esa magnitud.
- **2020.** La ENDUTIH 2020 se levantó en pandemia; el salto 2020→2021 puede tener un componente
  coyuntural.
