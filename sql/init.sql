-- DDL de economia_digital_dw: esquemas y tablas de silver y gold.
-- Docker lo ejecuta al crear el volumen de la base; los scripts de silver y gold lo vuelven a
-- aplicar al inicio (es idempotente). Las tablas de bronze NO están aquí: el extractor las crea
-- con las columnas exactas de cada archivo de la fuente (ver src/extractor_to_bronze.py).

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ==========================================================================
-- Capa silver: datos limpios, tipados y armonizados, uno a uno por fuente.
-- La carga la hace src/bronze_to_silver.py.
-- Llave de integración geográfica: cve_ent CHAR(2) ('00' = nacional, '27' = Tabasco,
-- '31' = Yucatán). Nunca se une por nombre salvo en el PIB estatal, que solo trae el
-- nombre y se valida contra el catálogo (ver docs/decisiones_limpieza.md).
-- ==========================================================================

-- 1. Catálogo de entidades (INEGI, catálogo de la ENDUTIH 2024) + fila nacional '00'
CREATE TABLE IF NOT EXISTS silver.cat_entidad (
    cve_ent             CHAR(2)       PRIMARY KEY CHECK (cve_ent ~ '^[0-9]{2}$'),
    nombre              TEXT          NOT NULL,
    nombre_normalizado  TEXT          NOT NULL UNIQUE,
    es_foco             BOOLEAN       NOT NULL,   -- Yucatán, Tabasco y nacional
    fuente              TEXT          NOT NULL,
    version_fuente      TEXT          NOT NULL,
    fecha_carga         TIMESTAMPTZ   NOT NULL
);

-- 2. Mapeo de variables ENDUTIH: qué columna de qué tabla mide cada concepto en cada año.
--    La numeración de las preguntas cambia entre años; cada mapeo se valida contra el texto
--    del diccionario de datos de INEGI (palabra clave obligatoria).
CREATE TABLE IF NOT EXISTS silver.endutih_mapeo_variables (
    anio                    SMALLINT      NOT NULL,
    concepto                TEXT          NOT NULL,
    tabla_bronze            TEXT          NOT NULL,
    columna                 TEXT          NOT NULL,
    descripcion_diccionario TEXT          NOT NULL,
    fuente                  TEXT          NOT NULL,
    version_fuente          TEXT          NOT NULL,
    fecha_carga             TIMESTAMPTZ   NOT NULL,
    PRIMARY KEY (anio, concepto, columna)
);

-- 3. ENDUTIH, hogares (una fila por hogar entrevistado y año).
--    Banderas de población: NULL = 'no sabe' / 'no responde' en la fuente.
CREATE TABLE IF NOT EXISTS silver.endutih_hogar (
    anio                SMALLINT      NOT NULL CHECK (anio BETWEEN 2020 AND 2030),
    upm                 TEXT          NOT NULL,
    viv_sel             TEXT          NOT NULL,
    hogar               TEXT          NOT NULL,
    cve_ent             CHAR(2)       NOT NULL REFERENCES silver.cat_entidad (cve_ent),
    est_dis             TEXT          NOT NULL,   -- estrato de diseño
    upm_dis             TEXT          NOT NULL,   -- UPM de diseño
    tloc                SMALLINT,                 -- tamaño de localidad (1 = 100 mil hab. y más)
    fac_hog             INTEGER       NOT NULL CHECK (fac_hog > 0),
    tiene_computadora   BOOLEAN       NOT NULL,   -- computadora de escritorio, laptop o tablet
    tiene_internet      BOOLEAN       NOT NULL,
    internet_fija       BOOLEAN,                  -- conexión fija o fija+móvil; NULL = no sabe
    tiene_celular       BOOLEAN       NOT NULL,
    razon_sin_internet  SMALLINT      CHECK (razon_sin_internet BETWEEN 1 AND 10),
    fuente              TEXT          NOT NULL,
    version_fuente      TEXT          NOT NULL,
    fecha_carga         TIMESTAMPTZ   NOT NULL,
    PRIMARY KEY (anio, upm, viv_sel, hogar)
);

-- 4. ENDUTIH, persona elegida de 6 años o más (cuestionario de usuario, una por hogar).
--    Las preguntas de uso de internet solo se hacen a usuarios de internet; para los no
--    usuarios la fuente deja el campo vacío y aquí se guarda FALSE (no realizó la actividad).
CREATE TABLE IF NOT EXISTS silver.endutih_persona (
    anio                SMALLINT      NOT NULL CHECK (anio BETWEEN 2020 AND 2030),
    upm                 TEXT          NOT NULL,
    viv_sel             TEXT          NOT NULL,
    hogar               TEXT          NOT NULL,
    num_ren             TEXT          NOT NULL,
    cve_ent             CHAR(2)       NOT NULL REFERENCES silver.cat_entidad (cve_ent),
    est_dis             TEXT          NOT NULL,
    upm_dis             TEXT          NOT NULL,
    tloc                SMALLINT,
    fac_per             INTEGER       NOT NULL CHECK (fac_per > 0),
    edad                SMALLINT      NOT NULL CHECK (edad >= 6),
    sexo                SMALLINT      CHECK (sexo IN (1, 2)),
    usa_internet        BOOLEAN       NOT NULL,
    usa_computadora     BOOLEAN       NOT NULL,
    usa_celular         BOOLEAN       NOT NULL,
    usa_smartphone      BOOLEAN       NOT NULL,
    usa_redes_sociales  BOOLEAN       NOT NULL,
    compra_internet     BOOLEAN       NOT NULL,
    vende_internet      BOOLEAN       NOT NULL,
    paga_internet       BOOLEAN       NOT NULL,
    banca_electronica   BOOLEAN       NOT NULL,
    fuente              TEXT          NOT NULL,
    version_fuente      TEXT          NOT NULL,
    fecha_carga         TIMESTAMPTZ   NOT NULL,
    PRIMARY KEY (anio, upm, viv_sel, hogar, num_ren)
);

-- 5. Valor Agregado Bruto del Comercio Electrónico (INEGI, cuentas nacionales), nacional.
CREATE TABLE IF NOT EXISTS silver.vabcoel (
    anio            SMALLINT          NOT NULL,
    componente      TEXT              NOT NULL CHECK (componente IN
                        ('total', 'comercio_al_por_mayor', 'comercio_al_por_menor', 'otros_servicios')),
    medida          TEXT              NOT NULL CHECK (medida IN
                        ('mdp_corrientes', 'mdp_constantes_2018', 'pct_pib', 'pct_vab',
                         'pct_vab_actividad')),
    valor           DOUBLE PRECISION  NOT NULL,
    estatus_cifra   TEXT              NOT NULL CHECK (estatus_cifra IN ('definitiva', 'revisada', 'preliminar')),
    fuente          TEXT              NOT NULL,
    version_fuente  TEXT              NOT NULL,
    fecha_carga     TIMESTAMPTZ       NOT NULL,
    PRIMARY KEY (anio, componente, medida)
);

-- 6. PIB por entidad federativa (INEGI), VAB total y de los sectores 51 y 21.
CREATE TABLE IF NOT EXISTS silver.pib_entidad (
    anio            SMALLINT          NOT NULL,
    cve_ent         CHAR(2)           NOT NULL REFERENCES silver.cat_entidad (cve_ent),
    concepto        TEXT              NOT NULL CHECK (concepto IN ('vab_total', 'vab_51', 'vab_21')),
    precios         TEXT              NOT NULL CHECK (precios IN ('corrientes', 'constantes_2018')),
    valor_mdp       DOUBLE PRECISION  NOT NULL,
    estatus_cifra   TEXT              NOT NULL CHECK (estatus_cifra IN ('definitiva', 'revisada', 'preliminar')),
    fuente          TEXT              NOT NULL,
    version_fuente  TEXT              NOT NULL,
    fecha_carga     TIMESTAMPTZ       NOT NULL,
    PRIMARY KEY (anio, cve_ent, concepto, precios)
);

-- 7. OECD ICT Access and Usage by Households and Individuals (comparación internacional).
CREATE TABLE IF NOT EXISTS silver.oecd_ict (
    anio            SMALLINT          NOT NULL,
    cod_pais        TEXT              NOT NULL,
    pais            TEXT              NOT NULL,
    medida          TEXT              NOT NULL,
    desc_medida     TEXT              NOT NULL,
    unidad          TEXT              NOT NULL CHECK (unidad IN ('pct_hogares', 'pct_personas_16_74')),
    valor           DOUBLE PRECISION  NOT NULL CHECK (valor BETWEEN 0 AND 100),
    estatus_obs     TEXT,
    fuente          TEXT              NOT NULL,
    version_fuente  TEXT              NOT NULL,
    fecha_carga     TIMESTAMPTZ       NOT NULL,
    PRIMARY KEY (anio, cod_pais, medida)
);

-- 8. Bitácora: conteos, descartes y decisiones de limpieza de cada corrida
CREATE TABLE IF NOT EXISTS silver.etl_log (
    id           BIGSERIAL     PRIMARY KEY,
    run_id       UUID          NOT NULL,
    tabla        TEXT          NOT NULL,
    metrica      TEXT          NOT NULL,
    valor        BIGINT        NOT NULL,
    detalle      TEXT,
    fecha_carga  TIMESTAMPTZ   NOT NULL
);

-- ==========================================================================
-- Capa gold: modelo dimensional. La carga la hacen src/silver_to_gold.py
-- (sql/gold/gold.sql + estimaciones de encuesta) y src/gold_analytics.py (resultado_*).
-- ==========================================================================

CREATE TABLE IF NOT EXISTS gold.dim_entidad (
    cve_ent   CHAR(2)   PRIMARY KEY,
    nombre    TEXT      NOT NULL,
    es_foco   BOOLEAN   NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    anio      SMALLINT  PRIMARY KEY,
    sexenio   TEXT      NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_indicador (
    id_indicador  TEXT      PRIMARY KEY,
    nombre        TEXT      NOT NULL,
    dimension     TEXT      NOT NULL CHECK (dimension IN ('acceso', 'uso', 'valor', 'brecha')),
    unidad        TEXT      NOT NULL,
    universo      TEXT      NOT NULL,
    fuente        TEXT      NOT NULL,
    descripcion   TEXT      NOT NULL,
    orden         SMALLINT  NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_pais (
    cod_pais  TEXT  PRIMARY KEY,
    nombre    TEXT  NOT NULL
);

-- Estimaciones de la ENDUTIH: anio × entidad × indicador × grupo de edad.
-- Error estándar por linealización de Taylor con el diseño muestral (estrato est_dis, UPM upm_dis).
CREATE TABLE IF NOT EXISTS gold.fact_encuesta_tic (
    anio                 SMALLINT          NOT NULL REFERENCES gold.dim_tiempo (anio),
    cve_ent              CHAR(2)           NOT NULL REFERENCES gold.dim_entidad (cve_ent),
    id_indicador         TEXT              NOT NULL REFERENCES gold.dim_indicador (id_indicador),
    grupo_edad           TEXT              NOT NULL CHECK (grupo_edad IN ('total', '16_74')),
    estimacion           DOUBLE PRECISION  NOT NULL,   -- porcentaje (0-100)
    error_estandar       DOUBLE PRECISION  NOT NULL,
    cv                   DOUBLE PRECISION,             -- coeficiente de variación, en porcentaje
    li_90                DOUBLE PRECISION  NOT NULL,
    ls_90                DOUBLE PRECISION  NOT NULL,
    calidad              TEXT              NOT NULL CHECK (calidad IN ('alta', 'moderada', 'baja')),
    n_muestra            INTEGER           NOT NULL,   -- registros en el denominador
    numerador_expandido  BIGINT            NOT NULL,
    universo_expandido   BIGINT            NOT NULL,
    fuente               TEXT              NOT NULL,
    version_fuente       TEXT              NOT NULL,
    fecha_carga          TIMESTAMPTZ       NOT NULL,
    run_id               UUID              NOT NULL,
    PRIMARY KEY (anio, cve_ent, id_indicador, grupo_edad)
);

CREATE TABLE IF NOT EXISTS gold.fact_valor_entidad (
    anio            SMALLINT          NOT NULL REFERENCES gold.dim_tiempo (anio),
    cve_ent         CHAR(2)           NOT NULL REFERENCES gold.dim_entidad (cve_ent),
    concepto        TEXT              NOT NULL,
    precios         TEXT              NOT NULL,
    valor_mdp       DOUBLE PRECISION  NOT NULL,
    estatus_cifra   TEXT              NOT NULL,
    fuente          TEXT              NOT NULL,
    version_fuente  TEXT              NOT NULL,
    fecha_carga     TIMESTAMPTZ       NOT NULL,
    run_id          UUID              NOT NULL,
    PRIMARY KEY (anio, cve_ent, concepto, precios)
);

CREATE TABLE IF NOT EXISTS gold.fact_comercio_electronico (
    anio            SMALLINT          NOT NULL REFERENCES gold.dim_tiempo (anio),
    componente      TEXT              NOT NULL,
    medida          TEXT              NOT NULL,
    valor           DOUBLE PRECISION  NOT NULL,
    estatus_cifra   TEXT              NOT NULL,
    fuente          TEXT              NOT NULL,
    version_fuente  TEXT              NOT NULL,
    fecha_carga     TIMESTAMPTZ       NOT NULL,
    run_id          UUID              NOT NULL,
    PRIMARY KEY (anio, componente, medida)
);

CREATE TABLE IF NOT EXISTS gold.fact_oecd_tic (
    anio            SMALLINT          NOT NULL REFERENCES gold.dim_tiempo (anio),
    cod_pais        TEXT              NOT NULL REFERENCES gold.dim_pais (cod_pais),
    medida          TEXT              NOT NULL,
    desc_medida     TEXT              NOT NULL,
    unidad          TEXT              NOT NULL,
    valor           DOUBLE PRECISION  NOT NULL,
    estatus_obs     TEXT,
    fuente          TEXT              NOT NULL,
    version_fuente  TEXT              NOT NULL,
    fecha_carga     TIMESTAMPTZ       NOT NULL,
    run_id          UUID              NOT NULL,
    PRIMARY KEY (anio, cod_pais, medida)
);

-- Resultados de src/gold_analytics.py
CREATE TABLE IF NOT EXISTS gold.resultado_brecha (
    anio            SMALLINT          NOT NULL,
    id_indicador    TEXT              NOT NULL,
    entidad_a       CHAR(2)           NOT NULL,
    entidad_b       CHAR(2)           NOT NULL,
    diferencia_pp   DOUBLE PRECISION  NOT NULL,   -- a - b, puntos porcentuales
    error_estandar  DOUBLE PRECISION  NOT NULL,
    z               DOUBLE PRECISION,
    p_value         DOUBLE PRECISION,
    significativa   BOOLEAN           NOT NULL,   -- p < 0.10 (nivel de confianza de INEGI: 90 por ciento)
    PRIMARY KEY (anio, id_indicador, entidad_a, entidad_b)
);

CREATE TABLE IF NOT EXISTS gold.resultado_tendencia (
    cve_ent              CHAR(2)           NOT NULL,
    id_indicador         TEXT              NOT NULL,
    anio_inicial         SMALLINT          NOT NULL,
    anio_final           SMALLINT          NOT NULL,
    valor_inicial        DOUBLE PRECISION  NOT NULL,
    valor_final          DOUBLE PRECISION  NOT NULL,
    cambio_pp            DOUBLE PRECISION  NOT NULL,
    error_estandar       DOUBLE PRECISION  NOT NULL,
    p_value              DOUBLE PRECISION,
    significativo        BOOLEAN           NOT NULL,
    pendiente_pp_anual   DOUBLE PRECISION  NOT NULL,   -- MCO sobre los años disponibles
    PRIMARY KEY (cve_ent, id_indicador)
);

CREATE TABLE IF NOT EXISTS gold.resultado_ranking (
    anio          SMALLINT          NOT NULL,
    id_indicador  TEXT              NOT NULL,
    cve_ent       CHAR(2)           NOT NULL,
    estimacion    DOUBLE PRECISION  NOT NULL,
    rango         SMALLINT          NOT NULL,   -- 1 = valor más alto de las 32 entidades
    n_entidades   SMALLINT          NOT NULL,
    PRIMARY KEY (anio, id_indicador, cve_ent)
);

CREATE TABLE IF NOT EXISTS gold.resultado_validacion_oecd (
    anio            SMALLINT          NOT NULL,
    medida_oecd     TEXT              NOT NULL,
    id_indicador    TEXT              NOT NULL,
    valor_oecd      DOUBLE PRECISION  NOT NULL,
    valor_endutih   DOUBLE PRECISION  NOT NULL,
    li_90           DOUBLE PRECISION  NOT NULL,
    ls_90           DOUBLE PRECISION  NOT NULL,
    diferencia_pp   DOUBLE PRECISION  NOT NULL,
    dentro_ic       BOOLEAN           NOT NULL,
    PRIMARY KEY (anio, medida_oecd)
);

CREATE TABLE IF NOT EXISTS gold.etl_log (
    id           BIGSERIAL     PRIMARY KEY,
    run_id       UUID          NOT NULL,
    tabla        TEXT          NOT NULL,
    metrica      TEXT          NOT NULL,
    valor        BIGINT        NOT NULL,
    fecha_carga  TIMESTAMPTZ   NOT NULL
);
