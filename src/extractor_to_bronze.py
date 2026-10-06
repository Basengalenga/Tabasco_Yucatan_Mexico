"""
Extracción y carga a la capa bronze de economia_digital_dw.

Cada extracción es una función independiente que descarga su fuente oficial y la
carga al esquema `bronze`:

    bronze.endutih_{hogares|usuarios|usuarios2}_<anio>  <- INEGI ENDUTIH 2020-2024, microdatos
    bronze.endutih_diccionario                           <- INEGI ENDUTIH, diccionarios de datos
    bronze.endutih_cat_entidad                           <- INEGI ENDUTIH 2024, catálogo de entidades
    bronze.vabcoel                                       <- INEGI, Valor Agregado Bruto del
                                                            Comercio Electrónico (cuentas nacionales)
    bronze.pibe                                          <- INEGI, PIB por entidad federativa
                                                            (VAB total, sector 51 y sector 21)
    bronze.oecd_ict_hogares / bronze.oecd_ict_individuos <- OECD ICT Access and Usage (SDMX)

Reglas de bronze:
    - Todas las columnas de la fuente se guardan como TEXT, sin limpiar ni transformar.
    - Nombres de columna normalizados a snake_case sin acentos.
    - Metadatos agregados: _ingested_at, _source_url, _run_id (y _archivo cuando la fuente
      es un ZIP con varios archivos). _ingested_at es el inicio del lote, igual para todas
      las tablas; en Airflow es el logical_date del DAG run.

Microdatos de la ENDUTIH:
    Cada archivo se carga a su propia tabla, con las columnas exactas de ese año (la
    numeración de las preguntas cambia entre levantamientos). Se cargan con COPY directo
    desde el ZIP, sin pasar por pandas: ~290 mil registros × ~230 columnas por tabla no
    caben cómodos en memoria como DataFrame de texto. Las columnas de metadatos llevan su
    valor como DEFAULT de la tabla, así COPY no tiene que tocar las filas.

Manejo de errores (fail-fast):
    Dentro de cada función primero se descarga todo y solo después se toca la base, en
    una transacción. Una descarga fallida nunca deja una tabla incompleta.

Requisito: el esquema `bronze` ya existe (se crea en sql/init.sql).
"""

import csv
import hashlib
import io
import os
import re
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.types import Text

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
DB_URL = os.environ.get("DB_URL", "postgresql+psycopg2://admin:admin123@db:5432/economia_digital_dw")
SCHEMA = "bronze"

INEGI = "https://www.inegi.org.mx/contenidos/programas"

# ENDUTIH: hasta 2022 el programa vive en /dutih/; desde 2023 en /endutih/.
# 2019 se excluye a propósito: su archivo de datos abiertos no trae la clave de entidad
# (ver docs/decisiones_limpieza.md, decisión D01).
URLS_ENDUTIH = {
    2020: f"{INEGI}/dutih/2020/datosabiertos/conjunto_de_datos_endutih_2020_csv.zip",
    2021: f"{INEGI}/dutih/2021/datosabiertos/conjunto_de_datos_endutih_2021_csv.zip",
    2022: f"{INEGI}/dutih/2022/datosabiertos/conjunto_de_datos_endutih_2022_csv.zip",
    2023: f"{INEGI}/endutih/2023/datosabiertos/conjunto_de_datos_endutih_2023_csv.zip",
    2024: f"{INEGI}/endutih/2024/datosabiertos/conjunto_de_datos_endutih_2024_csv.zip",
}
# Archivo de la fuente -> nombre de tabla. 2020 y 2021 usan singular (hogar, usuario);
# desde 2022, plural. Solo se uniforma el nombre de la tabla; el archivo queda en _archivo.
# No se cargan residentes ni viviendas: ningún indicador del proyecto los usa (decisión D02).
PATRON_TABLAS_ENDUTIH = {
    r"tr_endutih_hogar(es)?_anual": "hogares",
    r"tr_endutih_usuario(s)?_anual": "usuarios",
    r"tr_endutih_usuario(s)?2_anual": "usuarios2",
}

URL_VABCOEL = f"{INEGI}/vabcoel/2018/datosabiertos/conjunto_de_datos_vabcoel2018_csv.zip"

URL_PIBE = f"{INEGI}/pibent/2018/datosabiertos/pibe_datos_abiertos_csv.zip"
# Del ZIP del PIB estatal (79 tabulados) solo se cargan los 3 que usa el proyecto (decisión D03)
ARCHIVOS_PIBE = {
    "conjunto_de_datos_pibe_actividad_b.1bv2023_p.csv": "vab_total",
    "conjunto_de_datos_pibe_actividad_512023_p.csv": "vab_51",
    "conjunto_de_datos_pibe_actividad_212023_p.csv": "vab_21",
}

# OECD SDMX: se pide solo el total nacional (sin desagregar por edad, sexo, ingreso...) de
# las medidas que se usan; el flujo completo pesa ~180 MB (decisión D04).
OECD_SDMX = "https://sdmx.oecd.org/public/rest/data/OECD.STI.DEP"
URLS_OECD = {
    "oecd_ict_hogares": f"{OECD_SDMX},DSD_ICT_HH_IND@DF_HH,/"
                        ".A.A1_HH+B1_HH+B21A_HH+B21B_HH.PT_HH._T._Z._Z._Z._T._Z?startPeriod=2015",
    "oecd_ict_individuos": f"{OECD_SDMX},DSD_ICT_HH_IND@DF_IND,/"
                           ".A.C5B_I+C2B_I+G1_I+D1T_I+D1U_I+F1_I+D1B_I.PT_POP._Z.Y16T74._T._T._T._T"
                           "?startPeriod=2015",
}
HEADERS_OECD = {"Accept": "application/vnd.sdmx.data+csv; charset=utf-8; labels=both"}


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def normalizar_columna(nombre: str) -> str:
    """'Bien jurídico afectado' -> 'bien_juridico_afectado'; '2023<R>' -> '2023_r'."""
    sin_acentos = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    snake = re.sub(r"[^a-z0-9]+", "_", sin_acentos.lower())
    return snake.strip("_")


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [normalizar_columna(c) for c in df.columns]
    return df


def agregar_metadatos(df: pd.DataFrame, source_url: str, run_id: str, ingested_at: datetime) -> pd.DataFrame:
    """Se agregan después de normalizar, porque la normalización quitaría el '_' inicial."""
    df["_ingested_at"] = ingested_at
    df["_source_url"] = source_url
    df["_run_id"] = run_id
    return df


# Opcional, solo para desarrollo: si CACHE_DESCARGAS apunta a una carpeta, cada descarga se
# guarda ahí y se reutiliza (INEGI puede tardar varios minutos). En Airflow no se define.
CACHE_DESCARGAS = os.environ.get("CACHE_DESCARGAS")


def descargar(url: str, **kwargs) -> bytes:
    cache = None
    if CACHE_DESCARGAS:
        cache = os.path.join(CACHE_DESCARGAS, hashlib.md5(url.encode()).hexdigest())
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return f.read()
    r = requests.get(url, timeout=600, **kwargs)
    r.raise_for_status()
    if cache:
        with open(cache, "wb") as f:
            f.write(r.content)
    return r.content


def abrir_zip(contenido: bytes, url: str) -> zipfile.ZipFile:
    # INEGI responde 200 con una página HTML cuando el archivo no existe
    if not contenido.startswith(b"PK"):
        raise ValueError(f"La descarga no es un ZIP (¿cambió la URL?): {url}")
    return zipfile.ZipFile(io.BytesIO(contenido))


def leer_csv_texto(raw: bytes) -> str:
    """Los CSV de INEGI vienen en UTF-8 (algunos con BOM); latin-1 queda como respaldo."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def cargar_tabla(df: pd.DataFrame, tabla: str, conn) -> None:
    """Carga un DataFrame a bronze, reemplazando la tabla, con las columnas de la fuente como TEXT."""
    dtype = {c: Text() for c in df.columns if c != "_ingested_at"}
    df.to_sql(tabla, conn, schema=SCHEMA, if_exists="replace", index=False,
              dtype=dtype, chunksize=10_000, method="multi")
    print(f"OK   {SCHEMA}.{tabla}: {len(df):,} registros")


def copiar_csv_crudo(conn, tabla: str, raw: bytes, archivo: str, source_url: str,
                     run_id: str, ingested_at: datetime) -> int:
    """Crea bronze.<tabla> con las columnas del encabezado del CSV y lo carga con COPY, sin tocar las filas."""
    # DECISIÓN D05: el archivo de hogares 2023 mezcla finales de línea (encabezado CRLF,
    # datos LF) y COPY lo rechaza. Se uniforman a LF; ningún valor de las filas cambia.
    texto = leer_csv_texto(raw).replace("\r\n", "\n")
    encabezado = next(csv.reader(io.StringIO(texto.split("\n", 1)[0])))
    columnas = [normalizar_columna(c) for c in encabezado]
    if len(set(columnas)) != len(columnas):
        raise ValueError(f"{archivo}: columnas duplicadas tras normalizar")

    meta = {
        "_ingested_at": f"TIMESTAMPTZ DEFAULT '{ingested_at.isoformat()}'",
        "_source_url": f"TEXT DEFAULT '{source_url}'",
        "_run_id": f"TEXT DEFAULT '{run_id}'",
        "_archivo": f"TEXT DEFAULT '{archivo}'",
    }
    definicion = ", ".join([*(f'"{c}" TEXT' for c in columnas), *(f'"{c}" {t}' for c, t in meta.items())])
    conn.exec_driver_sql(f'DROP TABLE IF EXISTS {SCHEMA}."{tabla}"')
    conn.exec_driver_sql(f'CREATE TABLE {SCHEMA}."{tabla}" ({definicion})')

    lista = ", ".join(f'"{c}"' for c in columnas)
    with conn.connection.cursor() as cur:
        cur.copy_expert(f'COPY {SCHEMA}."{tabla}" ({lista}) FROM STDIN WITH (FORMAT csv, HEADER true)',
                        io.StringIO(texto))
        n = cur.rowcount
    print(f"OK   {SCHEMA}.{tabla}: {n:,} registros ({len(columnas)} columnas)")
    return n


# --------------------------------------------------------------------------
# Extracciones
# --------------------------------------------------------------------------
def extraer_cargar_endutih(engine, run_id: str, ingested_at: datetime) -> None:
    """ENDUTIH 2020-2024: hogares, usuarios y usuarios2 por año, diccionarios y catálogo de entidades."""
    zips = {}
    for anio, url in URLS_ENDUTIH.items():  # fail-fast: primero se descargan todos los años
        zips[anio] = abrir_zip(descargar(url), url)
        print(f"     endutih {anio}: descargado")

    diccionarios, catalogo = [], None
    with engine.begin() as conn:
        for anio, z in zips.items():
            url = URLS_ENDUTIH[anio]
            nombres = z.namelist()
            for patron, tabla in PATRON_TABLAS_ENDUTIH.items():
                datos = [n for n in nombres if re.search(rf"conjuntos?_de_datos/{patron}_{anio}\.csv$", n)]
                if len(datos) != 1:
                    raise ValueError(f"endutih {anio}: se esperaba 1 archivo para '{tabla}', hay {datos}")
                archivo = datos[0]
                copiar_csv_crudo(conn, f"endutih_{tabla}_{anio}", z.read(archivo), archivo.split("/")[-1],
                                 url, run_id, ingested_at)

                dic = [n for n in nombres if "diccionario" in n.lower()
                       and n.endswith(archivo.split("/")[-1])]
                if len(dic) != 1:
                    raise ValueError(f"endutih {anio}: no se encontró el diccionario de {archivo}")
                d = pd.read_csv(io.StringIO(leer_csv_texto(z.read(dic[0]))), dtype=str)
                d = normalizar_columnas(d)
                d["anio"], d["tabla"], d["_archivo"] = str(anio), tabla, dic[0].split("/")[-1]
                diccionarios.append(agregar_metadatos(d, url, run_id, ingested_at))

            cat = [n for n in nombres if n.endswith("tc_endutih_entidad.csv")]
            if cat:
                catalogo = pd.read_csv(io.StringIO(leer_csv_texto(z.read(cat[0]))), dtype=str)
                catalogo = agregar_metadatos(normalizar_columnas(catalogo), url, run_id, ingested_at)

        if catalogo is None:
            raise ValueError("endutih: ningún año trae el catálogo de entidades (tc_endutih_entidad.csv)")
        cargar_tabla(pd.concat(diccionarios, ignore_index=True), "endutih_diccionario", conn)
        cargar_tabla(catalogo, "endutih_cat_entidad", conn)


def leer_tabulado_inegi(raw: bytes) -> pd.DataFrame:
    """Tabulado de datos abiertos de INEGI: 'Descriptores' + una columna por año ('2023<R>', '2024<P>')."""
    return normalizar_columnas(pd.read_csv(io.StringIO(leer_csv_texto(raw)), dtype=str))


def extraer_cargar_vabcoel(engine, run_id: str, ingested_at: datetime) -> None:
    """Valor Agregado Bruto del Comercio Electrónico 2013-2024 (los 7 tabulados del ZIP)."""
    z = abrir_zip(descargar(URL_VABCOEL), URL_VABCOEL)
    indice = pd.read_csv(io.StringIO(leer_csv_texto(z.read("conjunto_de_datos/indice.csv"))),
                         header=None, names=["archivo", "titulo"], dtype=str)
    partes = []
    for archivo, titulo in indice.itertuples(index=False):
        df = leer_tabulado_inegi(z.read(f"conjunto_de_datos/{archivo}"))
        df["archivo"], df["titulo"] = archivo, titulo
        partes.append(df)
    df = agregar_metadatos(pd.concat(partes, ignore_index=True), URL_VABCOEL, run_id, ingested_at)
    with engine.begin() as conn:
        cargar_tabla(df, "vabcoel", conn)


def extraer_cargar_pibe(engine, run_id: str, ingested_at: datetime) -> None:
    """PIB por entidad federativa 2003-2023: VAB total, sector 51 (información) y sector 21 (minería)."""
    z = abrir_zip(descargar(URL_PIBE), URL_PIBE)
    partes = []
    for archivo in ARCHIVOS_PIBE:
        df = leer_tabulado_inegi(z.read(f"conjunto_de_datos/{archivo}"))
        df["archivo"] = archivo
        partes.append(df)
    df = agregar_metadatos(pd.concat(partes, ignore_index=True), URL_PIBE, run_id, ingested_at)
    with engine.begin() as conn:
        cargar_tabla(df, "pibe", conn)


def extraer_cargar_oecd(engine, run_id: str, ingested_at: datetime) -> None:
    """OECD ICT Access and Usage by Households / Individuals, total nacional por país."""
    tablas = {}
    for tabla, url in URLS_OECD.items():
        df = pd.read_csv(io.BytesIO(descargar(url, headers=HEADERS_OECD)), dtype=str)
        # 'REF_AREA: Reference area' -> 'ref_area' (la etiqueta larga va en los valores: 'MEX: Mexico')
        df.columns = [normalizar_columna(c.split(":")[0]) for c in df.columns]
        if df.empty:
            raise ValueError(f"{tabla}: la consulta SDMX no devolvió registros")
        tablas[tabla] = agregar_metadatos(df, url, run_id, ingested_at)
    with engine.begin() as conn:
        for tabla, df in tablas.items():
            cargar_tabla(df, tabla, conn)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    engine = create_engine(DB_URL)
    run_id = str(uuid.uuid4())
    ingested_at = datetime.now(timezone.utc)
    print(f"run_id: {run_id}")

    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))

    # Fail-fast: cualquier excepción detiene el script (no se atrapa a propósito).
    extraer_cargar_endutih(engine, run_id, ingested_at)
    extraer_cargar_vabcoel(engine, run_id, ingested_at)
    extraer_cargar_pibe(engine, run_id, ingested_at)
    extraer_cargar_oecd(engine, run_id, ingested_at)

    print("Carga a bronze completada.")


if __name__ == "__main__":
    main()
