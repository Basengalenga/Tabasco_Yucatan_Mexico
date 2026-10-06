"""
Transformación silver -> gold de economia_digital_dw.

Dos partes, en una sola transacción:

1. SQL (sql/gold/gold.sql): dimensiones de entidad, tiempo y país; hechos de valor
   económico (PIB estatal), comercio electrónico (VABCOEL) y OECD; vistas.
2. Python (este archivo): gold.dim_indicador y gold.fact_encuesta_tic, las estimaciones de
   la ENDUTIH por año × entidad × indicador.

Estimaciones de encuesta
    La ENDUTIH es una muestra probabilística: cada registro representa a fac_hog hogares o
    fac_per personas. Una proporción se estima como cociente de totales expandidos:
        p = Σ w·d·y / Σ w·d       (d = 1 si el registro está en el denominador del indicador)
    y su error estándar por linealización de Taylor con el diseño muestral de INEGI
    (estratos est_dis, unidades primarias upm_dis, con reemplazo):
        z_i  = w_i·d_i·(y_i - p) / Σ w·d
        V(p) = Σ_h n_h/(n_h - 1) · Σ_c (z_hc - z̄_h)²      (z_hc = suma de z en la UPM c del estrato h)
    Los estratos están anidados en las entidades (se valida), así que la estimación de una
    entidad usa solo sus registros. Se reporta además el intervalo al 90% (el nivel que usa
    INEGI) y la calidad según el coeficiente de variación: alta (CV < 15), moderada (15-30),
    baja (> 30).

Grupos de edad: 'total' (6 años y más, o todos los hogares) para las 33 entidades, y
'16_74' solo nacional, para comparar con OECD (que usa personas de 16 a 74 años).

Manejo de errores (fail-fast):
    TRUNCATE, carga y validaciones corren en una sola transacción. Si algo falla, gold
    queda como estaba. El DDL vive en sql/init.sql y se aplica al inicio (es idempotente).
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
DB_URL = os.environ.get("DB_URL", "postgresql+psycopg2://admin:admin123@db:5432/economia_digital_dw")
SCHEMA = "gold"
INIT_SQL = Path(__file__).resolve().parent.parent / "sql" / "init.sql"
GOLD_SQL = Path(__file__).resolve().parent.parent / "sql" / "gold" / "gold.sql"

CVE_NACIONAL = "00"
N_ENTIDADES = 32
Z_90 = 1.6448536269514722

# id -> (nombre, dimensión, unidad, universo, tabla, columna, denominador, descripción)
#   denominador: None = todo el universo; columna booleana = solo donde es TRUE;
#                'sin_internet' = hogares sin internet. 'razon=k' = razon_sin_internet == k.
INDICADORES = {
    "hog_internet": ("Hogares con internet", "acceso", "% de hogares", "Hogares", "hogar", "tiene_internet", None,
                     "Hogares que disponen de conexión a internet (fija o móvil). ENDUTIH P4_4."),
    "hog_computadora": ("Hogares con computadora", "acceso", "% de hogares", "Hogares", "hogar", "tiene_computadora",
                        None, "Hogares con computadora de escritorio, laptop o tablet. ENDUTIH P4_2."),
    "hog_internet_fija": ("Hogares con internet fijo", "acceso", "% de hogares", "Hogares", "hogar", "internet_fija",
                          None, "Hogares con conexión fija (sola o junto con móvil). Excluye 'no sabe'. ENDUTIH P4_5."),
    "hog_celular": ("Hogares con celular", "acceso", "% de hogares", "Hogares", "hogar", "tiene_celular", None,
                    "Hogares donde algún integrante dispone de teléfono celular. ENDUTIH P4_1_6."),
    "pob_smartphone": ("Usuarios de smartphone", "acceso", "% de la población de 6+", "Personas de 6 años y más",
                       "persona", "usa_smartphone", None,
                       "Personas que usaron un celular inteligente en los últimos 3 meses. ENDUTIH P8_3 y P8_4_2."),
    "pob_internet": ("Usuarios de internet", "uso", "% de la población de 6+", "Personas de 6 años y más",
                     "persona", "usa_internet", None,
                     "Personas que usaron internet en los últimos 3 meses. ENDUTIH P7_1."),
    "pob_computadora": ("Usuarios de computadora", "uso", "% de la población de 6+", "Personas de 6 años y más",
                        "persona", "usa_computadora", None,
                        "Personas que usaron computadora, laptop o tablet en los últimos 3 meses. ENDUTIH P6_1."),
    "pob_celular": ("Usuarios de celular", "uso", "% de la población de 6+", "Personas de 6 años y más",
                    "persona", "usa_celular", None, "Personas que usaron celular en los últimos 3 meses. ENDUTIH P8_3."),
    "pob_redes_sociales": ("Usuarios de redes sociales", "uso", "% de la población de 6+", "Personas de 6 años y más",
                           "persona", "usa_redes_sociales", None,
                           "Personas que usaron redes sociales en los últimos 3 meses."),
    "pob_compra": ("Compran por internet (población)", "uso", "% de la población de 6+", "Personas de 6 años y más",
                   "persona", "compra_internet", None,
                   "Personas que compraron por internet en los últimos 12 meses, sobre toda la población."),
    "pob_banca": ("Banca electrónica (población)", "uso", "% de la población de 6+", "Personas de 6 años y más",
                  "persona", "banca_electronica", None,
                  "Personas que usaron banca electrónica en los últimos 3 meses, sobre toda la población."),
    "usu_compra": ("Compran por internet", "uso", "% de los usuarios de internet", "Usuarios de internet de 6+",
                   "persona", "compra_internet", "usa_internet",
                   "Usuarios de internet que compraron en línea en los últimos 12 meses."),
    "usu_vende": ("Venden por internet", "uso", "% de los usuarios de internet", "Usuarios de internet de 6+",
                  "persona", "vende_internet", "usa_internet",
                  "Usuarios de internet que vendieron en línea en los últimos 12 meses."),
    "usu_paga": ("Pagan por internet", "uso", "% de los usuarios de internet", "Usuarios de internet de 6+",
                 "persona", "paga_internet", "usa_internet",
                 "Usuarios de internet que pagaron compras o servicios en línea en los últimos 12 meses."),
    "usu_banca": ("Usan banca electrónica", "uso", "% de los usuarios de internet", "Usuarios de internet de 6+",
                  "persona", "banca_electronica", "usa_internet",
                  "Usuarios de internet que usaron banca electrónica en los últimos 3 meses."),
    "sin_internet_recursos": ("Sin internet por falta de recursos", "brecha", "% de hogares sin internet",
                              "Hogares sin internet", "hogar", "razon=1", "sin_internet",
                              "Hogares sin internet cuya razón principal es la falta de recursos económicos."),
    "sin_internet_no_interesa": ("Sin internet porque no lo necesitan", "brecha", "% de hogares sin internet",
                                 "Hogares sin internet", "hogar", "razon=2", "sin_internet",
                                 "Hogares sin internet cuya razón principal es que no les interesa o no lo necesitan."),
    "sin_internet_no_sabe": ("Sin internet porque no saben usarlo", "brecha", "% de hogares sin internet",
                             "Hogares sin internet", "hogar", "razon=3", "sin_internet",
                             "Hogares sin internet cuya razón principal es que no saben usarlo."),
    "sin_internet_sin_proveedor": ("Sin internet por falta de proveedor", "brecha", "% de hogares sin internet",
                                   "Hogares sin internet", "hogar", "razon=6", "sin_internet",
                                   "Hogares sin internet porque no hay proveedor o infraestructura en su localidad."),
}
# Indicadores de valor: se calculan en las vistas de gold.sql; aquí solo se documentan en dim_indicador
INDICADORES_VALOR = {
    "vab51_participacion": ("Peso del sector de información (51) en la economía", "valor", "% del VAB",
                            "Economía de la entidad", "INEGI PIBE",
                            "VAB del sector 51 (información en medios masivos: telecomunicaciones, internet, "
                            "edición de software, radio y TV) / VAB total, precios corrientes."),
    "vab51_participacion_no_minero": ("Peso del sector 51 en la economía no minera", "valor", "% del VAB no minero",
                                      "Economía de la entidad sin minería", "INEGI PIBE",
                                      "VAB del sector 51 / (VAB total - VAB del sector 21 minería)."),
    "vab51_crecimiento_real": ("Crecimiento real del sector 51", "valor", "% anual", "Economía de la entidad",
                               "INEGI PIBE", "Variación anual del VAB del sector 51 a precios de 2018."),
    "vabcoel_pct_pib": ("Comercio electrónico en el PIB", "valor", "% del PIB", "Economía nacional",
                        "INEGI VABCOEL", "Valor agregado bruto del comercio electrónico / PIB nacional."),
}
# Indicadores que también se estiman para 16-74 años a nivel nacional (comparables con OECD)
INDICADORES_16_74 = ["pob_internet", "pob_computadora", "pob_compra", "pob_banca", "pob_redes_sociales"]

TABLAS = [
    "dim_entidad",
    "dim_tiempo",
    "dim_indicador",
    "dim_pais",
    "fact_encuesta_tic",
    "fact_valor_entidad",
    "fact_comercio_electronico",
    "fact_oecd_tic",
]


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise ValueError(mensaje)


def escalar(conn, sql: str):
    return conn.execute(text(sql)).scalar()


def ejecutar_script(conn, ruta: Path) -> None:
    """Ejecuta un archivo SQL con el cursor de psycopg2 sin parámetros (así '%' no se interpreta)."""
    with conn.connection.cursor() as cur:
        cur.execute(ruta.read_text())


def calidad(cv: float) -> str:
    if cv is None or np.isnan(cv) or cv < 15:
        return "alta"
    return "moderada" if cv <= 30 else "baja"


# --------------------------------------------------------------------------
# Estimación por diseño muestral
# --------------------------------------------------------------------------
def estimar_proporcion(w: np.ndarray, y: np.ndarray, d: np.ndarray, estrato: np.ndarray, upm: np.ndarray) -> dict:
    """Proporción ponderada y su error estándar (linealización de Taylor, UPM con reemplazo)."""
    wd = w * d
    total_d = wd.sum()
    exigir(total_d > 0, "estimación con denominador vacío")
    p = (wd * y).sum() / total_d
    z = wd * (y - p) / total_d

    por_upm = pd.DataFrame({"h": estrato, "c": upm, "z": z}).groupby(["h", "c"], sort=False)["z"].sum()
    por_estrato = por_upm.groupby(level="h")
    n_h = por_estrato.size()
    exigir((n_h >= 2).all(), f"estratos con una sola UPM: {n_h[n_h < 2].index.tolist()[:5]}")
    desv = por_upm - por_estrato.transform("mean")
    var = ((n_h / (n_h - 1)) * (desv ** 2).groupby(level="h").sum()).sum()
    return {"p": p, "se": float(np.sqrt(var)), "n": int(d.sum()), "num": (wd * y).sum(), "den": total_d}


def preparar(df: pd.DataFrame, columna: str, denominador: str | None):
    """Devuelve (y, d) como arreglos float para un indicador."""
    if columna.startswith("razon="):
        y = (df["razon_sin_internet"] == int(columna.split("=")[1])).to_numpy(float)
    else:
        y = df[columna].astype("float").to_numpy()  # NULL (p. ej. 'no sabe') -> NaN
    if denominador is None:
        d = np.ones(len(df))
    elif denominador == "sin_internet":
        d = (~df["tiene_internet"].astype(bool)).to_numpy(float)
    else:
        d = df[denominador].astype(bool).to_numpy(float)
    # Los NULL de la variable de interés salen del denominador
    d = np.where(np.isnan(y), 0.0, d)
    return np.nan_to_num(y), d


def estimaciones(engine, cves: list) -> pd.DataFrame:
    tablas = {
        "hogar": pd.read_sql("SELECT anio, cve_ent, est_dis, upm_dis, fac_hog AS w, tiene_computadora, "
                             "tiene_internet, internet_fija, tiene_celular, razon_sin_internet "
                             "FROM silver.endutih_hogar", engine),
        "persona": pd.read_sql("SELECT anio, cve_ent, est_dis, upm_dis, fac_per AS w, edad, usa_internet, "
                               "usa_computadora, usa_celular, usa_smartphone, usa_redes_sociales, compra_internet, "
                               "vende_internet, paga_internet, banca_electronica FROM silver.endutih_persona", engine),
    }
    for nombre, t in tablas.items():
        # Los estratos deben estar anidados en las entidades para estimar cada entidad por separado
        exigir(t.groupby(["anio", "est_dis"])["cve_ent"].nunique().max() == 1,
               f"{nombre}: hay estratos que cruzan entidades")
        t["estrato"] = t["anio"].astype(str) + "-" + t["est_dis"]
        t["upm"] = t["estrato"] + "-" + t["upm_dis"]

    filas = []
    for id_ind, (_, _, _, _, tabla, columna, denominador, _) in INDICADORES.items():
        t = tablas[tabla]
        grupos = [("total", t)]
        if id_ind in INDICADORES_16_74:
            grupos.append(("16_74", t[t["edad"].between(16, 74)]))
        for grupo, base in grupos:
            for anio, del_anio in base.groupby("anio"):
                por_entidad = [(CVE_NACIONAL, del_anio)]
                if grupo == "total":
                    por_entidad += [(c, g) for c, g in del_anio.groupby("cve_ent")]
                for cve, g in por_entidad:
                    y, d = preparar(g, columna, denominador)
                    r = estimar_proporcion(g["w"].to_numpy(float), y, d, g["estrato"].to_numpy(), g["upm"].to_numpy())
                    filas.append((int(anio), cve, id_ind, grupo, r))
        print(f"     {id_ind}: estimado")

    salida = pd.DataFrame([{
        "anio": a, "cve_ent": c, "id_indicador": i, "grupo_edad": g,
        "estimacion": 100 * r["p"], "error_estandar": 100 * r["se"],
        "n_muestra": r["n"], "numerador_expandido": round(r["num"]), "universo_expandido": round(r["den"]),
    } for a, c, i, g, r in filas])
    salida["cv"] = np.where(salida["estimacion"] > 0, 100 * salida["error_estandar"] / salida["estimacion"], np.nan)
    salida["li_90"] = (salida["estimacion"] - Z_90 * salida["error_estandar"]).clip(lower=0)
    salida["ls_90"] = (salida["estimacion"] + Z_90 * salida["error_estandar"]).clip(upper=100)
    salida["calidad"] = salida["cv"].map(calidad)
    exigir(set(salida["cve_ent"]) <= set(cves), "estimaciones: entidad fuera de dim_entidad")
    exigir(salida["estimacion"].between(0, 100).all(), "estimaciones: proporción fuera de [0, 100]")
    return salida


# --------------------------------------------------------------------------
# Validaciones
# --------------------------------------------------------------------------
def validar(conn) -> None:
    n = escalar(conn, "SELECT count(*) FROM gold.dim_entidad")
    exigir(n == N_ENTIDADES + 1, f"dim_entidad: se esperaban {N_ENTIDADES + 1} filas, hay {n}")

    for tabla_s, tabla_g in [("pib_entidad", "fact_valor_entidad"), ("vabcoel", "fact_comercio_electronico"),
                             ("oecd_ict", "fact_oecd_tic")]:
        s, g = escalar(conn, f"SELECT count(*) FROM silver.{tabla_s}"), escalar(conn, f"SELECT count(*) FROM gold.{tabla_g}")
        exigir(s == g, f"{tabla_g}: {g} filas, silver tiene {s}")

    # Cada año × indicador debe tener nacional + 32 entidades (grupo total)
    incompletos = conn.execute(text("""
        SELECT anio, id_indicador, count(*) FROM gold.fact_encuesta_tic WHERE grupo_edad = 'total'
        GROUP BY 1, 2 HAVING count(*) <> 33
    """)).fetchall()
    exigir(not incompletos, f"fact_encuesta_tic: año × indicador incompletos {incompletos[:5]}")

    # Los expandidos nacionales de hogares y personas coinciden con la suma de factores de silver
    diferencias = conn.execute(text("""
        SELECT f.anio, f.id_indicador, f.universo_expandido, s.total
        FROM gold.fact_encuesta_tic f
        JOIN (SELECT anio, sum(fac_hog) AS total FROM silver.endutih_hogar GROUP BY anio) s USING (anio)
        WHERE f.cve_ent = '00' AND f.grupo_edad = 'total' AND f.id_indicador = 'hog_internet'
          AND f.universo_expandido <> s.total
        UNION ALL
        SELECT f.anio, f.id_indicador, f.universo_expandido, s.total
        FROM gold.fact_encuesta_tic f
        JOIN (SELECT anio, sum(fac_per) AS total FROM silver.endutih_persona GROUP BY anio) s USING (anio)
        WHERE f.cve_ent = '00' AND f.grupo_edad = 'total' AND f.id_indicador = 'pob_internet'
          AND f.universo_expandido <> s.total
    """)).fetchall()
    exigir(not diferencias, f"fact_encuesta_tic: universos expandidos distintos a silver {diferencias}")


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------
def aplicar_ddl(engine) -> None:
    with engine.begin() as conn:
        ejecutar_script(conn, INIT_SQL)


def dim_indicador() -> pd.DataFrame:
    filas = [(i, n, dim, u, univ, "INEGI ENDUTIH", desc) for i, (n, dim, u, univ, _, _, _, desc) in INDICADORES.items()]
    filas += [(i, n, dim, u, univ, f, desc) for i, (n, dim, u, univ, f, desc) in INDICADORES_VALOR.items()]
    df = pd.DataFrame(filas, columns=["id_indicador", "nombre", "dimension", "unidad", "universo", "fuente", "descripcion"])
    df["orden"] = range(1, len(df) + 1)
    return df


def cargar_gold(engine, run_id: str, fecha_carga: datetime) -> None:
    cves = pd.read_sql("SELECT cve_ent FROM silver.cat_entidad", engine)["cve_ent"].tolist()
    encuesta = estimaciones(engine, cves)  # se calcula antes de abrir la transacción

    # DECISIÓN HUMANA (temporal): TRUNCATE + INSERT en cada ejecución, en una transacción.
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(f'{SCHEMA}.{t}' for t in TABLAS)}"))
        conn.execute(
            text("SELECT set_config('gold.run_id', :run_id, true), set_config('gold.fecha_carga', :fecha_carga, true)"),
            {"run_id": run_id, "fecha_carga": fecha_carga.isoformat()},
        )
        ejecutar_script(conn, GOLD_SQL)
        dim_indicador().to_sql("dim_indicador", conn, schema=SCHEMA, if_exists="append", index=False)
        encuesta.assign(
            fuente="INEGI ENDUTIH", version_fuente="ENDUTIH " + encuesta["anio"].astype(str),
            fecha_carga=fecha_carga, run_id=run_id,
        ).to_sql("fact_encuesta_tic", conn, schema=SCHEMA, if_exists="append", index=False, chunksize=5_000)

        validar(conn)

        log = []
        for nombre in [*TABLAS, "kpi_entidad_anio", "valor_entidad_anio", "comercio_electronico_anio"]:
            n = escalar(conn, f"SELECT count(*) FROM {SCHEMA}.{nombre}")
            log.append((nombre, "filas_cargadas", n))
            print(f"OK   {SCHEMA}.{nombre}: {n:,} registros")
        log.append(("fact_encuesta_tic", "estimaciones_calidad_baja", int((encuesta["calidad"] == "baja").sum())))
        log.append(("fact_encuesta_tic", "estimaciones_calidad_moderada", int((encuesta["calidad"] == "moderada").sum())))

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

    aplicar_ddl(engine)

    # Fail-fast: cualquier excepción detiene el script (no se atrapa a propósito).
    cargar_gold(engine, run_id, fecha_carga)

    print("Carga a gold completada.")


if __name__ == "__main__":
    main()
