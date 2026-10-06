-- Carga de la capa gold desde silver y creación de vistas.
-- Lo ejecuta src/silver_to_gold.py dentro de una transacción, después del TRUNCATE.
-- Vive en sql/gold/ para que Docker NO lo corra al crear la base (el entrypoint solo
-- ejecuta los archivos de primer nivel de /docker-entrypoint-initdb.d).
-- gold.dim_indicador y gold.fact_encuesta_tic NO se cargan aquí: las estimaciones de encuesta
-- (con error estándar por diseño muestral) las calcula silver_to_gold.py en Python.
-- Trazabilidad de los hechos: fuente y version_fuente se copian de silver; fecha_carga y run_id
-- los fija silver_to_gold.py con set_config('gold.fecha_carga' / 'gold.run_id') en la transacción.

-- --------------------------------------------------------------------------
-- Dimensiones
-- --------------------------------------------------------------------------
INSERT INTO gold.dim_entidad (cve_ent, nombre, es_foco)
SELECT cve_ent,
       CASE cve_ent WHEN '00' THEN 'México (nacional)' ELSE nombre END,
       es_foco
FROM silver.cat_entidad;

-- Años que cubre cualquiera de las fuentes, con el sexenio federal al que pertenecen
INSERT INTO gold.dim_tiempo (anio, sexenio)
SELECT a,
       CASE WHEN a <= 2006 THEN '2000-2006' WHEN a <= 2012 THEN '2006-2012'
            WHEN a <= 2018 THEN '2012-2018' WHEN a <= 2024 THEN '2018-2024' ELSE '2024-2030' END
FROM (SELECT min(anio)::INTEGER AS desde, max(anio)::INTEGER AS hasta
      FROM (SELECT anio FROM silver.vabcoel UNION ALL SELECT anio FROM silver.pib_entidad
            UNION ALL SELECT anio FROM silver.endutih_hogar UNION ALL SELECT anio FROM silver.oecd_ict) t) r,
     generate_series(r.desde, r.hasta) AS a;

INSERT INTO gold.dim_pais (cod_pais, nombre)
SELECT DISTINCT ON (cod_pais) cod_pais, pais
FROM silver.oecd_ict
ORDER BY cod_pais, anio DESC;

-- --------------------------------------------------------------------------
-- Hechos
-- --------------------------------------------------------------------------
INSERT INTO gold.fact_valor_entidad (anio, cve_ent, concepto, precios, valor_mdp, estatus_cifra,
                                     fuente, version_fuente, fecha_carga, run_id)
SELECT anio, cve_ent, concepto, precios, valor_mdp, estatus_cifra, fuente, version_fuente,
       current_setting('gold.fecha_carga')::TIMESTAMPTZ, current_setting('gold.run_id')::UUID
FROM silver.pib_entidad;

INSERT INTO gold.fact_comercio_electronico (anio, componente, medida, valor, estatus_cifra,
                                            fuente, version_fuente, fecha_carga, run_id)
SELECT anio, componente, medida, valor, estatus_cifra, fuente, version_fuente,
       current_setting('gold.fecha_carga')::TIMESTAMPTZ, current_setting('gold.run_id')::UUID
FROM silver.vabcoel;

INSERT INTO gold.fact_oecd_tic (anio, cod_pais, medida, desc_medida, unidad, valor, estatus_obs,
                                fuente, version_fuente, fecha_carga, run_id)
SELECT anio, cod_pais, medida, desc_medida, unidad, valor, estatus_obs, fuente, version_fuente,
       current_setting('gold.fecha_carga')::TIMESTAMPTZ, current_setting('gold.run_id')::UUID
FROM silver.oecd_ict;

-- --------------------------------------------------------------------------
-- Vistas
-- --------------------------------------------------------------------------

-- Valor económico por entidad y año (indicadores de VALOR).
--   participacion_51           = VAB del sector 51 / VAB total (precios corrientes), en %
--   participacion_51_no_minero = VAB 51 / (VAB total - VAB sector 21), en %. Tabasco es un
--                                estado petrolero: la minería infla su denominador y esconde
--                                el peso real del sector de información en el resto de la economía.
--   crecimiento_real_51        = variación anual del VAB 51 a precios de 2018, en %
CREATE OR REPLACE VIEW gold.valor_entidad_anio AS
WITH ancho AS (
    SELECT anio, cve_ent,
           max(valor_mdp) FILTER (WHERE concepto = 'vab_total' AND precios = 'corrientes')      AS vab_total,
           max(valor_mdp) FILTER (WHERE concepto = 'vab_51'    AND precios = 'corrientes')      AS vab_51,
           max(valor_mdp) FILTER (WHERE concepto = 'vab_21'    AND precios = 'corrientes')      AS vab_21,
           max(valor_mdp) FILTER (WHERE concepto = 'vab_51'    AND precios = 'constantes_2018') AS vab_51_real,
           max(valor_mdp) FILTER (WHERE concepto = 'vab_total' AND precios = 'constantes_2018') AS vab_total_real,
           max(estatus_cifra)                                                                   AS estatus_cifra
    FROM gold.fact_valor_entidad
    GROUP BY anio, cve_ent
)
SELECT a.anio, a.cve_ent, e.nombre, e.es_foco,
       a.vab_total, a.vab_51, a.vab_21, a.vab_51_real, a.vab_total_real,
       100 * a.vab_51 / NULLIF(a.vab_total, 0)                          AS participacion_51,
       100 * a.vab_51 / NULLIF(a.vab_total - a.vab_21, 0)               AS participacion_51_no_minero,
       100 * a.vab_21 / NULLIF(a.vab_total, 0)                          AS participacion_21,
       100 * (a.vab_51_real / NULLIF(lag(a.vab_51_real) OVER w, 0) - 1)       AS crecimiento_real_51,
       100 * (a.vab_total_real / NULLIF(lag(a.vab_total_real) OVER w, 0) - 1) AS crecimiento_real_total,
       a.estatus_cifra
FROM ancho a
JOIN gold.dim_entidad e USING (cve_ent)
WINDOW w AS (PARTITION BY a.cve_ent ORDER BY a.anio);

-- Comercio electrónico nacional (VABCOEL), una fila por año.
CREATE OR REPLACE VIEW gold.comercio_electronico_anio AS
SELECT anio,
       max(valor) FILTER (WHERE componente = 'total' AND medida = 'mdp_corrientes')                 AS vab_coel_mdp,
       max(valor) FILTER (WHERE componente = 'total' AND medida = 'mdp_constantes_2018')            AS vab_coel_real_mdp,
       max(valor) FILTER (WHERE componente = 'total' AND medida = 'pct_pib')                        AS pct_pib,
       max(valor) FILTER (WHERE componente = 'total' AND medida = 'pct_vab')                        AS pct_vab,
       max(valor) FILTER (WHERE componente = 'comercio_al_por_mayor' AND medida = 'mdp_corrientes') AS mayor_mdp,
       max(valor) FILTER (WHERE componente = 'comercio_al_por_menor' AND medida = 'mdp_corrientes') AS menor_mdp,
       max(valor) FILTER (WHERE componente = 'otros_servicios' AND medida = 'mdp_corrientes')       AS otros_servicios_mdp,
       max(valor) FILTER (WHERE componente = 'comercio_al_por_menor' AND medida = 'pct_vab_actividad')
                                                                                                    AS pct_del_comercio_al_por_menor,
       max(estatus_cifra)                                                                           AS estatus_cifra
FROM gold.fact_comercio_electronico
GROUP BY anio;

-- Panel entidad × año con los indicadores de encuesta (grupo de edad total) en columnas
-- y los de valor económico del mismo año. Solo años con ENDUTIH.
CREATE OR REPLACE VIEW gold.kpi_entidad_anio AS
SELECT f.anio, f.cve_ent, e.nombre, e.es_foco,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'hog_internet')         AS hog_internet,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'hog_computadora')      AS hog_computadora,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'hog_internet_fija')    AS hog_internet_fija,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'hog_celular')          AS hog_celular,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'pob_internet')         AS pob_internet,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'pob_computadora')      AS pob_computadora,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'pob_celular')          AS pob_celular,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'pob_smartphone')       AS pob_smartphone,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'pob_redes_sociales')   AS pob_redes_sociales,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'usu_compra')           AS usu_compra,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'usu_vende')            AS usu_vende,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'usu_paga')             AS usu_paga,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'usu_banca')            AS usu_banca,
       max(f.estimacion) FILTER (WHERE f.id_indicador = 'sin_internet_recursos') AS sin_internet_recursos,
       v.participacion_51,
       v.participacion_51_no_minero,
       v.crecimiento_real_51
FROM gold.fact_encuesta_tic f
JOIN gold.dim_entidad e USING (cve_ent)
LEFT JOIN gold.valor_entidad_anio v USING (anio, cve_ent)
WHERE f.grupo_edad = 'total'
GROUP BY f.anio, f.cve_ent, e.nombre, e.es_foco, v.participacion_51, v.participacion_51_no_minero,
         v.crecimiento_real_51;
