# Hallazgos: economía digital de Yucatán vs Tabasco vs México

Resultados de `gold.fact_encuesta_tic`, `gold.valor_entidad_anio` y las tablas
`gold.resultado_*` (`src/gold_analytics.py`). Estimaciones de la ENDUTIH con su intervalo de
confianza al 90% (nivel de INEGI); una diferencia solo se reporta como tal si la prueba z es
significativa al 90%. Las figuras están en `outputs/figures/` y en el dashboard.

## Panorama 2024

| Indicador | Yucatán | Tabasco | México | Dimensión |
| --- | --- | --- | --- | --- |
| Hogares con internet | 73.9% (#19) | 71.7% (#20) | 73.6% | Acceso |
| Hogares con internet fijo | 72.2% | 69.6% | 71.2% | Acceso |
| Hogares con computadora | 41.7% (#20) | **37.2% (#27)** | 43.9% | Acceso |
| Usuarios de smartphone (6+) | 85.7% | 84.9% | 84.0% | Acceso |
| Usuarios de internet (6+) | **86.0% (#14)** | 83.5% (#20) | 83.1% | Uso |
| Compran por internet (% usuarios) | **44.4% (#4)** | 34.8% (#20) | 35.8% | Uso |
| Venden por internet (% usuarios) | **20.5% (#1)** | 10.3% (#22) | 11.2% | Uso |
| Pagan por internet (% usuarios) | 37.5% (#10) | 33.9% | 33.0% | Uso |
| Banca electrónica (% usuarios) | **21.8% (#8)** | 16.4% | 17.7% | Uso |
| Sector 51 en el VAB no minero (2023) | 1.01% (#4) | 0.60% (#13) | 1.54% | Valor |
| Comercio electrónico en el PIB (2024p) | — | — | 6.9% | Valor |

`#n` = lugar entre las 32 entidades. En negritas, diferencias significativas contra el nacional.

## 1. Yucatán: la entidad que más vende en línea del país

- El **20.5%** de los usuarios de internet de Yucatán vendió algo en línea en 2024: **lugar 1 de
  32** y casi el doble del nacional (11.2%). La diferencia (+9.4 pp) es significativa
  (p < 0.001) y **persistente**: Yucatán estuvo entre los 4 primeros los 5 años (1º en 2022 y 2024).
- También compra más: 44.4% (#4), +8.6 pp sobre el nacional, y está **entre 6 y 9 pp por encima
  de lo que predice su nivel de conexión** (recta de mínimos cuadrados entre las 32 entidades),
  todos los años.
- Banca electrónica: pasó de 14.4% (2020, debajo del nacional) a 21.8% (2024, +4.1 pp sobre el
  nacional): **+7.4 pp, el mayor avance de las tres**, significativo.
- No es por más acceso: Yucatán tiene los mismos hogares conectados que el país (+0.3 pp, no
  significativo) y **menos computadoras** (41.7% vs 43.9%). La ventaja está en el *uso económico*
  de la conexión, no en la infraestructura.

## 2. Tabasco: la brecha de acceso se cerró; la de uso económico no

- Hogares con internet: **43.6% → 71.7%** (2020–2024), **+28.2 pp**, el doble del avance nacional
  (+13.7 pp). Pasó del lugar 30 al 20. Con internet fijo, +29.7 pp. La distancia con el nacional
  bajó de 16 pp a 1.9 pp y **ya no es significativa** (p = 0.24).
- La barrera económica cedió: los hogares sin internet que lo atribuyen a **falta de recursos**
  bajaron de 73.6% a 55.3% (−18.3 pp, significativo), hoy igual que el nacional.
- Pero el **uso económico** no siguió al acceso: compras (34.8%), ventas (10.3%) y banca (16.4%)
  están en el promedio nacional o debajo, y la banca electrónica no cambió en 5 años
  (−0.8 pp, no significativo).
- **Computadora**: 37.2% de los hogares, 6.7 pp debajo del nacional (significativo), lugar 27 de
  32. Es la brecha de acceso que queda.

## 3. México: el celular avanza, la computadora no

- Hogares con computadora: **43.8% → 43.9%** en 5 años (cambio no significativo). En Yucatán
  incluso bajó (−1.5 pp, no significativo).
- En el mismo periodo los usuarios de smartphone subieron de 73.9% a 84.0% y los de internet de
  71.5% a 83.1%. La conectividad mexicana es **móvil**.
- Las barreras para no tener internet en el hogar son económicas o de interés, **no de
  infraestructura**: menos del 5% de los hogares sin internet dice que no hay proveedor en su
  localidad (en las tres entidades).

## 4. Valor económico

- **Comercio electrónico**: pasó de 3.3% del PIB nacional (2013) a **6.9% (2024, preliminar)**,
  2.31 billones de pesos. El salto de 2022 (+39% nominal) es el mayor de la serie. Dentro del
  comercio al por menor, el 21% del valor agregado ya es electrónico.
- **Sector 51 (información: telecom, internet, software, medios)**:
  - Yucatán es **4º de 32** en peso del sector 51 (fue 2º en 2007–2015), aunque con 1.0% queda
    debajo del promedio nacional (1.5%), que jala la Ciudad de México. Su peso baja desde 2015
    (2.0% → 1.0%): el sector crece, pero menos que el resto de su economía.
  - Tabasco: el sector 51 es solo 0.33% de su VAB, pero la minería (petróleo) es el **45%**. Sin
    ella, el sector pesa 0.60% y Tabasco pasa del lugar 29 al **13**. Cualquier comparación de
    estructura económica con Tabasco tiene que quitar el petróleo.
  - Los tres crecen en términos reales después de la caída de 2020 (pandemia): VAB real del
    sector 51 en 2023 ≈ 110 (Yucatán y Tabasco) y 122 (nacional), con 2018 = 100.

## 5. Contexto internacional

- México está en el lugar **30 de 32 países** con dato en usuarios de internet de 16 a 74 años
  (85.8% en 2024 vs 93.9% del promedio OECD).

## 6. Validación del pipeline

Las estimaciones nacionales calculadas aquí desde los microdatos se compararon con las cifras que
México reporta a la OECD (que salen de la misma encuesta): en **7 de 8 medidas coinciden al
centésimo** los 5 años (40 pares), y el 100% cae dentro del IC 90%. La única diferencia es
internet fijo (0.2–0.4 pp), por el tratamiento de "no sabe" (D12). Es una validación externa de
la ingesta, la armonización de preguntas entre años, los factores de expansión y la definición
de los universos.

## Cautelas

- Estimaciones por muestreo: ver IC 90% y calidad. Las razones minoritarias para no tener
  internet ("sin proveedor", "no sabe usarlo") tienen calidad moderada o baja en las entidades.
- PIB estatal 2023 y VABCOEL 2024 son preliminares. VABCOEL solo existe a nivel nacional.
- 2020 se levantó en pandemia. El panel empieza en 2020 porque 2019 no trae clave de entidad (D01).
- El nivel de entidad oculta la variación interna (Mérida vs el resto de Yucatán, Villahermosa vs el resto de Tabasco).
