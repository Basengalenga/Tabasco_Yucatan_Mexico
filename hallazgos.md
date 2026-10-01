# Hallazgos del análisis de gold

Resultados de `src/gold_analytics.py` (tablas `gold.resultado_*`), panel municipal de
Yucatán 2020–2025, 106 municipios. Pesos Queen (`gold.vecinos_municipio`) estandarizados
por fila, 999 permutaciones con semilla fija, significancia al 0.05.

Corrida: `bronze_to_silver` run_id `d2efc1f1-531a-49ff-950f-d479e1dc1fc2`,
`silver_to_gold` run_id `3ca8403e-2404-49c0-bb25-a2a4039ec683`,
`gold_analytics` run_id `6d5c0ca2-30d7-42a3-8d51-6d784aef7475`.
El polígono de Progreso ya no incluye el Arrecife Alacranes (426.4 km² en lugar de ~658 km²).

Ver las cautelas del README: Mérida es un outlier, las tasas son inestables en municipios
de baja población y la asociación espacial no implica causalidad.

## 1. Correlaciones: Pearson vs Spearman

| Par | Año | Pearson | p | Spearman | p |
| --- | --- | --- | --- | --- | --- |
| densidad poblacional vs densidad de negocios | 2020 | 0.920 | < 0.001 | 0.848 | < 0.001 |
| | 2021 | 0.922 | < 0.001 | 0.848 | < 0.001 |
| | 2022 | 0.922 | < 0.001 | 0.848 | < 0.001 |
| | 2023 | 0.924 | < 0.001 | 0.850 | < 0.001 |
| | 2024 | 0.956 | < 0.001 | 0.853 | < 0.001 |
| | 2025 | 0.955 | < 0.001 | 0.842 | < 0.001 |
| tasa delictiva vs negocios por 1,000 hab | 2020 | -0.047 | 0.630 | -0.060 | 0.544 |
| | 2021 | -0.106 | 0.278 | -0.042 | 0.667 |
| | 2022 | 0.027 | 0.784 | -0.130 | 0.184 |
| | 2023 | -0.149 | 0.128 | -0.175 | 0.073 |
| | 2024 | -0.137 | 0.163 | -0.018 | 0.851 |
| | 2025 | -0.053 | 0.587 | -0.006 | 0.950 |
| tasa PEA vs tasa delictiva | 2020 | 0.058 | 0.552 | 0.079 | 0.423 |
| | 2021 | 0.285 | 0.003 | 0.235 | 0.015 |
| | 2022 | 0.137 | 0.162 | 0.144 | 0.140 |
| | 2023 | 0.169 | 0.084 | 0.148 | 0.129 |
| | 2024 | 0.169 | 0.083 | 0.124 | 0.207 |
| | 2025 | 0.245 | 0.011 | 0.205 | 0.035 |

- **Densidad poblacional y densidad de negocios** tienen una relación muy fuerte y estable
  en los 6 años. Pearson (0.92–0.96) siempre es mayor que Spearman (0.84–0.85), lo que es
  compatible con que Mérida, extrema en ambas variables, infle Pearson (no se aisló
  quitando a Mérida).
- **Tasa delictiva y negocios por 1,000 habitantes** no tienen relación: ningún año es
  significativo con ninguno de los dos métodos.
- **Tasa PEA y tasa delictiva** tienen una relación positiva débil, significativa solo en
  2021 y 2025 con ambos métodos; no es estable entre años.

## 2. Moran global

| Indicador | Año | I | z (sim) | p_sim |
| --- | --- | --- | --- | --- |
| densidad de negocios | 2020 | 0.195 | 4.72 | 0.001 |
| | 2021 | 0.196 | 4.72 | 0.001 |
| | 2022 | 0.196 | 4.72 | 0.001 |
| | 2023 | 0.197 | 4.74 | 0.001 |
| | 2024 | 0.199 | 4.50 | 0.004 |
| | 2025 | 0.198 | 4.50 | 0.006 |
| tasa delictiva por 1,000 hab | 2020 | 0.175 | 3.68 | 0.004 |
| | 2021 | 0.118 | 2.15 | 0.029 |
| | 2022 | 0.157 | 3.11 | 0.014 |
| | 2023 | 0.192 | 3.52 | 0.002 |
| | 2024 | 0.295 | 5.33 | 0.001 |
| | 2025 | 0.121 | 2.10 | 0.027 |

E[I] = -0.01 en todos los casos.

- Las dos variables presentan **autocorrelación espacial positiva y significativa en todos
  los años**: municipios con valores parecidos tienden a ser vecinos.
- La densidad de negocios es muy estable (I ≈ 0.20). La tasa delictiva varía más; 2024 es
  el año más agrupado (I = 0.295).

## 3. Moran bivariado: tasa delictiva vs densidad de negocios

| Año | I | z (sim) | p_sim |
| --- | --- | --- | --- |
| 2020 | 0.031 | 0.62 | 0.211 |
| 2021 | 0.069 | 1.37 | 0.092 |
| 2022 | 0.036 | 0.72 | 0.196 |
| 2023 | 0.039 | 0.77 | 0.197 |
| 2024 | 0.045 | 0.74 | 0.187 |
| 2025 | 0.005 | 0.11 | 0.435 |

- **No es significativo en ningún año.** Cada variable se agrupa por su lado, pero la tasa
  delictiva de un municipio no se asocia con la densidad de negocios de sus vecinos.

## 4. LISA por año

### Densidad de negocios

| Año | HH | HL | LH | LL |
| --- | --- | --- | --- | --- |
| 2020 | 8 | 0 | 4 | 16 |
| 2021 | 8 | 0 | 4 | 16 |
| 2022 | 8 | 0 | 4 | 16 |
| 2023 | 8 | 0 | 4 | 16 |
| 2024 | 6 | 1 | 4 | 15 |
| 2025 | 6 | 1 | 4 | 16 |

- **Cluster HH estable alrededor de Mérida**: Mérida, Kanasín, Progreso, Conkal,
  Chicxulub Pueblo y Tixkokob en los 6 años; Umán y Yaxkukul salen del cluster desde 2024.
- **Valladolid** aparece como HL (alto rodeado de bajos) en 2024 y 2025.
- **Clusters LL en el oriente y sur** del estado (p. ej. Tizimín, Panabá, Río Lagartos,
  Buctzotz, Cenotillo, Yaxcabá, Temax, San Felipe).

### Tasa delictiva por 1,000 habitantes

| Año | HH | HL | LH | LL |
| --- | --- | --- | --- | --- |
| 2020 | 6 | 3 | 5 | 5 |
| 2021 | 9 | 3 | 6 | 9 |
| 2022 | 5 | 2 | 3 | 13 |
| 2023 | 6 | 0 | 5 | 15 |
| 2024 | 12 | 1 | 4 | 9 |
| 2025 | 7 | 1 | 5 | 10 |

Municipios HH por año:

| Año | HH |
| --- | --- |
| 2020 | Bokobá, Cacalchén, Motul, Muxupip, Suma, Yobaín |
| 2021 | Abalá, Celestún, Chicxulub Pueblo, Ixil, Progreso, Samahil, Tetiz, Umán, Yaxkukul |
| 2022 | Cacalchén, Dzemul, Ixil, Motul, Telchac Pueblo |
| 2023 | Cacalchén, Dzemul, Ixil, Mocochá, Motul, Tekantó |
| 2024 | Baca, Bokobá, Cansahcab, Dzemul, Ixil, Mocochá, Motul, Sinanché, Suma, Telchac Pueblo, Yaxkukul, Yobaín |
| 2025 | Dzemul, Hunucmá, Ixil, Mocochá, Motul, Oxkutzcab, Progreso |

- El cluster HH cambia de un año a otro, pero **se repite en el centro-norte** (Motul,
  Ixil, Dzemul, Mocochá, Cacalchén). **Mérida no aparece** en el cluster HH de crimen.
- **Valladolid** es HL en 2020, 2021 y 2022.
- La variación del cluster entre años es consistente con la inestabilidad de las tasas en
  municipios pequeños.

## 5. Problemas de datos a revisar antes de interpretar tendencias

- **Caída abrupta de incidencia en 2022.** Los incidentes del estado pasan de 8,565 (2021)
  a 4,209 (2022); en Mérida de 6,522 a 1,820. En 2015 eran 34,716. Un cambio de esta
  magnitud parece de registro de la fuente (SESNSP), no de criminalidad real, y afecta
  cualquier comparación entre años.
- **Salto del DENUE en 2024.** El total del estado pasa de ~130 mil a ~142 mil
  establecimientos, justo cuando la clasificación cambia de SCIAN 2018 a SCIAN 2023; en
  Abalá, de 96 a 239. Puede ser un efecto de la fuente y no un cambio real.
