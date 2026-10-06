"""
Dashboard de economia_digital_dw (Streamlit): Yucatán vs Tabasco vs México.

Lee SOLO de la API (api/main.py), que a su vez lee la capa gold: estimaciones de la
ENDUTIH con su intervalo de confianza, valor económico (PIB estatal y comercio
electrónico), comparación OECD y resultados de src/gold_analytics.py.

Correr local:   streamlit run dashboard/main.py   (con la API en API_URL, por defecto localhost:8000)
Correr Docker:  docker compose up -d  ->  http://localhost:8501
"""

import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
API_URL = os.environ.get("API_URL", "http://localhost:8000")

NAC, TAB, YUC = "00", "27", "31"
FOCO = [YUC, TAB, NAC]
NOMBRES = {YUC: "Yucatán", TAB: "Tabasco", NAC: "México"}
# Paleta categórica validada (skill dataviz, 3 primeros slots: pasan CVD en todos los pares).
# El color sigue a la entidad en todas las gráficas.
COLOR = {YUC: "#2a78d6", TAB: "#eb6834", NAC: "#1baf7a"}
COLOR_NOMBRE = {NOMBRES[k]: v for k, v in COLOR.items()}
GRIS, GRIS_CLARO = "#898781", "#d9d8d2"
TINTA, TINTA_2 = "#0b0b0b", "#52514e"
AGREGADOS_OECD = ["OECD", "EU27", "EU28"]  # promedios, no países
DIVERGENTE = [[0, "#184f95"], [0.5, "#f0efec"], [1, "#b42f2f"]]

st.set_page_config(page_title="Economía digital · Yucatán, Tabasco y México", page_icon="📶", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1.6rem; max-width: 1400px; }
    h1, h2, h3 { letter-spacing: -0.01em; }
    .hero { padding: 6px 0 14px 0; }
    .hero h1 { font-size: 2.15rem; margin: 0; line-height: 1.15; }
    .hero h1 .y { color: #2a78d6; } .hero h1 .t { color: #eb6834; } .hero h1 .m { color: #1baf7a; }
    .hero p { color: #52514e; margin: 6px 0 0 0; font-size: 0.98rem; }
    .chip { display:inline-block; padding: 2px 10px; border-radius: 999px; background:#f0efec;
            color:#52514e; font-size: 0.78rem; margin-right: 6px; }
    .card { background: #ffffff; border: 1px solid rgba(11,11,11,0.08); border-radius: 14px;
            padding: 16px 18px 14px 18px; height: 100%; box-shadow: 0 1px 2px rgba(11,11,11,0.04); }
    .card .ent { font-weight: 650; font-size: 1.02rem; display:flex; align-items:center; gap:8px; }
    .card .dot { width: 10px; height: 10px; border-radius: 50%; display:inline-block; }
    .kpi { display:flex; justify-content: space-between; align-items: baseline; padding: 7px 0;
           border-bottom: 1px solid #f0efec; }
    .kpi:last-child { border-bottom: none; }
    .kpi .lab { color:#52514e; font-size: 0.86rem; }
    .kpi .val { font-size: 1.32rem; font-weight: 650; color:#0b0b0b; }
    .kpi .sub { color:#898781; font-size: 0.75rem; margin-left: 6px; font-weight: 400; }
    .hall { background: #ffffff; border: 1px solid rgba(11,11,11,0.08); border-left: 4px solid var(--c);
            border-radius: 12px; padding: 14px 16px; height: 100%; }
    .hall .big { font-size: 1.9rem; font-weight: 700; color: #0b0b0b; line-height: 1.1; }
    .hall .tit { font-weight: 600; margin: 4px 0 4px 0; }
    .hall .txt { color: #52514e; font-size: 0.88rem; }
    .nota { color: #52514e; font-size: 0.86rem; }
    [data-testid="stMetric"] { background:#fff; border:1px solid rgba(11,11,11,0.08); border-radius:12px; padding:12px 14px; }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Datos (todo desde la API)
# --------------------------------------------------------------------------
@st.cache_data(ttl=600)
def api(ruta: str) -> pd.DataFrame:
    r = requests.get(f"{API_URL}{ruta}", timeout=120)
    r.raise_for_status()
    return pd.DataFrame(r.json())


encuesta = api("/encuesta")
indicadores = api("/indicadores").set_index("id_indicador")
entidades = api("/entidades").set_index("cve_ent")
valor = api("/valor")
coel = api("/comercio-electronico")
brecha = api("/resultados/brecha")
tendencia = api("/resultados/tendencia")
ranking = api("/resultados/ranking")
validacion = api("/resultados/validacion-oecd")

ANIOS = sorted(encuesta["anio"].unique())
foco = encuesta[encuesta["cve_ent"].isin(FOCO)].assign(entidad=lambda d: d["cve_ent"].map(NOMBRES))


def nombre_ind(i: str) -> str:
    return indicadores.loc[i, "nombre"]


def valor_de(anio: int, cve: str, ind: str, col: str = "estimacion") -> float:
    fila = encuesta[(encuesta["anio"] == anio) & (encuesta["cve_ent"] == cve) & (encuesta["id_indicador"] == ind)]
    return float(fila[col].iloc[0]) if len(fila) else np.nan


# --------------------------------------------------------------------------
# Estilo de gráficas
# --------------------------------------------------------------------------
def estilo(fig: go.Figure, alto: int = 360, leyenda: bool = True) -> go.Figure:
    fig.update_layout(
        height=alto, margin=dict(l=8, r=8, t=74, b=8),
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13, color=TINTA),
        title_font=dict(size=15, color=TINTA), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
        showlegend=leyenda, hoverlabel=dict(bgcolor="white", font_size=13),
    )
    fig.update_xaxes(showgrid=False, linecolor="#c3c2b7", ticks="outside", tickcolor="#c3c2b7")
    fig.update_yaxes(gridcolor="#ecebe7", zeroline=False, linecolor="rgba(0,0,0,0)")
    return fig


def serie_con_ic(ind: str, titulo: str | None = None, alto: int = 330) -> go.Figure:
    """Líneas de las 3 entidades con banda del IC 90% y etiqueta directa al final."""
    fig = go.Figure()
    d = foco[foco["id_indicador"] == ind].sort_values("anio")
    for cve in FOCO:
        s = d[d["cve_ent"] == cve]
        c = COLOR[cve]
        fig.add_trace(go.Scatter(
            x=list(s["anio"]) + list(s["anio"][::-1]), y=list(s["ls_90"]) + list(s["li_90"][::-1]),
            fill="toself", fillcolor=c, opacity=0.13, mode="lines", line=dict(width=0), hoverinfo="skip",
            showlegend=False))
        fig.add_trace(go.Scatter(
            x=s["anio"], y=s["estimacion"], name=NOMBRES[cve], mode="lines+markers",
            line=dict(color=c, width=2.4), marker=dict(size=8, line=dict(width=2, color="white")),
            customdata=np.stack([s["li_90"], s["ls_90"], s["calidad"]], axis=-1),
            hovertemplate=f"<b>{NOMBRES[cve]}</b> %{{x}}: %{{y:.1f}}%<br>IC 90%: %{{customdata[0]:.1f}} – "
                          "%{customdata[1]:.1f} · calidad %{customdata[2]}<extra></extra>"))
    # Etiqueta directa al final de cada línea, separadas para que no se encimen
    ultimos = d[d["anio"] == d["anio"].max()].sort_values("estimacion")
    rango = max(d["ls_90"].max() - d["li_90"].min(), 1)
    posiciones, previo = [], -np.inf
    for v in ultimos["estimacion"]:
        previo = max(v, previo + 0.07 * rango)
        posiciones.append(previo)
    desplazamiento = (np.mean(ultimos["estimacion"]) - np.mean(posiciones))
    for (_, r), y in zip(ultimos.iterrows(), posiciones):
        fig.add_annotation(x=r["anio"], y=y + desplazamiento, text=f"<b>{r['estimacion']:.1f}</b>", showarrow=False,
                           xanchor="left", xshift=10, font=dict(color=COLOR[r["cve_ent"]], size=12))
    fig.update_xaxes(dtick=1, range=[min(ANIOS) - 0.2, max(ANIOS) + 0.6])
    fig.update_yaxes(ticksuffix="%")
    fig.update_layout(title=titulo or nombre_ind(ind), hovermode="closest")
    return estilo(fig, alto)


def hallazgo(col, color: str, cifra: str, titulo: str, texto: str) -> None:
    col.markdown(f'<div class="hall" style="--c:{color}"><div class="big">{cifra}</div>'
                 f'<div class="tit">{titulo}</div><div class="txt">{texto}</div></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Encabezado y filtros
# --------------------------------------------------------------------------
st.markdown(
    '<div class="hero"><h1>Economía digital: <span class="y">Yucatán</span> vs <span class="t">Tabasco</span> '
    'vs <span class="m">México</span></h1>'
    '<p>Acceso, uso y valor de las tecnologías de la información, 2020–2024. '
    'Estimaciones con intervalo de confianza al 90% calculadas desde los microdatos.</p>'
    '<div style="margin-top:8px"><span class="chip">INEGI · ENDUTIH 2020–2024</span>'
    '<span class="chip">INEGI · VAB del comercio electrónico</span><span class="chip">INEGI · PIB por entidad</span>'
    '<span class="chip">OECD · ICT Access & Usage</span></div></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Filtros")
    anio = st.select_slider("Año de la ENDUTIH", options=ANIOS, value=ANIOS[-1])
    st.divider()
    st.caption("**Cómo leer las cifras.** Son estimaciones de una encuesta por muestreo: cada una trae un "
               "intervalo de confianza al 90% (la banda sombreada). Dos entidades solo son distintas si la "
               "prueba de diferencias lo dice (pestaña «Brechas»).")
    st.caption("**Calidad.** Coeficiente de variación < 15% alta, 15–30% moderada, > 30% baja (criterio de INEGI).")

tabs = st.tabs(["✦ Panorama", "Acceso", "Uso", "Valor económico", "Brechas y significancia",
                "Contexto internacional", "Calidad de datos"])

# --------------------------------------------------------------------------
# 1. Panorama
# --------------------------------------------------------------------------
with tabs[0]:
    v_anio = valor[valor["anio"] == valor["anio"].max()]
    anio_pib = int(valor["anio"].max())
    kpis = [("pob_internet", "Usuarios de internet"), ("hog_internet", "Hogares con internet"),
            ("hog_computadora", "Hogares con computadora"), ("usu_compra", "Compran en línea¹"),
            ("usu_vende", "Venden en línea¹")]
    cols = st.columns(3)
    for col, cve in zip(cols, FOCO):
        filas = ""
        for ind, lab in kpis:
            v = valor_de(anio, cve, ind)
            r = ranking[(ranking["anio"] == anio) & (ranking["cve_ent"] == cve) & (ranking["id_indicador"] == ind)]
            sub = f'<span class="sub">#{int(r["rango"].iloc[0])} de 32</span>' if len(r) else ""
            filas += f'<div class="kpi"><span class="lab">{lab}</span><span class="val">{v:.1f}%{sub}</span></div>'
        p51 = v_anio.loc[v_anio["cve_ent"] == cve, "participacion_51_no_minero"].iloc[0]
        filas += (f'<div class="kpi"><span class="lab">Sector 51 en la economía no minera ({anio_pib})</span>'
                  f'<span class="val">{p51:.2f}%</span></div>')
        col.markdown(f'<div class="card"><div class="ent"><span class="dot" style="background:{COLOR[cve]}"></span>'
                     f'{NOMBRES[cve]}</div>{filas}</div>', unsafe_allow_html=True)
    st.caption(f"Año {anio}. ¹ Porcentaje de los usuarios de internet (compras y ventas en los últimos 12 meses). "
               "#n de 32 = lugar entre las 32 entidades (1 = más alto).")

    st.subheader("Lo que encontramos")
    ini, fin = ANIOS[0], ANIOS[-1]
    t = tendencia.set_index(["cve_ent", "id_indicador"])
    rk = ranking[(ranking["anio"] == fin)].set_index(["cve_ent", "id_indicador"])["rango"]
    c1, c2, c3 = st.columns(3)
    hallazgo(c1, COLOR[YUC], f"#{rk[(YUC, 'usu_vende')]} de 32",
             "Yucatán, el estado que más vende en línea",
             f"El {valor_de(fin, YUC, 'usu_vende'):.1f}% de sus usuarios de internet vendió algo en línea en {fin}, "
             f"casi el doble que el promedio nacional ({valor_de(fin, NAC, 'usu_vende'):.1f}%). También es "
             f"#{rk[(YUC, 'usu_compra')]} en compras.")
    hallazgo(c2, COLOR[TAB], f"+{t.loc[(TAB, 'hog_internet'), 'cambio_pp']:.0f} pp",
             "Tabasco cerró la brecha de conexión en el hogar",
             f"Sus hogares con internet pasaron de {t.loc[(TAB, 'hog_internet'), 'valor_inicial']:.1f}% a "
             f"{t.loc[(TAB, 'hog_internet'), 'valor_final']:.1f}% ({ini}–{fin}); la distancia con el nacional "
             f"bajó de {valor_de(ini, NAC, 'hog_internet') - valor_de(ini, TAB, 'hog_internet'):.0f} pp a "
             f"{valor_de(fin, NAC, 'hog_internet') - valor_de(fin, TAB, 'hog_internet'):.0f} pp (ya no es "
             "significativa).")
    hallazgo(c3, COLOR[NAC], f"{valor_de(fin, NAC, 'hog_computadora'):.0f}%",
             "La computadora no despega; el celular sí",
             f"Los hogares con computadora están estancados en México ({valor_de(ini, NAC, 'hog_computadora'):.1f}% "
             f"→ {valor_de(fin, NAC, 'hog_computadora'):.1f}%) mientras los usuarios de smartphone suben a "
             f"{valor_de(fin, NAC, 'pob_smartphone'):.0f}%. Tabasco tiene la menor tasa de las tres "
             f"({valor_de(fin, TAB, 'hog_computadora'):.1f}%, #{rk[(TAB, 'hog_computadora')]} de 32).")
    st.write("")
    c1, c2, c3 = st.columns(3)
    vt = valor[(valor["anio"] == anio_pib)].set_index("cve_ent")
    hallazgo(c1, COLOR[TAB], f"{vt.loc[TAB, 'participacion_21']:.0f}%",
             "El petróleo esconde la economía digital de Tabasco",
             f"La minería (petróleo) es el {vt.loc[TAB, 'participacion_21']:.0f}% del VAB de Tabasco. Sin ella, el "
             f"sector de información pesa {vt.loc[TAB, 'participacion_51_no_minero']:.2f}% (con ella "
             f"{vt.loc[TAB, 'participacion_51']:.2f}%), aún lejos del nacional "
             f"({vt.loc[NAC, 'participacion_51_no_minero']:.2f}%).")
    c0 = coel.set_index("anio")
    hallazgo(c2, COLOR[NAC], f"{c0['pct_pib'].iloc[-1]:.1f}% del PIB",
             "El comercio electrónico se duplicó en la economía",
             f"Pasó de {c0['pct_pib'].iloc[0]:.1f}% del PIB nacional en {c0.index[0]} a {c0['pct_pib'].iloc[-1]:.1f}% "
             f"en {c0.index[-1]} (preliminar): {c0['vab_coel_mdp'].iloc[-1] / 1e6:.2f} billones de pesos.")
    dentro = validacion["dentro_ic"].mean()
    exactas = (validacion["diferencia_pp"].abs() < 0.01).mean()
    hallazgo(c3, GRIS, f"{exactas:.0%}",
             "Nuestras estimaciones reproducen a la OECD",
             f"Las cifras nacionales calculadas aquí desde los microdatos coinciden al centésimo con las que México "
             f"reporta a la OECD en el {exactas:.0%} de los casos, y el {dentro:.0%} cae dentro del IC 90%. "
             "Es una validación externa del pipeline.")

    st.subheader(f"Las tres entidades lado a lado · {anio}")
    orden = ["hog_internet", "hog_internet_fija", "hog_computadora", "pob_smartphone", "pob_internet",
             "pob_redes_sociales", "usu_compra", "usu_paga", "usu_banca", "usu_vende"]
    d = foco[(foco["anio"] == anio) & (foco["id_indicador"].isin(orden))].copy()
    d["indicador"] = d["id_indicador"].map(nombre_ind)
    fig = go.Figure()
    etiquetas = [nombre_ind(i) for i in orden][::-1]
    for cve in FOCO:
        s = d[d["cve_ent"] == cve].set_index("id_indicador").loc[orden[::-1]]
        fig.add_trace(go.Scatter(
            x=s["estimacion"], y=etiquetas, mode="markers", name=NOMBRES[cve],
            marker=dict(size=13, color=COLOR[cve], line=dict(width=2, color="white")),
            error_x=dict(type="data", symmetric=False, array=s["ls_90"] - s["estimacion"],
                         arrayminus=s["estimacion"] - s["li_90"], color=COLOR[cve], thickness=1.5, width=0),
            customdata=np.stack([s["li_90"], s["ls_90"]], axis=-1),
            hovertemplate=f"<b>{NOMBRES[cve]}</b> · %{{y}}: %{{x:.1f}}%<br>IC 90%: %{{customdata[0]:.1f}} – "
                          "%{customdata[1]:.1f}<extra></extra>"))
    fig.update_xaxes(ticksuffix="%", range=[0, 100], showgrid=True, gridcolor="#ecebe7")
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(estilo(fig, 470), width="stretch")
    st.caption("Cada punto es la estimación; la línea horizontal es su intervalo de confianza al 90%. Compras, pagos, "
               "banca y ventas son % de los usuarios de internet; el resto, % de hogares o de la población de 6+.")


# --------------------------------------------------------------------------
# 2. Acceso
# --------------------------------------------------------------------------
with tabs[1]:
    st.markdown('<p class="nota">¿Quién tiene con qué conectarse? Hogares con internet, conexión fija y '
                'computadora, y personas con smartphone. Banda = IC 90%.</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(serie_con_ic("hog_internet"), width="stretch")
    c2.plotly_chart(serie_con_ic("hog_internet_fija"), width="stretch")
    c1, c2 = st.columns(2)
    c1.plotly_chart(serie_con_ic("hog_computadora"), width="stretch")
    c2.plotly_chart(serie_con_ic("pob_smartphone"), width="stretch")

    st.subheader(f"¿Por qué no tienen internet? · {anio}")
    razones = {"sin_internet_recursos": "Falta de recursos", "sin_internet_no_interesa": "No les interesa / no lo necesitan",
               "sin_internet_no_sabe": "No saben usarlo", "sin_internet_sin_proveedor": "No hay proveedor en su localidad"}
    d = foco[(foco["anio"] == anio) & (foco["id_indicador"].isin(razones))].copy()
    d["razón"] = d["id_indicador"].map(razones)
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.bar(d, x="estimacion", y="razón", color="entidad", barmode="group", orientation="h",
                     color_discrete_map=COLOR_NOMBRE, category_orders={"razón": list(razones.values()),
                                                                      "entidad": [NOMBRES[c] for c in FOCO]},
                     custom_data=["li_90", "ls_90", "calidad"], labels={"estimacion": "", "razón": ""})
        fig.update_traces(marker_line_color="white", marker_line_width=2, marker_cornerradius=4,
                          hovertemplate="%{y}: %{x:.1f}%<br>IC 90% %{customdata[0]:.1f}–%{customdata[1]:.1f} · "
                                        "calidad %{customdata[2]}<extra></extra>")
        fig.update_xaxes(ticksuffix="%")
        fig.update_layout(title="% de los hogares sin internet, por razón principal")
        st.plotly_chart(estilo(fig, 380), width="stretch")
    with c2:
        st.markdown("**Lectura**")
        rec = {c: valor_de(anio, c, "sin_internet_recursos") for c in FOCO}
        st.markdown(
            f"- La **falta de recursos** sigue siendo la barrera principal: {rec[YUC]:.0f}% en Yucatán, "
            f"{rec[TAB]:.0f}% en Tabasco y {rec[NAC]:.0f}% en el país.\n"
            f"- En Tabasco esa razón bajó de {valor_de(ANIOS[0], TAB, 'sin_internet_recursos'):.0f}% "
            f"({ANIOS[0]}) a {valor_de(ANIOS[-1], TAB, 'sin_internet_recursos'):.0f}% ({ANIOS[-1]}): la "
            "barrera económica se redujo.\n"
            "- **La infraestructura casi no es el problema**: menos del 5% de los hogares desconectados dice que no hay "
            "proveedor (con poca muestra: en algunos años la estimación es de calidad baja).")
        st.caption("Universo: hogares sin internet. Calidad baja = CV > 30%, usar con cautela.")


# --------------------------------------------------------------------------
# 3. Uso
# --------------------------------------------------------------------------
with tabs[2]:
    st.markdown('<p class="nota">¿Qué hacen las personas en internet? Uso general (% de la población de 6+) y '
                'economía digital de los usuarios (% de quienes usan internet).</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(serie_con_ic("pob_internet"), width="stretch")
    c2.plotly_chart(serie_con_ic("pob_redes_sociales"), width="stretch")
    c1, c2 = st.columns(2)
    c1.plotly_chart(serie_con_ic("usu_compra", "Compran por internet (% de usuarios)"), width="stretch")
    c2.plotly_chart(serie_con_ic("usu_vende", "Venden por internet (% de usuarios)"), width="stretch")
    c1, c2 = st.columns(2)
    c1.plotly_chart(serie_con_ic("usu_paga", "Pagan por internet (% de usuarios)"), width="stretch")
    c2.plotly_chart(serie_con_ic("usu_banca", "Usan banca electrónica (% de usuarios)"), width="stretch")

    st.subheader(f"¿Dónde quedan entre los 32 estados? · {anio}")
    lista = ["hog_internet", "hog_computadora", "pob_internet", "pob_smartphone", "usu_compra", "usu_paga",
             "usu_banca", "usu_vende"]
    est = encuesta[(encuesta["anio"] == anio) & (encuesta["id_indicador"].isin(lista)) & (encuesta["cve_ent"] != NAC)]
    est = est.assign(indicador=est["id_indicador"].map(nombre_ind),
                     entidad=est["cve_ent"].map(lambda c: entidades.loc[c, "nombre"]))
    fig = go.Figure()
    resto = est[~est["cve_ent"].isin([YUC, TAB])]
    fig.add_trace(go.Scatter(x=resto["estimacion"], y=resto["indicador"], mode="markers", name="Otras 30 entidades",
                             marker=dict(size=9, color=GRIS_CLARO, line=dict(width=1, color="white")),
                             customdata=resto["entidad"], hovertemplate="%{customdata}: %{x:.1f}%<extra></extra>"))
    nac = encuesta[(encuesta["anio"] == anio) & (encuesta["id_indicador"].isin(lista)) & (encuesta["cve_ent"] == NAC)]
    fig.add_trace(go.Scatter(x=nac["estimacion"], y=nac["id_indicador"].map(nombre_ind), mode="markers",
                             name="México (nacional)", marker=dict(size=16, color=COLOR[NAC], symbol="line-ns",
                                                                    line=dict(width=3, color=COLOR[NAC])),
                             hovertemplate="Nacional: %{x:.1f}%<extra></extra>"))
    for cve in [YUC, TAB]:
        s = est[est["cve_ent"] == cve].merge(
            ranking[(ranking["anio"] == anio) & (ranking["cve_ent"] == cve)][["id_indicador", "rango"]], on="id_indicador")
        fig.add_trace(go.Scatter(x=s["estimacion"], y=s["indicador"], mode="markers", name=NOMBRES[cve],
                                 marker=dict(size=14, color=COLOR[cve], line=dict(width=2, color="white")),
                                 customdata=s["rango"],
                                 hovertemplate=f"<b>{NOMBRES[cve]}</b>: %{{x:.1f}}% · lugar %{{customdata}} de 32"
                                               "<extra></extra>"))
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="#ecebe7")
    fig.update_yaxes(categoryorder="array", categoryarray=[nombre_ind(i) for i in lista][::-1])
    st.plotly_chart(estilo(fig, 440), width="stretch")

    st.subheader("Acceso y uso van juntos")
    c1, c2 = st.columns([3, 2])
    with c1:
        x, y = "hog_internet", "usu_compra"
        anch = encuesta[(encuesta["anio"] == anio) & (encuesta["id_indicador"].isin([x, y]))].pivot(
            index="cve_ent", columns="id_indicador", values="estimacion").reset_index()
        anch = anch[anch["cve_ent"] != NAC]
        anch["entidad"] = anch["cve_ent"].map(lambda c: entidades.loc[c, "nombre"])
        anch["grupo"] = anch["cve_ent"].map(lambda c: NOMBRES.get(c, "Otras entidades"))
        fig = px.scatter(anch, x=x, y=y, color="grupo", hover_name="entidad",
                         color_discrete_map={**COLOR_NOMBRE, "Otras entidades": GRIS_CLARO},
                         labels={x: nombre_ind(x) + " (%)", y: "Compran por internet (% de usuarios)"},
                         category_orders={"grupo": ["Yucatán", "Tabasco", "Otras entidades"]})
        fig.update_traces(marker=dict(size=12, line=dict(width=2, color="white")))
        b1, b0 = np.polyfit(anch[x], anch[y], 1)
        xs = np.array([anch[x].min(), anch[x].max()])
        fig.add_trace(go.Scatter(x=xs, y=b0 + b1 * xs, mode="lines", name="Tendencia (MCO)",
                                 line=dict(color=GRIS, width=1.5, dash="dot"), hoverinfo="skip"))
        fig.update_layout(title=f"32 entidades · {anio}")
        st.plotly_chart(estilo(fig, 400), width="stretch")
    with c2:
        st.markdown("Los estados con más hogares conectados también compran más en línea, todos los años. "
                    "**Yucatán está por encima de la tendencia**: en 2020–2024 compra entre 6 y 9 puntos más de "
                    "lo que su nivel de conexión anticiparía (recta de mínimos cuadrados entre las 32 entidades), "
                    "siempre entre los 4 estados más alejados hacia arriba.")
        st.caption("Asociación entre entidades, no causalidad.")


# --------------------------------------------------------------------------
# 4. Valor económico
# --------------------------------------------------------------------------
with tabs[3]:
    st.markdown('<p class="nota">El valor que la economía digital genera: peso del sector 51 (información en '
                'medios masivos: telecomunicaciones, internet, software, radio y TV) en cada entidad, y el valor '
                'agregado del comercio electrónico nacional.</p>', unsafe_allow_html=True)
    sin_mineria = st.toggle("Excluir la minería del denominador (recomendado para comparar con Tabasco)", value=True)
    col_p = "participacion_51_no_minero" if sin_mineria else "participacion_51"
    vf = valor[valor["cve_ent"].isin(FOCO)].copy()
    vf["entidad"] = vf["cve_ent"].map(NOMBRES)
    c1, c2 = st.columns(2)
    with c1:
        fig = px.line(vf, x="anio", y=col_p, color="entidad", markers=True, color_discrete_map=COLOR_NOMBRE,
                      labels={"anio": "", col_p: ""}, category_orders={"entidad": [NOMBRES[c] for c in FOCO]})
        fig.update_traces(line_width=2.4, marker=dict(size=7, line=dict(width=2, color="white")),
                          hovertemplate="%{x}: %{y:.2f}%<extra></extra>")
        fig.update_yaxes(ticksuffix="%", rangemode="tozero")
        fig.update_layout(title="Peso del sector 51 en el VAB" + (" no minero" if sin_mineria else ""))
        st.plotly_chart(estilo(fig, 360), width="stretch")
    with c2:
        base = vf[vf["anio"] == 2018].set_index("cve_ent")["vab_51_real"]
        vf["indice"] = 100 * vf["vab_51_real"] / vf["cve_ent"].map(base)
        fig = px.line(vf, x="anio", y="indice", color="entidad", markers=True, color_discrete_map=COLOR_NOMBRE,
                      labels={"anio": "", "indice": ""}, category_orders={"entidad": [NOMBRES[c] for c in FOCO]})
        fig.update_traces(line_width=2.4, marker=dict(size=7, line=dict(width=2, color="white")),
                          hovertemplate="%{x}: %{y:.1f}<extra></extra>")
        fig.add_hline(y=100, line_dash="dot", line_color=GRIS)
        fig.update_layout(title="VAB real del sector 51 (índice 2018 = 100)")
        st.plotly_chart(estilo(fig, 360), width="stretch")
    st.caption("Fuente: INEGI, PIB por entidad federativa base 2018; 2022 revisada y 2023 preliminar. "
               "La caída de 2020 es la pandemia.")

    c1, c2 = st.columns(2)
    with c1:
        partes = coel.melt(id_vars="anio", value_vars=["mayor_mdp", "menor_mdp", "otros_servicios_mdp"],
                           var_name="componente", value_name="mdp")
        partes["componente"] = partes["componente"].map({"mayor_mdp": "Comercio al por mayor",
                                                         "menor_mdp": "Comercio al por menor",
                                                         "otros_servicios_mdp": "Otros servicios"})
        partes["miles de millones"] = partes["mdp"] / 1000
        fig = px.bar(partes, x="anio", y="miles de millones", color="componente",
                     color_discrete_sequence=["#4a3aa7", "#e87ba4", "#eda100"],
                     labels={"anio": "", "miles de millones": ""})
        fig.update_traces(marker_line_color="white", marker_line_width=1.5,
                          hovertemplate="%{x} · %{fullData.name}: %{y:,.0f} mil millones<extra></extra>")
        fig.update_yaxes(ticksuffix=" mm")
        fig.update_layout(title="VAB del comercio electrónico por actividad")
        fig = estilo(fig, 400).update_layout(legend=dict(yanchor="top", y=-0.12), margin=dict(t=46, b=40))
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = go.Figure(go.Scatter(x=coel["anio"], y=coel["pct_pib"], mode="lines+markers+text",
                                   line=dict(color=COLOR[NAC], width=2.6),
                                   marker=dict(size=8, color=COLOR[NAC], line=dict(width=2, color="white")),
                                   text=[f"{v:.1f}%" if a in (coel['anio'].min(), 2019, coel['anio'].max()) else ""
                                         for a, v in zip(coel["anio"], coel["pct_pib"])],
                                   textposition="top center", hovertemplate="%{x}: %{y:.2f}% del PIB<extra></extra>"))
        fig.update_yaxes(ticksuffix="%", rangemode="tozero")
        fig.update_layout(title="Comercio electrónico como % del PIB nacional")
        st.plotly_chart(estilo(fig, 380, leyenda=False), width="stretch")
    st.caption("Fuente: INEGI, Valor Agregado Bruto del Comercio Electrónico (VABCOEL), base 2018; 2023 revisada, "
               "2024 preliminar. mm = miles de millones de pesos corrientes. Solo existe a nivel nacional: no hay cifra oficial por entidad. En 2019 el comercio "
               "al por menor salta (+133%) por la actualización de fuentes de INEGI.")


# --------------------------------------------------------------------------
# 5. Brechas y significancia
# --------------------------------------------------------------------------
with tabs[4]:
    st.markdown('<p class="nota">Diferencias en puntos porcentuales con prueba z al 90% de confianza. '
                'Solo las celdas con ● son diferencias estadísticamente significativas.</p>', unsafe_allow_html=True)
    pares = {(YUC, TAB): "Yucatán − Tabasco", (YUC, NAC): "Yucatán − México", (TAB, NAC): "Tabasco − México"}
    b = brecha[brecha["anio"] == anio].copy()
    b["par"] = [pares[(a, c)] for a, c in zip(b["entidad_a"], b["entidad_b"])]
    b["indicador"] = b["id_indicador"].map(nombre_ind)
    orden_ind = [i for i in indicadores.index if i in set(b["id_indicador"])]
    m = b.pivot(index="indicador", columns="par", values="diferencia_pp").loc[[nombre_ind(i) for i in orden_ind],
                                                                               list(pares.values())]
    sig = b.pivot(index="indicador", columns="par", values="significativa").loc[m.index, m.columns]
    texto = m.round(1).astype(str).where(~sig, m.round(1).astype(str) + " ●")
    lim = float(np.nanmax(np.abs(m.to_numpy())))
    fig = go.Figure(go.Heatmap(z=m.to_numpy(), x=m.columns, y=m.index, text=texto.to_numpy(), texttemplate="%{text}",
                               colorscale=DIVERGENTE, zmid=0, zmin=-lim, zmax=lim, xgap=3, ygap=3,
                               colorbar=dict(title="pp", thickness=10),
                               hovertemplate="%{y}<br>%{x}: %{z:.1f} pp<extra></extra>"))
    fig.update_xaxes(side="top", showline=False)
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(estilo(fig, 720, leyenda=False), width="stretch")
    st.caption("Rojo: la primera entidad está por encima; azul: por debajo. En 'sin internet por...' un valor alto es "
               "peor. La prueba contra el nacional descuenta que la entidad forma parte del total nacional.")

    st.subheader(f"Cambio {ANIOS[0]} → {ANIOS[-1]}")
    tt = tendencia.copy()
    tt["entidad"] = tt["cve_ent"].map(NOMBRES)
    tt["indicador"] = tt["id_indicador"].map(nombre_ind)
    tt = tt[tt["id_indicador"].isin(["hog_internet", "hog_internet_fija", "hog_computadora", "pob_smartphone",
                                     "pob_internet", "usu_compra", "usu_vende", "usu_paga", "usu_banca"])]
    fig = px.bar(tt, x="cambio_pp", y="indicador", color="entidad", barmode="group", orientation="h",
                 color_discrete_map=COLOR_NOMBRE, category_orders={"entidad": [NOMBRES[c] for c in FOCO]},
                 custom_data=["valor_inicial", "valor_final", "p_value"], labels={"cambio_pp": "", "indicador": ""})
    fig.update_traces(marker_line_color="white", marker_line_width=2, marker_cornerradius=3,
                      hovertemplate="%{y}: %{x:+.1f} pp<br>%{customdata[0]:.1f}% → %{customdata[1]:.1f}% · "
                                    "p = %{customdata[2]:.3f}<extra></extra>")
    fig.add_vline(x=0, line_color="#c3c2b7")
    fig.update_xaxes(ticksuffix=" pp")
    fig.update_layout(title="Cambio en puntos porcentuales")
    st.plotly_chart(estilo(fig, 520), width="stretch")
    no_sig = tt[~tt["significativo"]]
    if len(no_sig):
        st.caption("Cambios no significativos al 90%: " + "; ".join(
            f"{r.entidad} · {r.indicador} ({round(r.cambio_pp, 1) + 0.0:+.1f} pp)" for r in no_sig.itertuples()) + ".")


# --------------------------------------------------------------------------
# 6. Contexto internacional
# --------------------------------------------------------------------------
with tabs[5]:
    oecd = api("/oecd")
    medidas = (oecd[["medida", "desc_medida"]].drop_duplicates().set_index("medida")["desc_medida"]
               .str.replace(" - last 3 m", " (últimos 3 meses)").str.replace(" - last 12 m", " (últimos 12 meses)"))
    c1, c2 = st.columns([2, 1])
    medida = c1.selectbox("Medida OECD", list(medidas.index), index=list(medidas.index).index("C5B_I"),
                          format_func=lambda m: f"{m} · {medidas[m]}")
    # Solo años en que México reporta la medida (OECD publica antes a los países europeos)
    anios_m = sorted(oecd.loc[(oecd["medida"] == medida) & (oecd["cod_pais"] == "MEX"), "anio"].unique())
    anio_o = c2.selectbox("Año (con dato de México)", anios_m[::-1])
    o = oecd[(oecd["medida"] == medida) & (oecd["anio"] == anio_o)].sort_values("valor")
    o["grupo"] = np.select([o["cod_pais"] == "MEX", o["cod_pais"].isin(AGREGADOS_OECD)],
                           ["México", "Promedio OECD / UE"], "Otros países")
    fig = px.bar(o, x="valor", y="pais", orientation="h", color="grupo",
                 color_discrete_map={"México": COLOR[NAC], "Promedio OECD / UE": TINTA_2, "Otros países": GRIS_CLARO},
                 labels={"valor": "", "pais": ""}, custom_data=["estatus_obs"])
    fig.update_traces(marker_cornerradius=3, hovertemplate="%{y}: %{x:.1f}%<br>%{customdata[0]}<extra></extra>")
    fig.update_xaxes(ticksuffix="%")
    fig.update_yaxes(categoryorder="array", categoryarray=list(o["pais"]))  # por valor, no por grupo
    fig.update_layout(title=f"{medidas[medida]} · {anio_o}", bargap=0.25)
    st.plotly_chart(estilo(fig, max(420, 19 * len(o))), width="stretch")
    pos = o.sort_values("valor", ascending=False).reset_index(drop=True)
    paises = pos[~pos["cod_pais"].isin(AGREGADOS_OECD)].reset_index(drop=True)
    if "MEX" in set(paises["cod_pais"]):
        lugar = int(paises.index[paises["cod_pais"] == "MEX"][0]) + 1
        st.caption(f"México ocupa el lugar {lugar} de {len(paises)} países con dato. Hogares: % de hogares; "
                   "personas: % de la población de 16 a 74 años.")

    st.subheader("Validación: ENDUTIH (este pipeline) vs cifras de México en OECD")
    v = validacion.copy()
    v["diferencia_pp"] = v["diferencia_pp"].round(2) + 0.0  # evita '-0.00' 
    v["medida"] = v["medida_oecd"] + " · " + v["medida_oecd"].map(medidas)
    fig = go.Figure()
    vv = v[v["anio"] == v["anio"].max()]
    fig.add_trace(go.Scatter(x=vv["valor_oecd"], y=vv["medida"], mode="markers", name="OECD (MEX)",
                             marker=dict(size=16, color="white", line=dict(width=2.5, color=TINTA_2)),
                             hovertemplate="OECD: %{x:.2f}%<extra></extra>"))
    fig.add_trace(go.Scatter(x=vv["valor_endutih"], y=vv["medida"], mode="markers", name="ENDUTIH (este pipeline)",
                             marker=dict(size=8, color=COLOR[NAC]),
                             error_x=dict(type="data", symmetric=False, array=vv["ls_90"] - vv["valor_endutih"],
                                          arrayminus=vv["valor_endutih"] - vv["li_90"], color=COLOR[NAC], width=6),
                             hovertemplate="ENDUTIH: %{x:.2f}%<extra></extra>"))
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="#ecebe7")
    fig.update_layout(title=f"{int(vv['anio'].iloc[0])}: el punto verde (nuestro) cae dentro del círculo (OECD)")
    st.plotly_chart(estilo(fig, 380), width="stretch")
    st.dataframe(v[["anio", "medida", "valor_oecd", "valor_endutih", "diferencia_pp", "dentro_ic"]].rename(columns={
        "anio": "Año", "medida": "Medida", "valor_oecd": "OECD", "valor_endutih": "ENDUTIH",
        "diferencia_pp": "Diferencia (pp)", "dentro_ic": "Dentro del IC 90%"}),
        hide_index=True, width="stretch",
        column_config={c: st.column_config.NumberColumn(format="%.2f") for c in ["OECD", "ENDUTIH", "Diferencia (pp)"]})
    st.caption("Personas: población de 16 a 74 años (definición OECD), recalculada desde los microdatos. La única "
               "diferencia es internet fijo (B21A_HH, ~0.2–0.4 pp): aquí se excluye del denominador a los hogares "
               "que no saben qué tipo de conexión tienen.")


# --------------------------------------------------------------------------
# 7. Calidad de datos
# --------------------------------------------------------------------------
with tabs[6]:
    st.subheader("Decisiones de limpieza (última corrida de silver)")
    dec = api("/calidad/decisiones")
    st.dataframe(dec[["tabla", "metrica", "valor", "detalle"]].rename(columns={
        "tabla": "Tabla", "metrica": "Decisión / métrica", "valor": "Registros", "detalle": "Detalle"}),
        hide_index=True, width="stretch", height=420)
    st.caption("El catálogo completo de decisiones (D01–D17) con su justificación está en docs/decisiones_limpieza.md.")

    st.subheader("Calidad de las estimaciones")
    cal = encuesta[encuesta["cve_ent"].isin(FOCO)].groupby(["cve_ent", "calidad"]).size().unstack(fill_value=0)
    cal.index = cal.index.map(NOMBRES)
    st.dataframe(cal.reindex(columns=["alta", "moderada", "baja"], fill_value=0), width="stretch")
    baja = encuesta[(encuesta["cve_ent"].isin(FOCO)) & (encuesta["calidad"] != "alta")].assign(
        entidad=lambda d: d["cve_ent"].map(NOMBRES), indicador=lambda d: d["id_indicador"].map(nombre_ind))
    st.dataframe(baja[["anio", "entidad", "indicador", "estimacion", "cv", "calidad", "n_muestra"]].sort_values(
        ["calidad", "anio"]), hide_index=True, width="stretch",
        column_config={"estimacion": st.column_config.NumberColumn("Estimación (%)", format="%.1f"),
                       "cv": st.column_config.NumberColumn("CV (%)", format="%.1f")})

    st.subheader("Armonización de preguntas de la ENDUTIH entre años")
    mapeo = api("/calidad/mapeo-variables")
    st.dataframe(mapeo, hide_index=True, width="stretch", height=360)
    st.caption("Cada columna se validó contra el texto del diccionario de datos de INEGI: si INEGI renumera una "
               "pregunta, el pipeline se detiene en lugar de mezclar preguntas distintas.")

    st.subheader("Última carga de gold")
    st.dataframe(api("/etl-log"), hide_index=True, width="stretch")
