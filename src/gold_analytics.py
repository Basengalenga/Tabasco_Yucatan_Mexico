"""
Análisis estadístico sobre gold de economia_digital_dw.

Lee SOLO de gold (fact_encuesta_tic, valor_entidad_anio, fact_oecd_tic) y calcula:

    gold.resultado_brecha           <- Yucatán vs Tabasco, Yucatán vs nacional y Tabasco vs
                                       nacional, por indicador y año, con prueba z
    gold.resultado_tendencia        <- cambio del primer al último año de la ENDUTIH por entidad
                                       foco, con prueba z, y pendiente por MCO (pp por año)
    gold.resultado_ranking          <- lugar de cada entidad entre las 32, por indicador y año
    gold.resultado_validacion_oecd  <- estimaciones nacionales de la ENDUTIH vs las cifras que
                                       México reporta a OECD (validación cruzada del pipeline)

Pruebas de diferencias (nivel de confianza 90%, el que usa INEGI):
    - Entre dos entidades: muestras independientes (los estratos están anidados en las
      entidades), V(a - b) = V(a) + V(b).
    - Entidad vs nacional: el nacional incluye a la entidad. Con s = peso de la entidad en el
      universo nacional, nacional = s·entidad + (1 - s)·resto, así que
      Cov(entidad, nacional) = s·V(entidad) y V(e - n) = V(e) + V(n) - 2·s·V(e).
    - Entre años: levantamientos independientes, V(final - inicial) = V(final) + V(inicial).

Manejo de errores (fail-fast):
    Primero se calcula todo en memoria; después TRUNCATE + INSERT de las tablas
    resultado_* en una sola transacción. Si algo falla, gold queda como estaba.
"""

import os
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import create_engine, text

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
DB_URL = os.environ.get("DB_URL", "postgresql+psycopg2://admin:admin123@db:5432/economia_digital_dw")
SCHEMA = "gold"

ALFA = 0.10
NACIONAL, TABASCO, YUCATAN = "00", "27", "31"
PARES = [(YUCATAN, TABASCO), (YUCATAN, NACIONAL), (TABASCO, NACIONAL)]
FOCO = [NACIONAL, TABASCO, YUCATAN]

# Medida OECD -> (indicador ENDUTIH, grupo de edad)
VALIDACION_OECD = {
    "B1_HH": ("hog_internet", "total"),
    "A1_HH": ("hog_computadora", "total"),
    "B21A_HH": ("hog_internet_fija", "total"),
    "C5B_I": ("pob_internet", "16_74"),
    "C2B_I": ("pob_computadora", "16_74"),
    "G1_I": ("pob_compra", "16_74"),
    "D1T_I": ("pob_banca", "16_74"),
    "D1B_I": ("pob_redes_sociales", "16_74"),
}

TABLAS = [
    "resultado_brecha",
    "resultado_tendencia",
    "resultado_ranking",
    "resultado_validacion_oecd",
]


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise ValueError(mensaje)


def prueba_z(diferencia: float, error: float) -> tuple:
    if error <= 0:
        return None, None
    z = diferencia / error
    return z, float(2 * stats.norm.sf(abs(z)))


# --------------------------------------------------------------------------
# Análisis
# --------------------------------------------------------------------------
def brechas(enc: pd.DataFrame) -> pd.DataFrame:
    e = enc.set_index(["anio", "id_indicador", "cve_ent"])
    filas = []
    for (anio, ind), _ in enc.groupby(["anio", "id_indicador"]):
        for a, b in PARES:
            ra, rb = e.loc[(anio, ind, a)], e.loc[(anio, ind, b)]
            var = ra["error_estandar"] ** 2 + rb["error_estandar"] ** 2
            if b == NACIONAL:
                s = ra["universo_expandido"] / rb["universo_expandido"]
                var -= 2 * s * ra["error_estandar"] ** 2
            dif, ee = ra["estimacion"] - rb["estimacion"], float(np.sqrt(max(var, 0)))
            z, p = prueba_z(dif, ee)
            filas.append((anio, ind, a, b, dif, ee, z, p, p is not None and p < ALFA))
    return pd.DataFrame(filas, columns=["anio", "id_indicador", "entidad_a", "entidad_b", "diferencia_pp",
                                        "error_estandar", "z", "p_value", "significativa"])


def tendencias(enc: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for (cve, ind), g in enc[enc["cve_ent"].isin(FOCO)].groupby(["cve_ent", "id_indicador"]):
        g = g.sort_values("anio")
        ini, fin = g.iloc[0], g.iloc[-1]
        cambio = fin["estimacion"] - ini["estimacion"]
        ee = float(np.sqrt(fin["error_estandar"] ** 2 + ini["error_estandar"] ** 2))
        z, p = prueba_z(cambio, ee)
        pendiente = stats.linregress(g["anio"], g["estimacion"]).slope
        filas.append((cve, ind, int(ini["anio"]), int(fin["anio"]), ini["estimacion"], fin["estimacion"],
                      cambio, ee, p, p is not None and p < ALFA, pendiente))
    return pd.DataFrame(filas, columns=["cve_ent", "id_indicador", "anio_inicial", "anio_final", "valor_inicial",
                                        "valor_final", "cambio_pp", "error_estandar", "p_value", "significativo",
                                        "pendiente_pp_anual"])


def rankings(enc: pd.DataFrame, valor: pd.DataFrame) -> pd.DataFrame:
    estados = enc[enc["cve_ent"] != NACIONAL][["anio", "id_indicador", "cve_ent", "estimacion"]]
    v = valor[valor["cve_ent"] != NACIONAL].melt(
        id_vars=["anio", "cve_ent"], value_vars=["participacion_51", "participacion_51_no_minero"],
        var_name="id_indicador", value_name="estimacion").dropna()
    v["id_indicador"] = v["id_indicador"].map({"participacion_51": "vab51_participacion",
                                               "participacion_51_no_minero": "vab51_participacion_no_minero"})
    r = pd.concat([estados, v], ignore_index=True)
    r["rango"] = r.groupby(["anio", "id_indicador"])["estimacion"].rank(ascending=False, method="min").astype(int)
    r["n_entidades"] = r.groupby(["anio", "id_indicador"])["cve_ent"].transform("count")
    exigir((r["n_entidades"] == 32).all(), "ranking: algún año × indicador no tiene las 32 entidades")
    return r


def validacion_oecd(enc_todo: pd.DataFrame, oecd: pd.DataFrame) -> pd.DataFrame:
    nac = enc_todo[enc_todo["cve_ent"] == NACIONAL].set_index(["anio", "id_indicador", "grupo_edad"])
    filas = []
    for r in oecd[oecd["cod_pais"] == "MEX"].itertuples():
        if r.medida not in VALIDACION_OECD:
            continue
        ind, grupo = VALIDACION_OECD[r.medida]
        if (r.anio, ind, grupo) not in nac.index:
            continue
        e = nac.loc[(r.anio, ind, grupo)]
        filas.append((r.anio, r.medida, ind, r.valor, e["estimacion"], e["li_90"], e["ls_90"],
                      e["estimacion"] - r.valor, e["li_90"] <= r.valor <= e["ls_90"]))
    df = pd.DataFrame(filas, columns=["anio", "medida_oecd", "id_indicador", "valor_oecd", "valor_endutih",
                                      "li_90", "ls_90", "diferencia_pp", "dentro_ic"])
    exigir(not df.empty, "validación OECD: no hay años en común")
    return df


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------
def cargar_resultados(engine, resultados: dict, run_id: str, fecha_carga: datetime) -> None:
    # DECISIÓN HUMANA (temporal): TRUNCATE + INSERT en cada ejecución, en una transacción.
    log = []
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(f'{SCHEMA}.{t}' for t in TABLAS)}"))
        for nombre in TABLAS:
            df = resultados[nombre]
            df.to_sql(nombre, conn, schema=SCHEMA, if_exists="append", index=False)
            log.append((nombre, "filas_cargadas", len(df)))
            print(f"OK   {SCHEMA}.{nombre}: {len(df):,} registros")

        pd.DataFrame(log, columns=["tabla", "metrica", "valor"]).assign(
            run_id=run_id, fecha_carga=fecha_carga,
        ).to_sql("etl_log", conn, schema=SCHEMA, if_exists="append", index=False)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    engine = create_engine(DB_URL)
    run_id = str(uuid.uuid4())
    fecha_carga = datetime.now(timezone.utc)
    print(f"run_id: {run_id}")

    enc_todo = pd.read_sql("SELECT * FROM gold.fact_encuesta_tic", engine)
    enc_todo["cve_ent"] = enc_todo["cve_ent"].str.strip()
    enc = enc_todo[enc_todo["grupo_edad"] == "total"]
    valor = pd.read_sql("SELECT anio, cve_ent, participacion_51, participacion_51_no_minero "
                        "FROM gold.valor_entidad_anio", engine)
    valor["cve_ent"] = valor["cve_ent"].str.strip()
    oecd = pd.read_sql("SELECT anio, cod_pais, medida, valor FROM gold.fact_oecd_tic", engine)

    # Fail-fast: cualquier excepción detiene el script (no se atrapa a propósito).
    resultados = {
        "resultado_brecha": brechas(enc),
        "resultado_tendencia": tendencias(enc),
        "resultado_ranking": rankings(enc, valor),
        "resultado_validacion_oecd": validacion_oecd(enc_todo, oecd),
    }
    cargar_resultados(engine, resultados, run_id, fecha_carga)

    print("Análisis de gold completado.")


if __name__ == "__main__":
    main()
