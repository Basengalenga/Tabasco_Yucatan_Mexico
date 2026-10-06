-- Validaciones post-carga de la capa silver.
-- Correr con:
--   docker exec -i ed_dw psql -U admin -d economia_digital_dw < validaciones/silver.sql
-- No vive en ./sql porque esa carpeta se monta en /docker-entrypoint-initdb.d y Docker
-- ejecutaría estas consultas al crear la base, cuando bronze todavía no existe.

-- 1. Conteo de filas por tabla
SELECT 'cat_entidad' AS tabla, count(*) AS filas FROM silver.cat_entidad
UNION ALL SELECT 'endutih_mapeo_variables', count(*) FROM silver.endutih_mapeo_variables
UNION ALL SELECT 'endutih_hogar', count(*) FROM silver.endutih_hogar
UNION ALL SELECT 'endutih_persona', count(*) FROM silver.endutih_persona
UNION ALL SELECT 'vabcoel', count(*) FROM silver.vabcoel
UNION ALL SELECT 'pib_entidad', count(*) FROM silver.pib_entidad
UNION ALL SELECT 'oecd_ict', count(*) FROM silver.oecd_ict;

-- 2. Bronze -> silver sin pérdida de registros de la ENDUTIH (diferencia debe ser 0)
SELECT anio, b.n AS bronze, s.n AS silver, b.n - s.n AS diferencia
FROM (SELECT 2020 AS anio, count(*) AS n FROM bronze.endutih_hogares_2020
      UNION ALL SELECT 2021, count(*) FROM bronze.endutih_hogares_2021
      UNION ALL SELECT 2022, count(*) FROM bronze.endutih_hogares_2022
      UNION ALL SELECT 2023, count(*) FROM bronze.endutih_hogares_2023
      UNION ALL SELECT 2024, count(*) FROM bronze.endutih_hogares_2024) b
JOIN (SELECT anio, count(*) AS n FROM silver.endutih_hogar GROUP BY anio) s USING (anio)
ORDER BY anio;

-- 3. Cobertura: 32 entidades por año, muestra de Yucatán y Tabasco
SELECT anio, count(DISTINCT cve_ent) AS entidades,
       count(*) FILTER (WHERE cve_ent = '31') AS hogares_yucatan,
       count(*) FILTER (WHERE cve_ent = '27') AS hogares_tabasco,
       sum(fac_hog) AS hogares_expandidos
FROM silver.endutih_hogar GROUP BY anio ORDER BY anio;

-- 4. Consistencia de saltos (todas deben dar 0)
SELECT 'actividades contestadas por no usuarios' AS regla, count(*) AS violaciones
FROM silver.endutih_persona
WHERE NOT usa_internet AND (compra_internet OR vende_internet OR paga_internet OR banca_electronica OR usa_redes_sociales)
UNION ALL
SELECT 'smartphone sin usar celular', count(*) FROM silver.endutih_persona WHERE usa_smartphone AND NOT usa_celular
UNION ALL
SELECT 'internet fijo sin internet', count(*) FROM silver.endutih_hogar WHERE internet_fija AND NOT tiene_internet
UNION ALL
SELECT 'razón sin internet en hogar conectado', count(*) FROM silver.endutih_hogar
WHERE tiene_internet AND razon_sin_internet IS NOT NULL
UNION ALL
SELECT 'informantes menores de 6 años', count(*) FROM silver.endutih_persona WHERE edad < 6;

-- 5. Estratos con una sola UPM (deben ser 0: el error estándar los necesita con 2 o más)
SELECT anio, count(*) AS estratos_con_una_upm
FROM (SELECT anio, est_dis, count(DISTINCT upm_dis) AS upms FROM silver.endutih_hogar GROUP BY 1, 2) t
WHERE upms < 2 GROUP BY anio;

-- 6. PIB: la suma de las entidades coincide con el nacional (diferencia relativa < 0.1%)
SELECT anio, concepto, precios,
       round((sum(valor_mdp) FILTER (WHERE cve_ent <> '00') / max(valor_mdp) FILTER (WHERE cve_ent = '00') - 1)::NUMERIC, 6)
         AS diferencia_relativa
FROM silver.pib_entidad WHERE anio >= 2018
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- 7. VABCOEL: componentes suman el total
SELECT anio, round(sum(valor) FILTER (WHERE componente <> 'total')::NUMERIC, 1) AS suma_componentes,
       round(max(valor) FILTER (WHERE componente = 'total')::NUMERIC, 1) AS total
FROM silver.vabcoel WHERE medida = 'mdp_corrientes' GROUP BY anio ORDER BY anio;

-- 8. Mapeo de preguntas por año (renumeraciones de la ENDUTIH)
SELECT concepto, string_agg(anio || ':' || columna, '  ' ORDER BY anio, columna) AS columnas
FROM silver.endutih_mapeo_variables GROUP BY concepto ORDER BY concepto;

-- Extra: bitácora de decisiones de la última corrida
SELECT tabla, metrica, valor, detalle
FROM silver.etl_log
WHERE run_id = (SELECT run_id FROM silver.etl_log ORDER BY fecha_carga DESC, id DESC LIMIT 1)
ORDER BY id;
