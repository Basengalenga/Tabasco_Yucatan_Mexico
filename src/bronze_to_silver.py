"""
Transformación bronze -> silver de economia_digital_dw.

Cada tabla silver se construye con una función independiente que lee su fuente en
bronze, la limpia y devuelve un DataFrame listo para cargar:

    silver.cat_entidad              <- bronze.endutih_cat_entidad (+ fila nacional '00')
    silver.endutih_mapeo_variables  <- MAPEO_* de este archivo, validado con bronze.endutih_diccionario
    silver.endutih_hogar            <- bronze.endutih_hogares_<anio>
    silver.endutih_persona          <- bronze.endutih_usuarios_<anio> + bronze.endutih_usuarios2_<anio>
    silver.vabcoel                  <- bronze.vabcoel
    silver.pib_entidad              <- bronze.pibe
    silver.oecd_ict                 <- bronze.oecd_ict_hogares + bronze.oecd_ict_individuos

Reglas de silver:
    - Llave geográfica: cve_ent CHAR(2); '00' = nacional.
    - Respuestas 1 = Sí / 2 = No de la ENDUTIH -> BOOLEAN.
    - Columnas de trazabilidad: fuente, version_fuente, fecha_carga.
    - Cada descarte, recodificación y decisión de limpieza se registra en silver.etl_log
      (métrica + conteo + detalle). El catálogo completo de decisiones, con su justificación,
      está en docs/decisiones_limpieza.md; los identificadores Dxx de los comentarios
      apuntan a ese documento.

Manejo de errores (fail-fast):
    Primero se transforman y validan todas las tablas en memoria; solo después se toca la
    base, en una sola transacción. Si algo falla, silver queda como estaba.

El DDL vive en sql/init.sql. Este script lo ejecuta al inicio (es idempotente).
"""

import csv
import io
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
DB_URL = os.environ.get("DB_URL", "postgresql+psycopg2://admin:admin123@db:5432/economia_digital_dw")
SCHEMA = "silver"
INIT_SQL = Path(__file__).resolve().parent.parent / "sql" / "init.sql"

ANIOS_ENDUTIH = range(2020, 2025)
N_ENTIDADES = 32
CVE_NACIONAL = "00"
ENTIDADES_FOCO = {"00", "27", "31"}  # nacional, Tabasco, Yucatán

# DECISIÓN D06: la numeración de las preguntas cambia entre levantamientos (p. ej. 'compras
# por internet' es P7_19 en 2020-2022 y P7_21 en 2023-2024, y en 2020-2022 P7_21 pregunta
# otra cosa: la frecuencia de compra). Cada concepto se mapea por año a su columna, y el
# mapeo se valida contra el texto del diccionario de INEGI: la descripción de la columna
# debe contener la palabra clave. Si INEGI renumera, el pipeline falla en vez de mezclar
# preguntas distintas.
#   concepto -> (tabla, palabra clave, {años: [columnas]})
MAPEO_HOGAR = {
    "computadora": ("hogares", "dispon", {
        (2020, 2021): ["p4_2_1", "p4_2_2", "p4_2_3"],
        (2022, 2023, 2024): ["p4_2_1_1", "p4_2_2_1", "p4_2_3_1"],
    }),
    "internet": ("hogares", "conexion a internet en el hogar", {ANIOS_ENDUTIH: ["p4_4"]}),
    "tipo_conexion": ("hogares", "fija, movil o de ambas", {ANIOS_ENDUTIH: ["p4_5"]}),
    "celular": ("hogares", "celular", {ANIOS_ENDUTIH: ["p4_1_6"]}),
    "razon_sin_internet": ("hogares", "por que no disponen de internet", {ANIOS_ENDUTIH: ["p4_8"]}),
}
MAPEO_PERSONA = {
    "usa_internet": ("usuarios", "ha utilizado internet", {ANIOS_ENDUTIH: ["p7_1"]}),
    "usa_computadora": ("usuarios", "utilizo computadora", {ANIOS_ENDUTIH: ["p6_1"]}),
    "usa_redes_sociales": ("usuarios", "redes sociales", {(2020, 2021, 2022): ["p7_13"], (2023, 2024): ["p7_15"]}),
    "vende_internet": ("usuarios", "ventas por internet", {(2020, 2021, 2022): ["p7_17"], (2023, 2024): ["p7_19"]}),
    "compra_internet": ("usuarios", "compras por internet", {(2020, 2021, 2022): ["p7_19"], (2023, 2024): ["p7_21"]}),
    "paga_internet": ("usuarios", "pagos por internet", {(2020, 2021, 2022): ["p7_27"], (2023, 2024): ["p7_28"]}),
    "banca_electronica": ("usuarios", "banca electronica", {(2020, 2021, 2022): ["p7_32"], (2023, 2024): ["p7_33"]}),
    "usa_celular": ("usuarios2", "telefono celular", {ANIOS_ENDUTIH: ["p8_3"]}),
    "usa_smartphone": ("usuarios2", "inteligente", {ANIOS_ENDUTIH: ["p8_4_2"]}),
}
# Actividades que la ENDUTIH solo pregunta a usuarios de internet (salto: vacío para no usuarios)
SOLO_USUARIOS_INTERNET = ["usa_redes_sociales", "vende_internet", "compra_internet", "paga_internet",
                          "banca_electronica"]

# Llaves de la ENDUTIH y su ancho (DECISIÓN D07: 2022 y otros años las traen sin ceros a la izquierda)
ANCHO_LLAVES = {"upm": 7, "viv_sel": 2, "hogar": 2, "num_ren": 2, "est_dis": 3, "upm_dis": 5}

ESTATUS_CIFRA = {"r": "revisada", "p": "preliminar"}

# VABCOEL: unidad del renglón -> medida. Se quedan solo niveles y participaciones (DECISIÓN D10).
MEDIDAS_VABCOEL = {
    ("coel_corr", "millones de pesos a precios corrientes"): "mdp_corrientes",
    ("coel_cte", "millones de pesos a precios de 2018"): "mdp_constantes_2018",
    ("pcoel_pibt", "participacion porcentual"): "pct_pib",
    ("pcoel_vabt", "participacion porcentual"): "pct_vab",
    ("pcoel_aeta", "participacion porcentual"): "pct_vab_actividad",
}
COMPONENTES_VABCOEL = {
    "total": "total",
    "comercio al por mayor": "comercio_al_por_mayor",
    "comercio al por menor": "comercio_al_por_menor",
    "otros servicios": "otros_servicios",
}
PRECIOS_PIBE = {"millones de pesos": "corrientes", "millones de pesos a precios de 2018": "constantes_2018"}
CONCEPTOS_PIBE = {
    "conjunto_de_datos_pibe_actividad_b.1bv2023_p.csv": "vab_total",
    "conjunto_de_datos_pibe_actividad_512023_p.csv": "vab_51",
    "conjunto_de_datos_pibe_actividad_212023_p.csv": "vab_21",
}
UNIDADES_OECD = {"PT_HH": "pct_hogares", "PT_POP": "pct_personas_16_74"}

# Orden de carga (respeta las FKs). etl_log no se trunca.
TABLAS = [
    "cat_entidad",
    "endutih_mapeo_variables",
    "endutih_hogar",
    "endutih_persona",
    "vabcoel",
    "pib_entidad",
    "oecd_ict",
]


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def normalizar_texto(valor: str) -> str:
    """'  ¿Disponen de conexión a Internet?  ' -> '¿disponen de conexion a internet?' (sin acentos)."""
    sin_acentos = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


def exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise ValueError(mensaje)


def registrar(log: list, tabla: str, metrica: str, valor, detalle: str | None = None) -> None:
    log.append((tabla, metrica, int(valor), detalle))


def columnas_del_anio(mapeo: dict, anio: int) -> dict:
    """concepto -> (tabla, palabra clave, [columnas]) para un año."""
    salida = {}
    for concepto, (tabla, clave, por_anios) in mapeo.items():
        cols = [c for anios, cs in por_anios.items() if anio in anios for c in cs]
        exigir(bool(cols), f"mapeo: {concepto} no tiene columna para {anio}")
        salida[concepto] = (tabla, clave, cols)
    return salida


def si_no(serie: pd.Series, columna: str) -> pd.Series:
    """'1' -> True, '2' -> False, vacío -> NA. Cualquier otro código es error."""
    s = serie.str.strip()
    invalidos = s.notna() & ~s.isin(["1", "2"])
    exigir(not invalidos.any(), f"{columna}: códigos fuera de 1/2 {s[invalidos].unique()[:10].tolist()}")
    return s.map({"1": True, "2": False}).astype("boolean")


def a_entero(serie: pd.Series, columna: str) -> pd.Series:
    s = serie.str.strip()
    invalidos = s.notna() & ~s.str.fullmatch(r"[0-9]+", na=False)
    exigir(not invalidos.any(), f"{columna}: valores no numéricos {s[invalidos].unique()[:10].tolist()}")
    return s.astype("Int64")


def a_numero(serie: pd.Series) -> pd.Series:
    """Cifras de tabulados de INEGI: 'NA' (no aplica) -> NaN."""
    return pd.to_numeric(serie.replace({"NA": None}), errors="raise")


def copy_postgres(table, conn, keys, data_iter) -> None:
    """Método de inserción para pandas.to_sql usando COPY (mucho más rápido que INSERT)."""
    dbapi_conn = conn.connection
    with dbapi_conn.cursor() as cur:
        buf = io.StringIO()
        csv.writer(buf).writerows(data_iter)
        buf.seek(0)
        columnas = ", ".join(f'"{k}"' for k in keys)
        cur.copy_expert(f"COPY {table.schema}.{table.name} ({columnas}) FROM STDIN WITH CSV", buf)


def trazabilidad(df: pd.DataFrame, fuente: str, version, fecha_carga: datetime) -> pd.DataFrame:
    df["fuente"] = fuente
    df["version_fuente"] = version
    df["fecha_carga"] = fecha_carga
    return df


# --------------------------------------------------------------------------
# Transformaciones
# --------------------------------------------------------------------------
def transformar_cat_entidad(engine, fecha_carga: datetime, log: list) -> pd.DataFrame:
    df = pd.read_sql("SELECT cve_ent, nom_ent FROM bronze.endutih_cat_entidad", engine)
    df["cve_ent"] = df["cve_ent"].str.strip().str.zfill(2)
    df["nombre"] = df["nom_ent"].str.strip()
    exigir(len(df) == N_ENTIDADES and df["cve_ent"].is_unique, "cat_entidad: se esperaban 32 entidades únicas")

    # DECISIÓN D08: se agrega la fila '00' para el total nacional (las fuentes lo reportan
    # como 'Estados Unidos Mexicanos'); así todas las tablas comparten la misma llave.
    df = pd.concat([pd.DataFrame([{"cve_ent": CVE_NACIONAL, "nombre": "Estados Unidos Mexicanos"}]), df],
                   ignore_index=True)
    registrar(log, "cat_entidad", "fila_nacional_agregada", 1, "cve_ent '00' = Estados Unidos Mexicanos")
    df["nombre_normalizado"] = df["nombre"].map(normalizar_texto)
    df["es_foco"] = df["cve_ent"].isin(ENTIDADES_FOCO)
    df = trazabilidad(df, "INEGI ENDUTIH", "Catálogo de entidades ENDUTIH 2024", fecha_carga)
    return df[["cve_ent", "nombre", "nombre_normalizado", "es_foco", "fuente", "version_fuente", "fecha_carga"]]


def transformar_mapeo(engine, fecha_carga: datetime, log: list) -> pd.DataFrame:
    dic = pd.read_sql("SELECT * FROM bronze.endutih_diccionario", engine)
    # DECISIÓN D09: el diccionario 2020 llama 'campo' a lo que los demás años llaman 'columna'
    dic["col"] = dic["columna"].fillna(dic["campo"]).str.strip().str.lower()
    dic["desc_norm"] = dic["descripcion"].map(normalizar_texto)
    registrar(log, "endutih_mapeo_variables", "diccionarios_con_campo_en_vez_de_columna",
              dic["columna"].isna().sum(), "renglones de diccionario donde el nombre viene en 'campo' (2020)")

    filas = []
    for anio in ANIOS_ENDUTIH:
        for mapeo in (MAPEO_HOGAR, MAPEO_PERSONA):
            for concepto, (tabla, clave, cols) in columnas_del_anio(mapeo, anio).items():
                for col in cols:
                    d = dic[(dic["anio"] == str(anio)) & (dic["tabla"] == tabla) & (dic["col"] == col)]
                    exigir(len(d) == 1, f"mapeo {anio}: {tabla}.{col} no está en el diccionario")
                    desc = d["desc_norm"].iloc[0]
                    exigir(clave in desc, f"mapeo {anio}: {tabla}.{col} ({concepto}) no contiene '{clave}': {desc[:120]}")
                    filas.append((anio, concepto, f"endutih_{tabla}_{anio}", col,
                                  re.sub(r"\s+", " ", d["descripcion"].iloc[0]).strip()))
    df = pd.DataFrame(filas, columns=["anio", "concepto", "tabla_bronze", "columna", "descripcion_diccionario"])
    registrar(log, "endutih_mapeo_variables", "columnas_validadas_contra_diccionario", len(df))
    return trazabilidad(df, "INEGI ENDUTIH", df["anio"].map(lambda a: f"ENDUTIH {a}"), fecha_carga)


def leer_endutih(engine, tabla: str, anio: int, columnas: list, log: list) -> pd.DataFrame:
    disponibles = set(pd.read_sql(
        text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'bronze' AND table_name = :t"),
        engine, params={"t": f"endutih_{tabla}_{anio}"})["column_name"])
    # DECISIÓN D07: la clave de entidad se llama 'ent' hasta 2023 y 'cve_ent' en 2024
    ent = "cve_ent" if "cve_ent" in disponibles else "ent"
    faltan = [c for c in columnas if c not in disponibles]
    exigir(not faltan, f"endutih_{tabla}_{anio}: faltan columnas {faltan}")
    sql = f"SELECT {ent} AS cve_ent, {', '.join(columnas)} FROM bronze.endutih_{tabla}_{anio}"
    df = pd.read_sql(sql, engine)
    for c, ancho in {"cve_ent": 2, **ANCHO_LLAVES}.items():
        if c in df:
            cortas = df[c].str.strip().str.len() < ancho
            if cortas.any():
                registrar(log, f"endutih_{tabla}", f"llave_{c}_rellenada_con_ceros_{anio}", cortas.sum(),
                          f"'{c}' sin ceros a la izquierda en la fuente; se completa a {ancho} dígitos")
            antes = df[c].str.strip().nunique()
            df[c] = df[c].str.strip().str.zfill(ancho)
            # Rellenar nunca debe fusionar dos claves distintas (p. ej. '1' y '01' en el mismo archivo)
            exigir(df[c].nunique() == antes, f"endutih_{tabla}_{anio}: rellenar '{c}' con ceros fusiona claves")
    return df


def transformar_hogar(engine, cves: set, fecha_carga: datetime, log: list) -> pd.DataFrame:
    partes = []
    for anio in ANIOS_ENDUTIH:
        cols = columnas_del_anio(MAPEO_HOGAR, anio)
        fuente_cols = [c for _, _, cs in cols.values() for c in cs]
        df = leer_endutih(engine, "hogares", anio,
                          ["upm", "viv_sel", "hogar", "est_dis", "upm_dis", "tloc", "fac_hog", *fuente_cols], log)
        registrar(log, "endutih_hogar", f"registros_bronze_{anio}", len(df))

        sal = df[["upm", "viv_sel", "hogar", "cve_ent", "est_dis", "upm_dis"]].copy()
        sal["anio"] = anio
        sal["tloc"] = a_entero(df["tloc"], "tloc")
        sal["fac_hog"] = a_entero(df["fac_hog"], "fac_hog")

        compu = pd.concat([si_no(df[c], c) for c in cols["computadora"][2]], axis=1)
        exigir(compu.notna().all().all(), f"hogar {anio}: computadora con vacíos")
        # DECISIÓN D11: 'tiene computadora' = escritorio O laptop O tablet (definición de INEGI/OECD A1_HH)
        sal["tiene_computadora"] = compu.any(axis=1).astype(bool)

        for concepto, destino in [("internet", "tiene_internet"), ("celular", "tiene_celular")]:
            col = cols[concepto][2][0]
            v = si_no(df[col], col)
            exigir(v.notna().all(), f"hogar {anio}: {col} con vacíos")
            sal[destino] = v.astype(bool)

        # P4_5: 1 solo fija, 2 solo móvil, 3 ambas, 9 no sabe; vacío si el hogar no tiene internet
        tipo = df[cols["tipo_conexion"][2][0]].str.strip()
        exigir((tipo.isna() == ~sal["tiene_internet"]).all(), f"hogar {anio}: P4_5 no respeta el salto de P4_4")
        exigir(tipo.dropna().isin(["1", "2", "3", "9"]).all(), f"hogar {anio}: P4_5 con códigos desconocidos")
        # DECISIÓN D12: 'no sabe' (9) -> NULL; hogar sin internet -> FALSE (no tiene conexión fija)
        sal["internet_fija"] = tipo.map({"1": True, "3": True, "2": False, "9": pd.NA}).astype("boolean")
        sal.loc[~sal["tiene_internet"], "internet_fija"] = False
        registrar(log, "endutih_hogar", f"tipo_conexion_no_sabe_a_null_{anio}", (tipo == "9").sum(),
                  "P4_5 = 9 (no sabe si la conexión es fija o móvil)")

        razon = a_entero(df[cols["razon_sin_internet"][2][0]], "p4_8")
        exigir((razon.notna() == ~sal["tiene_internet"]).all(), f"hogar {anio}: P4_8 no respeta el salto de P4_4")
        sal["razon_sin_internet"] = razon
        partes.append(sal)

    df = pd.concat(partes, ignore_index=True)
    exigir(df["cve_ent"].isin(cves).all(), "hogar: cve_ent fuera del catálogo")
    exigir(not df.duplicated(["anio", "upm", "viv_sel", "hogar"]).any(), "hogar: llave duplicada")
    exigir((df["fac_hog"] > 0).all(), "hogar: factor de expansión no positivo")
    exigir(df.groupby("anio")["cve_ent"].nunique().eq(N_ENTIDADES).all(), "hogar: algún año no cubre las 32 entidades")
    df = trazabilidad(df, "INEGI ENDUTIH", df["anio"].map(lambda a: f"ENDUTIH {a}"), fecha_carga)
    return df[["anio", "upm", "viv_sel", "hogar", "cve_ent", "est_dis", "upm_dis", "tloc", "fac_hog",
               "tiene_computadora", "tiene_internet", "internet_fija", "tiene_celular", "razon_sin_internet",
               "fuente", "version_fuente", "fecha_carga"]]


def transformar_persona(engine, cves: set, fecha_carga: datetime, log: list) -> pd.DataFrame:
    llaves = ["upm", "viv_sel", "hogar", "num_ren"]
    partes = []
    for anio in ANIOS_ENDUTIH:
        cols = columnas_del_anio(MAPEO_PERSONA, anio)
        de = lambda t: [c for tb, _, cs in cols.values() if tb == t for c in cs]
        u = leer_endutih(engine, "usuarios", anio,
                         [*llaves, "est_dis", "upm_dis", "tloc", "fac_per", "edad", "sexo", *de("usuarios")], log)
        u2 = leer_endutih(engine, "usuarios2", anio, [*llaves, *de("usuarios2")], log).drop(columns="cve_ent")
        registrar(log, "endutih_persona", f"registros_bronze_{anio}", len(u))

        # usuarios y usuarios2 son el mismo informante elegido, partido en dos archivos
        df = u.merge(u2, on=llaves, how="outer", indicator=True, validate="one_to_one")
        exigir((df["_merge"] == "both").all(), f"persona {anio}: usuarios y usuarios2 no traen los mismos informantes")

        sal = df[[*llaves, "cve_ent", "est_dis", "upm_dis"]].copy()
        sal["anio"] = anio
        sal["tloc"] = a_entero(df["tloc"], "tloc")
        sal["fac_per"] = a_entero(df["fac_per"], "fac_per")
        sal["edad"] = a_entero(df["edad"], "edad")
        sal["sexo"] = a_entero(df["sexo"], "sexo")

        for concepto in ["usa_internet", "usa_computadora", "usa_celular"]:
            col = cols[concepto][2][0]
            v = si_no(df[col], col)
            exigir(v.notna().all(), f"persona {anio}: {col} ({concepto}) con vacíos")
            sal[concepto] = v.astype(bool)

        # DECISIÓN D13: las actividades en internet solo se preguntan a usuarios de internet.
        # El vacío de los no usuarios se lee como 'no realizó la actividad' (FALSE); un vacío
        # entre usuarios sería un dato faltante real y detiene el pipeline.
        for concepto in SOLO_USUARIOS_INTERNET:
            col = cols[concepto][2][0]
            v = si_no(df[col], col)
            exigir(v[sal["usa_internet"]].notna().all(), f"persona {anio}: {col} ({concepto}) vacío entre usuarios")
            exigir(v[~sal["usa_internet"]].isna().all(), f"persona {anio}: {col} ({concepto}) contestado por no usuarios")
            sal[concepto] = v.fillna(False).astype(bool)
        registrar(log, "endutih_persona", f"no_usuarios_internet_salto_a_false_{anio}", (~sal["usa_internet"]).sum(),
                  "actividades en internet vacías por salto -> FALSE")

        # Smartphone (P8_4_2) solo se pregunta a quien usó celular (P8_3 = 1)
        col = cols["usa_smartphone"][2][0]
        v = si_no(df[col], col)
        exigir(v[sal["usa_celular"]].notna().all(), f"persona {anio}: {col} vacío entre usuarios de celular")
        sal["usa_smartphone"] = v.fillna(False).astype(bool)
        partes.append(sal)

    df = pd.concat(partes, ignore_index=True)
    exigir(df["cve_ent"].isin(cves).all(), "persona: cve_ent fuera del catálogo")
    exigir(not df.duplicated(["anio", *llaves]).any(), "persona: llave duplicada")
    exigir((df["edad"] >= 6).all(), "persona: informantes menores de 6 años (fuera del universo)")
    exigir((df["fac_per"] > 0).all(), "persona: factor de expansión no positivo")
    df = trazabilidad(df, "INEGI ENDUTIH", df["anio"].map(lambda a: f"ENDUTIH {a}"), fecha_carga)
    return df[["anio", *llaves, "cve_ent", "est_dis", "upm_dis", "tloc", "fac_per", "edad", "sexo",
               "usa_internet", "usa_computadora", "usa_celular", "usa_smartphone", "usa_redes_sociales",
               "compra_internet", "vende_internet", "paga_internet", "banca_electronica",
               "fuente", "version_fuente", "fecha_carga"]]


def columnas_anio(df: pd.DataFrame) -> dict:
    """'2023_r' -> (2023, 'revisada'); '2013' -> (2013, 'definitiva')."""
    salida = {}
    for c in df.columns:
        m = re.fullmatch(r"(\d{4})(?:_([rp]))?", c)
        if m:
            salida[c] = (int(m.group(1)), ESTATUS_CIFRA.get(m.group(2), "definitiva"))
    return salida


def a_largo(df: pd.DataFrame, id_vars: list) -> pd.DataFrame:
    anios = columnas_anio(df)
    largo = df.melt(id_vars=id_vars, value_vars=list(anios), var_name="col_anio", value_name="valor_txt")
    largo["anio"] = largo["col_anio"].map(lambda c: anios[c][0])
    largo["estatus_cifra"] = largo["col_anio"].map(lambda c: anios[c][1])
    largo["valor"] = a_numero(largo["valor_txt"])
    return largo


def transformar_vabcoel(engine, fecha_carga: datetime, log: list) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM bronze.vabcoel", engine)
    registrar(log, "vabcoel", "renglones_bronze", len(df))
    partes = df["descriptores"].str.replace(r"<[^>]+>", "", regex=True).str.split("|")
    df["unidad"] = partes.str[0].map(normalizar_texto)
    df["clave_archivo"] = df["archivo"].str.extract(r"conjunto_de_datos_([a-z]+_[a-z]+)_")[0]
    df["medida"] = [MEDIDAS_VABCOEL.get((a, u)) for a, u in zip(df["clave_archivo"], df["unidad"])]

    # DECISIÓN D10: se descartan los renglones derivados (variación anual, estructura porcentual,
    # distribución por actividad e índice de precios implícitos): se recalculan desde los niveles
    # y guardarlos duplicaría información con redondeos distintos.
    descartados = df["medida"].isna()
    for (archivo, unidad), n in df[descartados].groupby(["clave_archivo", "unidad"]).size().items():
        registrar(log, "vabcoel", "renglones_derivados_descartados", n, f"{archivo}: {unidad}")
    df = df[~descartados].copy()

    # DECISIÓN D14: INEGI publica 'Otros servicios' como hijo de 'Comercio al por menor'
    # ('...|Comercio al por menor|Otros servicios<C1>'), pero la nota C1 lo define como las
    # actividades de servicios distintas al comercio al por mayor y al por menor. Se toma el
    # último nivel del descriptor como componente; si no hay componente, es el total.
    ultimo = partes[~descartados].str[-1].map(normalizar_texto)
    df["componente"] = ultimo.map(COMPONENTES_VABCOEL).fillna(
        ultimo.map(lambda u: "total" if u == "valor agregado bruto" else None))
    exigir(df["componente"].notna().all(), f"vabcoel: componentes desconocidos {ultimo[df['componente'].isna()].unique()}")
    registrar(log, "vabcoel", "jerarquia_otros_servicios_corregida",
              df["descriptores"].str.contains("menor|Otros", regex=False).sum(),
              "'Comercio al por menor|Otros servicios' -> componente 'otros_servicios'")

    largo = a_largo(df, ["medida", "componente"])
    exigir(largo["valor"].notna().all(), "vabcoel: niveles con 'NA'")
    exigir(not largo.duplicated(["anio", "componente", "medida"]).any(), "vabcoel: llave duplicada")

    # Validación: los tres componentes suman el total (tolerancia por redondeo)
    corr = largo[largo["medida"] == "mdp_corrientes"].pivot(index="anio", columns="componente", values="valor")
    suma = corr[["comercio_al_por_mayor", "comercio_al_por_menor", "otros_servicios"]].sum(axis=1)
    exigir(((suma / corr["total"] - 1).abs() < 0.001).all(), "vabcoel: los componentes no suman el total")

    largo = trazabilidad(largo, "INEGI SCNM", "VABCOEL base 2018, cifras 2024 preliminares", fecha_carga)
    return largo[["anio", "componente", "medida", "valor", "estatus_cifra", "fuente", "version_fuente", "fecha_carga"]]


def transformar_pib(engine, cat: pd.DataFrame, fecha_carga: datetime, log: list) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM bronze.pibe", engine)
    registrar(log, "pib_entidad", "renglones_bronze", len(df))
    partes = df["descriptores"].str.replace(r"<[^>]+>", "", regex=True).str.split("|")
    df["precios"] = partes.str[0].map(normalizar_texto).map(PRECIOS_PIBE)
    df["concepto"] = df["archivo"].map(CONCEPTOS_PIBE)
    exigir(df["concepto"].notna().all(), "pib: archivo no reconocido")
    exigir(partes.str[1].str.startswith("B.1bV").all(), "pib: se esperaba solo valor agregado bruto (B.1bV)")

    # DECISIÓN D15: de las 11 presentaciones del tabulado solo se conservan los niveles en
    # millones de pesos (corrientes y constantes 2018); estructura, variaciones, índices y
    # contribuciones se derivan de los niveles.
    descartados = df["precios"].isna()
    registrar(log, "pib_entidad", "renglones_derivados_descartados", descartados.sum(),
              "estructura %, variación anual, índices de volumen y precios, contribución a la variación")
    df = df[~descartados].copy()

    # DECISIÓN D16: el PIB estatal solo trae el nombre de la entidad. Se liga al catálogo por
    # nombre normalizado (sin acentos ni mayúsculas) y se exige coincidencia exacta de las 33.
    nombre = partes[~descartados].str[2].map(normalizar_texto)
    df["cve_ent"] = nombre.map(cat.set_index("nombre_normalizado")["cve_ent"])
    exigir(df["cve_ent"].notna().all(), f"pib: entidades sin clave {nombre[df['cve_ent'].isna()].unique()}")
    exigir(df["cve_ent"].nunique() == N_ENTIDADES + 1, "pib: no están las 32 entidades más el nacional")

    largo = a_largo(df, ["cve_ent", "concepto", "precios"]).rename(columns={"valor": "valor_mdp"})
    exigir(largo["valor_mdp"].notna().all(), "pib: niveles con 'NA'")

    # Validación: la suma de las 32 entidades coincide con el nacional (INEGI advierte redondeo)
    t = largo[largo["concepto"] == "vab_total"]
    est = t[t["cve_ent"] != CVE_NACIONAL].groupby(["anio", "precios"])["valor_mdp"].sum()
    nac = t[t["cve_ent"] == CVE_NACIONAL].set_index(["anio", "precios"])["valor_mdp"]
    exigir(((est / nac - 1).abs() < 0.001).all(), "pib: la suma de entidades no coincide con el nacional")

    largo = trazabilidad(largo, "INEGI PIBE", "PIB por entidad federativa base 2018, 2023 preliminar", fecha_carga)
    return largo[["anio", "cve_ent", "concepto", "precios", "valor_mdp", "estatus_cifra",
                  "fuente", "version_fuente", "fecha_carga"]]


def transformar_oecd(engine, fecha_carga: datetime, log: list) -> pd.DataFrame:
    partes = []
    for tabla in ["oecd_ict_hogares", "oecd_ict_individuos"]:
        df = pd.read_sql(f"SELECT ref_area, measure, unit_measure, time_period, obs_value, obs_status, "
                         f"dataflow FROM bronze.{tabla}", engine)
        registrar(log, "oecd_ict", f"registros_bronze_{tabla}", len(df))
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)

    df[["cod_pais", "pais"]] = df["ref_area"].str.split(": ", n=1, expand=True)
    df[["medida", "desc_medida"]] = df["measure"].str.split(": ", n=1, expand=True)
    df["unidad"] = df["unit_measure"].str.split(":").str[0].map(UNIDADES_OECD)
    exigir(df["unidad"].notna().all(), "oecd: unidad desconocida")
    df["anio"] = df["time_period"].astype(int)
    df["valor"] = pd.to_numeric(df["obs_value"], errors="coerce")
    # DECISIÓN D17: se descartan observaciones sin valor y se conserva la bandera de estatus
    # de OECD (quiebre de serie, definición distinta, baja confiabilidad) para mostrarla.
    sin_valor = df["valor"].isna()
    registrar(log, "oecd_ict", "observaciones_sin_valor_descartadas", sin_valor.sum())
    df = df[~sin_valor].copy()
    df["estatus_obs"] = df["obs_status"].str.split(": ", n=1).str[1]
    registrar(log, "oecd_ict", "observaciones_con_estatus_especial",
              (df["estatus_obs"].notna() & (df["estatus_obs"] != "Normal value")).sum(),
              "quiebre de serie / definición distinta / baja confiabilidad (se conservan con su bandera)")
    exigir(not df.duplicated(["anio", "cod_pais", "medida"]).any(), "oecd: llave duplicada")
    df = trazabilidad(df, "OECD", "ICT Access and Usage by Households and Individuals (DSD_ICT_HH_IND 1.1)",
                      fecha_carga)
    return df[["anio", "cod_pais", "pais", "medida", "desc_medida", "unidad", "valor", "estatus_obs",
               "fuente", "version_fuente", "fecha_carga"]]


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------
def aplicar_ddl(engine) -> None:
    # Cursor de psycopg2 sin parámetros: así un '%' en el SQL no se interpreta como marcador
    with engine.begin() as conn, conn.connection.cursor() as cur:
        cur.execute(INIT_SQL.read_text())


def cargar_silver(engine, tablas: dict, log: list, run_id: str, fecha_carga: datetime) -> None:
    # DECISIÓN HUMANA (temporal): TRUNCATE + INSERT en cada ejecución, en una transacción.
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(f'{SCHEMA}.{t}' for t in TABLAS)}"))
        for nombre in TABLAS:
            df = tablas[nombre]
            df.to_sql(nombre, conn, schema=SCHEMA, if_exists="append", index=False,
                      method=copy_postgres, chunksize=50_000)
            registrar(log, nombre, "filas_cargadas", len(df))
            print(f"OK   {SCHEMA}.{nombre}: {len(df):,} registros")

        pd.DataFrame(log, columns=["tabla", "metrica", "valor", "detalle"]).assign(
            run_id=run_id, fecha_carga=fecha_carga,
        ).to_sql("etl_log", conn, schema=SCHEMA, if_exists="append", index=False)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    engine = create_engine(DB_URL)
    run_id = str(uuid.uuid4())
    fecha_carga = datetime.now(timezone.utc)
    log: list = []
    print(f"run_id: {run_id}")

    aplicar_ddl(engine)

    # DECISIÓN D01: la ENDUTIH 2019 no se usa (ver extractor); queda registrado aquí también.
    registrar(log, "endutih", "anio_2019_excluido", 1, "datos abiertos 2019 sin clave de entidad")

    # Fail-fast: cualquier excepción detiene el script (no se atrapa a propósito).
    cat = transformar_cat_entidad(engine, fecha_carga, log)
    cves = set(cat["cve_ent"]) - {CVE_NACIONAL}
    tablas = {
        "cat_entidad": cat,
        "endutih_mapeo_variables": transformar_mapeo(engine, fecha_carga, log),
        "endutih_hogar": transformar_hogar(engine, cves, fecha_carga, log),
        "endutih_persona": transformar_persona(engine, cves, fecha_carga, log),
        "vabcoel": transformar_vabcoel(engine, fecha_carga, log),
        "pib_entidad": transformar_pib(engine, cat, fecha_carga, log),
        "oecd_ict": transformar_oecd(engine, fecha_carga, log),
    }
    cargar_silver(engine, tablas, log, run_id, fecha_carga)

    print("Carga a silver completada.")


if __name__ == "__main__":
    main()
