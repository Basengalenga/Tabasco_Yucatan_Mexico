"""
Figuras estáticas desde la capa gold de economia_digital_dw.

Lee SOLO de gold y escribe PNG en outputs/figures/:

    serie_<indicador>.png        Yucatán, Tabasco y México 2020-2024 con banda del IC 90%
    brechas_<anio>.png           diferencias entre entidades (pp) con marca de significancia
    ranking_<anio>.png           lugar de Yucatán y Tabasco entre las 32 entidades
    valor_sector51.png           peso del sector 51 en el VAB no minero, 2013-2023
    comercio_electronico.png     VAB del comercio electrónico como % del PIB, 2013-2024
    validacion_oecd.png          ENDUTIH (este pipeline) vs cifras de México en OECD

No forma parte del DAG: se corre a mano cuando gold ya está cargado (ver README).
Cada ejecución sobrescribe los PNG.
"""

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import create_engine

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
DB_URL = os.environ.get("DB_URL", "postgresql+psycopg2://admin:admin123@db:5432/economia_digital_dw")
SALIDA = Path(__file__).resolve().parent.parent / "outputs" / "figures"
DPI = 200

NAC, TAB, YUC = "00", "27", "31"
FOCO = [YUC, TAB, NAC]
NOMBRES = {YUC: "Yucatán", TAB: "Tabasco", NAC: "México"}
# Paleta categórica validada (skill dataviz): los 3 primeros slots pasan CVD en todos los pares
COLOR = {YUC: "#2a78d6", TAB: "#eb6834", NAC: "#1baf7a"}
SUPERFICIE, TINTA, TINTA_2, TENUE, REJILLA = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"

SERIES = ["hog_internet", "hog_computadora", "hog_internet_fija", "pob_internet", "pob_smartphone",
          "usu_compra", "usu_vende", "usu_paga", "usu_banca"]
BRECHAS = ["hog_internet", "hog_internet_fija", "hog_computadora", "pob_smartphone", "pob_internet",
           "pob_redes_sociales", "usu_compra", "usu_vende", "usu_paga", "usu_banca", "sin_internet_recursos"]

plt.rcParams.update({
    "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
    "font.family": "sans-serif", "font.size": 10, "text.color": TINTA, "axes.labelcolor": TINTA_2,
    "xtick.color": TENUE, "ytick.color": TENUE, "axes.edgecolor": "#c3c2b7",
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": REJILLA, "grid.linewidth": 0.6,
    "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left",
})


def guardar(fig, nombre: str) -> None:
    fig.savefig(SALIDA / nombre, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"OK   outputs/figures/{nombre}")


def fuente(fig, texto: str) -> None:
    fig.text(0.01, -0.02, texto, fontsize=7.5, color=TENUE, ha="left", va="top")


# --------------------------------------------------------------------------
# Figuras
# --------------------------------------------------------------------------
def serie(enc: pd.DataFrame, ind: str, nombre: str, unidad: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    d = enc[(enc["id_indicador"] == ind) & enc["cve_ent"].isin(FOCO)]
    for cve in FOCO:
        s = d[d["cve_ent"] == cve].sort_values("anio")
        ax.fill_between(s["anio"], s["li_90"], s["ls_90"], color=COLOR[cve], alpha=0.13, linewidth=0)
        ax.plot(s["anio"], s["estimacion"], color=COLOR[cve], linewidth=2, marker="o", markersize=6,
                markeredgecolor="white", markeredgewidth=1.5, label=NOMBRES[cve])
    # Etiquetas finales separadas para que no se encimen
    fin = d[d["anio"] == d["anio"].max()].sort_values("estimacion")
    rango = max(d["ls_90"].max() - d["li_90"].min(), 1)
    previo, posiciones = -np.inf, []
    for v in fin["estimacion"]:
        previo = max(v, previo + 0.07 * rango)
        posiciones.append(previo)
    ajuste = np.mean(fin["estimacion"]) - np.mean(posiciones)
    for (_, r), y in zip(fin.iterrows(), posiciones):
        ax.annotate(f"{NOMBRES[r['cve_ent']]} {r['estimacion']:.1f}", (r["anio"], y + ajuste), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=9, color=COLOR[r["cve_ent"]], fontweight="bold")
    ax.set_xticks(sorted(d["anio"].unique()))
    ax.set_xlim(d["anio"].min() - 0.2, d["anio"].max() + 0.9)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_title(nombre)
    ax.text(0, 1.01, unidad + " · banda = IC 90%", transform=ax.transAxes, fontsize=8.5, color=TINTA_2)
    fuente(fig, "Fuente: INEGI, ENDUTIH 2020-2024 (microdatos); estimación propia con diseño muestral.")
    guardar(fig, f"serie_{ind}.png")


def brechas(br: pd.DataFrame, indicadores: pd.DataFrame, anio: int) -> None:
    pares = [(YUC, TAB, "Yucatán − Tabasco"), (YUC, NAC, "Yucatán − México"), (TAB, NAC, "Tabasco − México")]
    b = br[(br["anio"] == anio) & (br["id_indicador"].isin(BRECHAS))]
    filas = [i for i in BRECHAS if i in set(b["id_indicador"])]
    m = np.full((len(filas), 3), np.nan)
    sig = np.zeros_like(m, dtype=bool)
    for j, (a, c, _) in enumerate(pares):
        for i, ind in enumerate(filas):
            r = b[(b["id_indicador"] == ind) & (b["entidad_a"] == a) & (b["entidad_b"] == c)].iloc[0]
            m[i, j], sig[i, j] = r["diferencia_pp"], r["significativa"]
    lim = np.nanmax(np.abs(m))
    fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(filas) + 1.2))
    ax.imshow(m, cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    for i in range(len(filas)):
        for j in range(3):
            ax.text(j, i, f"{m[i, j]:+.1f}" + (" ●" if sig[i, j] else ""), ha="center", va="center", fontsize=9,
                    color=TINTA if abs(m[i, j]) < 0.6 * lim else "white")
    ax.set_xticks(range(3), [p[2] for p in pares])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(filas)), [indicadores.loc[i, "nombre"] for i in filas])
    ax.grid(False)
    ax.tick_params(length=0)
    ax.set_title(f"Brechas en puntos porcentuales · {anio}  (● = significativa al 90%)", pad=28)
    fuente(fig, "Prueba z con errores estándar de diseño; contra el nacional se descuenta la covarianza entidad-país.")
    guardar(fig, f"brechas_{anio}.png")


def ranking(enc: pd.DataFrame, rk: pd.DataFrame, indicadores: pd.DataFrame, anio: int) -> None:
    lista = ["hog_internet", "hog_computadora", "pob_internet", "pob_smartphone", "usu_compra", "usu_paga",
             "usu_banca", "usu_vende"]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for i, ind in enumerate(lista[::-1]):
        e = enc[(enc["anio"] == anio) & (enc["id_indicador"] == ind)]
        otros = e[~e["cve_ent"].isin(FOCO)]
        ax.scatter(otros["estimacion"], [i] * len(otros), s=28, color="#d9d8d2", edgecolor="white", linewidth=0.8)
        nac = e[e["cve_ent"] == NAC]["estimacion"].iloc[0]
        ax.plot([nac, nac], [i - 0.3, i + 0.3], color=COLOR[NAC], linewidth=2.5)
        for cve in [TAB, YUC]:
            v = e[e["cve_ent"] == cve]["estimacion"].iloc[0]
            lugar = rk[(rk["anio"] == anio) & (rk["id_indicador"] == ind) & (rk["cve_ent"] == cve)]["rango"].iloc[0]
            ax.scatter([v], [i], s=90, color=COLOR[cve], edgecolor="white", linewidth=1.5, zorder=3)
            ax.annotate(f"#{lugar}", (v, i), xytext=(0, 8 if cve == YUC else -12), textcoords="offset points",
                        ha="center", fontsize=7.5, color=COLOR[cve], fontweight="bold")
    ax.set_yticks(range(len(lista)), [indicadores.loc[i, "nombre"] for i in lista[::-1]])
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="x", color=REJILLA)
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Yucatán y Tabasco entre las 32 entidades · {anio}")
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=COLOR[YUC], label="Yucatán"),
               plt.Line2D([], [], marker="o", linestyle="", color=COLOR[TAB], label="Tabasco"),
               plt.Line2D([], [], color=COLOR[NAC], linewidth=2.5, label="México (nacional)"),
               plt.Line2D([], [], marker="o", linestyle="", color="#d9d8d2", label="Otras entidades")]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8)
    fuente(fig, "#n = lugar entre las 32 entidades (1 = valor más alto). Fuente: INEGI, ENDUTIH.")
    guardar(fig, f"ranking_{anio}.png")


def valor_sector51(valor: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    for cve in FOCO:
        s = valor[(valor["cve_ent"] == cve) & (valor["anio"] >= 2013)].sort_values("anio")
        ax.plot(s["anio"], s["participacion_51_no_minero"], color=COLOR[cve], linewidth=2, marker="o", markersize=5,
                markeredgecolor="white", label=NOMBRES[cve])
        u = s.iloc[-1]
        ax.annotate(f"{NOMBRES[cve]} {u['participacion_51_no_minero']:.2f}%", (u["anio"], u["participacion_51_no_minero"]),
                    xytext=(8, 0), textcoords="offset points", va="center", fontsize=9, color=COLOR[cve],
                    fontweight="bold")
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.1f}%")
    ax.set_xlim(2012.6, 2025.6)
    ax.set_title("Peso del sector 51 (información) en el VAB no minero")
    fuente(fig, "VAB sector 51 / (VAB total − VAB sector 21), precios corrientes. Fuente: INEGI, PIB por entidad "
                "federativa base 2018 (2023 preliminar).")
    guardar(fig, "valor_sector51.png")


def comercio_electronico(coel: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(coel["anio"], coel["pct_pib"], color=COLOR[NAC], linewidth=2.4, marker="o", markersize=6,
            markeredgecolor="white")
    for a in [coel["anio"].min(), coel["anio"].max()]:
        v = coel.loc[coel["anio"] == a, "pct_pib"].iloc[0]
        ax.annotate(f"{v:.1f}%", (a, v), xytext=(0, 9), textcoords="offset points", ha="center", fontweight="bold")
    ax.set_ylim(0, coel["pct_pib"].max() * 1.2)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_title("Comercio electrónico como % del PIB de México")
    fuente(fig, "Fuente: INEGI, Valor Agregado Bruto del Comercio Electrónico, base 2018 (2024 preliminar).")
    guardar(fig, "comercio_electronico.png")


def validacion_oecd(val: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([0, 100], [0, 100], color=TENUE, linewidth=1, linestyle=":")
    ax.scatter(val["valor_oecd"], val["valor_endutih"], s=40, color=COLOR[NAC], edgecolor="white", linewidth=1, zorder=3)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Cifra de México en OECD (%)")
    ax.set_ylabel("Estimación de este pipeline (%)")
    ax.grid(axis="both", color=REJILLA)
    exactas = (val["diferencia_pp"].abs() < 0.01).mean()
    ax.set_title(f"Validación: {exactas:.0%} coinciden al centésimo")
    fuente(fig, f"{len(val)} pares año × medida (2020-2024). Línea = igualdad perfecta.")
    guardar(fig, "validacion_oecd.png")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DB_URL)
    enc = pd.read_sql("SELECT * FROM gold.fact_encuesta_tic WHERE grupo_edad = 'total'", engine)
    indicadores = pd.read_sql("SELECT * FROM gold.dim_indicador", engine).set_index("id_indicador")
    br = pd.read_sql("SELECT * FROM gold.resultado_brecha", engine)
    rk = pd.read_sql("SELECT * FROM gold.resultado_ranking", engine)
    valor = pd.read_sql("SELECT * FROM gold.valor_entidad_anio", engine)
    coel = pd.read_sql("SELECT * FROM gold.comercio_electronico_anio ORDER BY anio", engine)
    val = pd.read_sql("SELECT * FROM gold.resultado_validacion_oecd", engine)
    for df in (enc, br, rk, valor):
        for c in ("cve_ent", "entidad_a", "entidad_b"):
            if c in df:
                df[c] = df[c].str.strip()

    for ind in SERIES:
        serie(enc, ind, indicadores.loc[ind, "nombre"], indicadores.loc[ind, "unidad"])
    for anio in sorted(enc["anio"].unique()):
        brechas(br, indicadores, anio)
        ranking(enc, rk, indicadores, anio)
    valor_sector51(valor)
    comercio_electronico(coel)
    validacion_oecd(val)


if __name__ == "__main__":
    main()
