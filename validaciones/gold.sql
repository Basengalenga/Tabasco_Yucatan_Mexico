-- Consultas de validación de la capa gold. Cada indicador se recalcula directamente desde silver
-- o desde los hechos (sin las vistas) para demostrar que el warehouse reproduce las cifras.
-- Correr con:
--   docker exec -i ed_dw psql -U admin -d economia_digital_dw < validaciones/gold.sql

\set anio 2024

-- 1. Proporciones ponderadas recalculadas desde silver vs gold (diferencia debe ser ~0)
WITH silver_h AS (
    SELECT cve_ent, 100.0 * sum(fac_hog) FILTER (WHERE tiene_internet) / sum(fac_hog) AS hog_internet,
           100.0 * sum(fac_hog) FILTER (WHERE tiene_computadora) / sum(fac_hog) AS hog_computadora
    FROM silver.endutih_hogar WHERE anio = :anio AND cve_ent IN ('27', '31') GROUP BY cve_ent
    UNION ALL
    SELECT '00', 100.0 * sum(fac_hog) FILTER (WHERE tiene_internet) / sum(fac_hog),
           100.0 * sum(fac_hog) FILTER (WHERE tiene_computadora) / sum(fac_hog)
    FROM silver.endutih_hogar WHERE anio = :anio
)
SELECT s.cve_ent,
       round(s.hog_internet::NUMERIC, 3) AS silver_hog_internet,
       round(g1.estimacion::NUMERIC, 3) AS gold_hog_internet,
       round(s.hog_computadora::NUMERIC, 3) AS silver_hog_computadora,
       round(g2.estimacion::NUMERIC, 3) AS gold_hog_computadora
FROM silver_h s
JOIN gold.fact_encuesta_tic g1 ON g1.cve_ent = s.cve_ent AND g1.anio = :anio AND g1.id_indicador = 'hog_internet' AND g1.grupo_edad = 'total'
JOIN gold.fact_encuesta_tic g2 ON g2.cve_ent = s.cve_ent AND g2.anio = :anio AND g2.id_indicador = 'hog_computadora' AND g2.grupo_edad = 'total'
ORDER BY s.cve_ent;

-- 2. Indicador condicional: compran por internet / usuarios de internet
SELECT cve_ent,
       round((100.0 * sum(fac_per) FILTER (WHERE compra_internet) / sum(fac_per))::NUMERIC, 3) AS usu_compra_silver
FROM silver.endutih_persona WHERE anio = :anio AND usa_internet AND cve_ent IN ('27', '31')
GROUP BY cve_ent ORDER BY cve_ent;

SELECT cve_ent, round(estimacion::NUMERIC, 3) AS usu_compra_gold, round(error_estandar::NUMERIC, 3) AS ee, calidad
FROM gold.fact_encuesta_tic
WHERE anio = :anio AND id_indicador = 'usu_compra' AND grupo_edad = 'total' AND cve_ent IN ('27', '31')
ORDER BY cve_ent;

-- 3. Panel de las tres entidades foco (vista kpi_entidad_anio)
SELECT anio, nombre, round(hog_internet::NUMERIC, 1) AS hog_internet, round(pob_internet::NUMERIC, 1) AS pob_internet,
       round(usu_compra::NUMERIC, 1) AS usu_compra, round(usu_vende::NUMERIC, 1) AS usu_vende,
       round(participacion_51_no_minero::NUMERIC, 2) AS sector51_no_minero
FROM gold.kpi_entidad_anio WHERE es_foco ORDER BY nombre, anio;

-- 4. Valor: peso del sector 51 recalculado desde el hecho
SELECT v.anio, v.cve_ent,
       round((100 * v51.valor_mdp / vt.valor_mdp)::NUMERIC, 3) AS desde_hechos,
       round(v.participacion_51::NUMERIC, 3) AS vista
FROM gold.valor_entidad_anio v
JOIN gold.fact_valor_entidad v51 ON v51.anio = v.anio AND v51.cve_ent = v.cve_ent AND v51.concepto = 'vab_51' AND v51.precios = 'corrientes'
JOIN gold.fact_valor_entidad vt  ON vt.anio = v.anio AND vt.cve_ent = v.cve_ent AND vt.concepto = 'vab_total' AND vt.precios = 'corrientes'
WHERE v.es_foco AND v.anio >= 2020 ORDER BY v.cve_ent, v.anio;

-- 5. Brechas significativas en el año (Yucatán vs Tabasco y vs nacional)
SELECT b.id_indicador, b.entidad_a, b.entidad_b, round(b.diferencia_pp::NUMERIC, 1) AS dif_pp,
       round(b.p_value::NUMERIC, 4) AS p
FROM gold.resultado_brecha b WHERE b.anio = :anio AND b.significativa ORDER BY abs(b.diferencia_pp) DESC;

-- 6. Validación externa: ENDUTIH vs OECD
SELECT medida_oecd, count(*) AS anios, round(max(abs(diferencia_pp))::NUMERIC, 3) AS max_dif_pp,
       bool_and(dentro_ic) AS siempre_dentro_ic
FROM gold.resultado_validacion_oecd GROUP BY medida_oecd ORDER BY medida_oecd;

-- 7. Integridad referencial de los hechos (todas deben dar 0)
SELECT 'fact_encuesta_tic sin entidad' AS regla, count(*) FROM gold.fact_encuesta_tic f
LEFT JOIN gold.dim_entidad e USING (cve_ent) WHERE e.cve_ent IS NULL
UNION ALL
SELECT 'fact_encuesta_tic sin indicador', count(*) FROM gold.fact_encuesta_tic f
LEFT JOIN gold.dim_indicador i USING (id_indicador) WHERE i.id_indicador IS NULL
UNION ALL
SELECT 'fact_oecd_tic sin país', count(*) FROM gold.fact_oecd_tic f
LEFT JOIN gold.dim_pais p USING (cod_pais) WHERE p.cod_pais IS NULL;
