"""
API de economia_digital_dw (FastAPI).

Expone en JSON la capa gold que consume el dashboard: estimaciones de la ENDUTIH,
valor económico (PIB estatal y comercio electrónico), comparación OECD y las tablas
resultado_* de src/gold_analytics.py. Las únicas lecturas fuera de gold son las bitácoras
de silver (decisiones de limpieza) y el mapeo de variables de la ENDUTIH, para la
pestaña de calidad de datos.

Correr local:   uvicorn main:app --port 8000   (desde api/)
Correr Docker:  docker compose up -d  ->  http://api:8000 dentro de la red de docker
"""

import os
from decimal import Decimal

import pandas as pd
from fastapi import FastAPI, Response
from sqlalchemy import create_engine

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
DB_URL = os.environ.get("DB_URL", "postgresql+psycopg2://admin:admin123@db:5432/economia_digital_dw")

motor = create_engine(DB_URL)
app = FastAPI(title="Economía digital: Yucatán vs Tabasco vs México")


# --------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------
def consulta(sql: str) -> pd.DataFrame:
    df = pd.read_sql(sql, motor)
    # Las columnas NUMERIC de PostgreSQL llegan como Decimal; se pasan a float
    for c in df.columns:
        if df[c].map(lambda v: isinstance(v, Decimal)).any():
            df[c] = df[c].astype(float)
    for c in ("cve_ent", "entidad_a", "entidad_b"):
        if c in df.columns:
            df[c] = df[c].str.strip()
    return df


def registros(sql: str) -> Response:
    # to_json convierte NaN en null y las fechas a ISO 8601; double_precision=15 evita que redondee
    return Response(consulta(sql).to_json(orient="records", date_format="iso", double_precision=15),
                    media_type="application/json")


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/entidades")
def entidades():
    return registros("SELECT * FROM gold.dim_entidad ORDER BY cve_ent")


@app.get("/indicadores")
def indicadores():
    return registros("SELECT * FROM gold.dim_indicador ORDER BY orden")


@app.get("/encuesta")
def encuesta():
    """Estimaciones ENDUTIH de las 33 entidades (grupo de edad total) con error estándar e IC 90%."""
    return registros("""
        SELECT anio, cve_ent, id_indicador, estimacion, error_estandar, cv, li_90, ls_90, calidad,
               n_muestra, numerador_expandido, universo_expandido
        FROM gold.fact_encuesta_tic WHERE grupo_edad = 'total'
    """)


@app.get("/valor")
def valor():
    return registros("SELECT * FROM gold.valor_entidad_anio WHERE anio >= 2013")


@app.get("/comercio-electronico")
def comercio_electronico():
    return registros("SELECT * FROM gold.comercio_electronico_anio ORDER BY anio")


@app.get("/oecd")
def oecd():
    return registros("""
        SELECT f.anio, f.cod_pais, p.nombre AS pais, f.medida, f.desc_medida, f.unidad, f.valor, f.estatus_obs
        FROM gold.fact_oecd_tic f JOIN gold.dim_pais p USING (cod_pais)
    """)


@app.get("/resultados/brecha")
def resultado_brecha():
    return registros("SELECT * FROM gold.resultado_brecha")


@app.get("/resultados/tendencia")
def resultado_tendencia():
    return registros("SELECT * FROM gold.resultado_tendencia")


@app.get("/resultados/ranking")
def resultado_ranking():
    return registros("SELECT * FROM gold.resultado_ranking")


@app.get("/resultados/validacion-oecd")
def resultado_validacion_oecd():
    return registros("SELECT * FROM gold.resultado_validacion_oecd ORDER BY medida_oecd, anio")


@app.get("/calidad/decisiones")
def decisiones():
    """Bitácora de la última corrida de silver: descartes, recodificaciones y decisiones de limpieza."""
    return registros("""
        SELECT tabla, metrica, valor, detalle, fecha_carga FROM silver.etl_log
        WHERE run_id = (SELECT run_id FROM silver.etl_log ORDER BY fecha_carga DESC, id DESC LIMIT 1)
        ORDER BY id
    """)


@app.get("/calidad/mapeo-variables")
def mapeo_variables():
    return registros("SELECT anio, concepto, tabla_bronze, columna, descripcion_diccionario "
                     "FROM silver.endutih_mapeo_variables ORDER BY concepto, anio")


@app.get("/etl-log")
def etl_log():
    return registros("""
        SELECT tabla, metrica, valor, fecha_carga FROM gold.etl_log
        WHERE run_id IN (SELECT run_id FROM gold.etl_log GROUP BY run_id ORDER BY max(fecha_carga) DESC LIMIT 2)
        ORDER BY fecha_carga, id
    """)
