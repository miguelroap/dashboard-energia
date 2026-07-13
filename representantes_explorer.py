# -*- coding: utf-8 -*-
"""
representantes_explorer.py — Análisis de ofertas de representantes  (v3)
=========================================================================

Rediseño centrado en LA CURVA DE OFERTA como objeto de estudio, con tres
niveles de agregación conmutables sobre las mismas vistas:

    Representante  ·  Tecnología  ·  UP

Vistas:
  1. CURVA DE MÉRITO — precio vs MW acumulado (escalera pay-as-bid real).
     Cada grupo (rep/tech/UP) apila sus bloques ordenados por precio.
     Toggle de normalización: MW absolutos o % de capacidad instalada
     (para comparar agentes de tamaños muy distintos).
  2. PRECIO POR TECNOLOGÍA — distribución (box) del precio ponderado de
     cada UP, agrupado por tecnología y coloreado por representante:
     quién oferta agresivo DENTRO de la misma tecnología.
  3. TABLA POR UP — una fila por UP: agente, tecnología, capacidad,
     MW medio ofertado, precio ponderado, rango, cobertura del período
     y PRIMA vs la mediana de su tecnología (positiva = más caro).
  4. EVOLUCIÓN — precio ponderado y MW diarios por grupo.
  5. LECTURA IA — export estructurado para pegar en un chat (patrón B),
     con hook de API preparado (patrón A).

Datos: tablas BigQuery `i90_diaXX_*offer*_raw` (pieza ofertas-fetch-data)
+ maestro de UPs (programming_units_external_table_latest) para Tech,
Power_MW y Sujeto del Mercado.

Mercados de Participante (banda/energía secundaria): la ENTITY es el código
PM, no la UP, así que los niveles Tecnología/UP no aplican y el módulo
fuerza nivel Representante con aviso.

Integración en app.py: IDÉNTICA a v2 (set_bq + set_helpers +
render_representantes). No hay que tocar nada.
"""

import datetime as dt
from textwrap import dedent

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# ==============================================================================
# CATÁLOGO DE MERCADOS
# ==============================================================================
MARKETS = {
    "rrtt_pdbf_sub": dict(
        label_es="RRTT PDBF · Subir", label_en="RRTT PDBF · Up",
        entity="UP", interleaved=False, side="Subir", price_unit="€/MWh",
        mw_table="i90_dia17_rrtt_pdbf_offer_up_mw_raw",
        pr_table="i90_dia22_rrtt_pdbf_offer_up_price_raw"),
    "rrtt_pdbf_baj": dict(
        label_es="RRTT PDBF · Bajar", label_en="RRTT PDBF · Down",
        entity="UP", interleaved=False, side="Bajar", price_unit="€/MWh",
        mw_table="i90_dia41_rrtt_pdbf_offer_dn_mw_raw",
        pr_table="i90_dia23_rrtt_pdbf_offer_dn_price_raw"),
    "rrtt_tr_sub": dict(
        label_es="RRTT TR (RT5) · Subir", label_en="RRTT TR (RT5) · Up",
        entity="UP", interleaved=False, side="Subir", price_unit="€/MWh",
        mw_table="i90_dia32_rrtt_tr_offer_up_mw_raw",
        pr_table="i90_dia31_rrtt_tr_offer_up_price_raw"),
    "rrtt_tr_baj": dict(
        label_es="RRTT TR (RT5) · Bajar", label_en="RRTT TR (RT5) · Down",
        entity="UP", interleaved=False, side="Bajar", price_unit="€/MWh",
        mw_table="i90_dia42_rrtt_tr_offer_dn_mw_raw",
        pr_table="i90_dia24_rrtt_tr_offer_dn_price_raw"),
    "terciaria": dict(
        label_es="Terciaria / mFRR", label_en="Tertiary / mFRR",
        entity="UP", interleaved=True, side=None, price_unit="€/MWh",
        mw_table="i90_dia15_tertiary_offer_raw",
        pr_table="i90_dia15_tertiary_offer_raw"),
    "banda_sec": dict(
        label_es="Banda secundaria", label_en="Secondary band",
        entity="PM", interleaved=True, side=None, price_unit="€/MW",
        mw_table="i90_dia13_secondary_band_offer_raw",
        pr_table="i90_dia13_secondary_band_offer_raw"),
    "energia_sec": dict(
        label_es="Energía secundaria", label_en="Secondary energy",
        entity="PM", interleaved=True, side=None, price_unit="€/MWh",
        mw_table="i90_dia38_secondary_energy_offer_raw",
        pr_table="i90_dia38_secondary_energy_offer_raw"),
}

_SS_KEY = "repofertas_v3"

# ==============================================================================
# INYECCIÓN DE DEPENDENCIAS (idéntica a v2)
# ==============================================================================
_BQ, _HELPERS = {}, {}


def set_bq(client=None, project="miguel-energia", dataset="red_electrica_data"):
    _BQ["client"] = client
    _BQ["project"] = project
    _BQ["dataset"] = dataset


def set_helpers(metric_card=None, section_header=None, base_layout=None, t=None):
    if metric_card:     _HELPERS["metric_card"] = metric_card
    if section_header:  _HELPERS["section_header"] = section_header
    if base_layout:     _HELPERS["base_layout"] = base_layout
    if t:               _HELPERS["t"] = t


def _t(en, es):
    fn = _HELPERS.get("t")
    return fn(en, es) if fn else es


def _section(icon, title):
    fn = _HELPERS.get("section_header")
    if fn:
        fn(icon, title)
    else:
        st.markdown(f"### {icon} {title}")


def _layout(**extra):
    fn = _HELPERS.get("base_layout")
    if fn:
        return fn(**extra)
    base = dict(template="plotly_white", paper_bgcolor="#ffffff",
                plot_bgcolor="#FBFCFE",
                font=dict(family="Inter, sans-serif", color="#46556B", size=12),
                margin=dict(l=10, r=10, t=45, b=10))
    base.update(extra)
    return base


def _mkt_label(mkt):
    return _t(mkt["label_en"], mkt["label_es"])


# ==============================================================================
# BIGQUERY
# ==============================================================================
@st.cache_resource(show_spinner=False)
def _build_bq_client(project):
    from google.cloud import bigquery
    from google.oauth2 import service_account
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(project=project, credentials=creds)


def _client():
    c = _BQ.get("client")
    if c is None:
        c = _build_bq_client(_BQ.get("project", "miguel-energia"))
        _BQ["client"] = c
    return c


def _qp(d_ini, d_fin):
    from google.cloud import bigquery
    return bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
        bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin)])


@st.cache_data(ttl=3600, show_spinner=False)
def _load_up_master():
    project, dataset = _BQ["project"], _BQ["dataset"]
    sql = f"""
        SELECT UP, Power_MW, Tech,
               Sujeto_del_Mercado   AS SM,
               Sujeto_del_Mercado_2 AS SM2, RZ
        FROM `{project}.{dataset}.programming_units_external_table_latest`
    """
    df = _client().query(sql).to_dataframe()
    df["Power_MW"] = pd.to_numeric(df["Power_MW"], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def _data_availability(table):
    project, dataset = _BQ["project"], _BQ["dataset"]
    sql = f"""SELECT MIN(DELIVERY_DATE_DAY_CET) AS dmin,
                     MAX(DELIVERY_DATE_DAY_CET) AS dmax
              FROM `{project}.{dataset}.{table}`"""
    df = _client().query(sql).to_dataframe()
    if df.empty or pd.isna(df.loc[0, "dmax"]):
        return None, None
    return (pd.to_datetime(df.loc[0, "dmin"]).date(),
            pd.to_datetime(df.loc[0, "dmax"]).date())


def _q_blocks(mkt, entities, d_ini, d_fin):
    """Agregado del período por (ENTITY, BLOCK)."""
    project, dataset = _BQ["project"], _BQ["dataset"]
    ent_list = ",".join(f"'{e}'" for e in entities)
    if mkt["interleaved"]:
        sql = f"""
        SELECT ENTITY, BLOCK,
               SUM(VALUE_MW) AS mw_sum,
               SAFE_DIVIDE(SUM(VALUE_MW * VALUE_EUR), SUM(VALUE_MW)) AS pr_w,
               MIN(VALUE_EUR) AS pr_min, MAX(VALUE_EUR) AS pr_max,
               COUNT(VALUE_MW) AS qh_count,
               COUNT(DISTINCT DELIVERY_DATE_DAY_CET) AS days
        FROM `{project}.{dataset}.{mkt['mw_table']}`
        WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
          AND ENTITY IN ({ent_list}) AND VALUE_MW IS NOT NULL
        GROUP BY ENTITY, BLOCK"""
    else:
        # Las tablas simples son ya direccionales (dia32=Subir, dia42=Bajar…).
        # OFFER_SIDE contiene 'Venta'/'Compra', no 'Subir'/'Bajar':
        # filtrar por él dejaría 0 filas. Se omite.
        sql = f"""
        WITH mw AS (
          SELECT ENTITY, BLOCK, SUM(VALUE_MW) AS mw_sum,
                 COUNT(VALUE_MW) AS qh_count,
                 COUNT(DISTINCT DELIVERY_DATE_DAY_CET) AS days
          FROM `{project}.{dataset}.{mkt['mw_table']}`
          WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
            AND ENTITY IN ({ent_list}) AND VALUE_MW IS NOT NULL
          GROUP BY ENTITY, BLOCK),
        pr AS (
          SELECT ENTITY, BLOCK, AVG(VALUE_EUR) AS pr_w,
                 MIN(VALUE_EUR) AS pr_min, MAX(VALUE_EUR) AS pr_max
          FROM `{project}.{dataset}.{mkt['pr_table']}`
          WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
            AND ENTITY IN ({ent_list}) AND VALUE_EUR IS NOT NULL
          GROUP BY ENTITY, BLOCK)
        SELECT mw.ENTITY, mw.BLOCK, mw.mw_sum, mw.qh_count, mw.days,
               pr.pr_w, pr.pr_min, pr.pr_max
        FROM mw LEFT JOIN pr USING (ENTITY, BLOCK)"""
    return _client().query(sql, job_config=_qp(d_ini, d_fin)).to_dataframe()


def _q_evolution(mkt, entities, d_ini, d_fin):
    project, dataset = _BQ["project"], _BQ["dataset"]
    ent_list = ",".join(f"'{e}'" for e in entities)
    if mkt["interleaved"]:
        sql = f"""
        SELECT DELIVERY_DATE_DAY_CET AS d, ENTITY,
               SUM(VALUE_MW) AS mw_sum,
               SAFE_DIVIDE(SUM(VALUE_MW * VALUE_EUR), SUM(VALUE_MW)) AS pr_w
        FROM `{project}.{dataset}.{mkt['mw_table']}`
        WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
          AND ENTITY IN ({ent_list}) AND VALUE_MW IS NOT NULL
        GROUP BY d, ENTITY"""
    else:
        sql = f"""
        WITH mw AS (
          SELECT DELIVERY_DATE_DAY_CET AS d, ENTITY, SUM(VALUE_MW) AS mw_sum
          FROM `{project}.{dataset}.{mkt['mw_table']}`
          WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
            AND ENTITY IN ({ent_list}) AND VALUE_MW IS NOT NULL
          GROUP BY d, ENTITY),
        pr AS (
          SELECT DELIVERY_DATE_DAY_CET AS d, ENTITY, AVG(VALUE_EUR) AS pr_w
          FROM `{project}.{dataset}.{mkt['pr_table']}`
          WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
            AND ENTITY IN ({ent_list}) AND VALUE_EUR IS NOT NULL
          GROUP BY d, ENTITY)
        SELECT mw.d, mw.ENTITY, mw.mw_sum, pr.pr_w
        FROM mw LEFT JOIN pr USING (d, ENTITY)"""
    return _client().query(sql, job_config=_qp(d_ini, d_fin)).to_dataframe()


# ==============================================================================
# TRANSFORMACIONES (puras: testables sin Streamlit)
# ==============================================================================
def enrich_blocks(df_blocks, master, entity_kind):
    """Añade SM, Tech, Power_MW y mw_avg (MW medio por QH) a cada bloque."""
    if df_blocks is None or df_blocks.empty:
        return pd.DataFrame()
    df = df_blocks.copy()
    df["mw_avg"] = df["mw_sum"] / df["qh_count"].replace(0, pd.NA)
    if entity_kind == "UP":
        m = master[["UP", "SM", "Tech", "Power_MW"]].drop_duplicates("UP")
        df = df.merge(m, left_on="ENTITY", right_on="UP", how="left")
        df["SM"] = df["SM"].fillna(df["ENTITY"])
        df["Tech"] = df["Tech"].fillna("(sin tech)")
    else:  # PM: ENTITY es el código de participante; sin desglose UP/Tech
        df["UP"] = df["ENTITY"]
        df["SM"] = df["ENTITY"]
        df["Tech"] = "(PM)"
        df["Power_MW"] = pd.NA
    return df


def up_metrics(dfb, period_days):
    """Una fila por UP: precio pond., MW medio, cobertura, prima vs tech."""
    if dfb.empty:
        return pd.DataFrame()
    rows = []
    for up, g in dfb.groupby("UP"):
        v = g.dropna(subset=["pr_w"])
        wsum = v["mw_sum"].sum()
        pr = float((v["pr_w"] * v["mw_sum"]).sum() / wsum) if wsum > 0 else (
            float(v["pr_w"].mean()) if not v.empty else None)
        qh_offer = int(g["qh_count"].max())          # bloque 1 ≈ QH con oferta
        rows.append(dict(
            UP=up, SM=g["SM"].iloc[0], Tech=g["Tech"].iloc[0],
            Power_MW=float(g["Power_MW"].iloc[0]) if pd.notna(g["Power_MW"].iloc[0]) else None,
            mw_avg=float(g["mw_avg"].sum()) if g["mw_avg"].notna().any() else 0.0,
            pr_w=pr,
            pr_min=float(g["pr_min"].min()) if g["pr_min"].notna().any() else None,
            pr_max=float(g["pr_max"].max()) if g["pr_max"].notna().any() else None,
            blocks=int(g["BLOCK"].nunique()),
            cobertura=min(1.0, qh_offer / max(1, period_days * 96)),
        ))
    out = pd.DataFrame(rows)
    # prima vs mediana de su tecnología (entre TODO lo seleccionado)
    med = out.groupby("Tech")["pr_w"].transform("median")
    out["prima_tech"] = out["pr_w"] - med
    return out.sort_values("mw_avg", ascending=False).reset_index(drop=True)


def merit_curve(dfb, level):
    """Puntos de curva de mérito por grupo: bloques ordenados por precio,
    MW medio acumulado. level ∈ {'SM','Tech','UP'}."""
    if dfb.empty:
        return pd.DataFrame()
    d = dfb.dropna(subset=["pr_w", "mw_avg"]).copy()
    parts = []
    for grp, g in d.groupby(level):
        g = g.sort_values("pr_w")
        cum = g["mw_avg"].cumsum()
        parts.append(pd.DataFrame({
            "grupo": grp, "mw_cum": cum.values, "precio": g["pr_w"].values}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def group_capacity(dfb, level):
    """Capacidad instalada (Σ Power_MW de UPs únicas) por grupo."""
    caps = (dfb[[level, "UP", "Power_MW"]].drop_duplicates(["UP"])
            .groupby(level)["Power_MW"].sum(min_count=1))
    return caps.to_dict()


def _wgroup(df, keys):
    mw = df.groupby(keys)["mw_sum"].sum().rename("mw")
    v = df.dropna(subset=["pr_w"]).copy()
    if v.empty:
        out = mw.reset_index()
        out["pr_w"] = pd.NA
        return out
    v["_pv"] = v["pr_w"] * v["mw_sum"]
    num = v.groupby(keys)["_pv"].sum()
    den = v.groupby(keys)["mw_sum"].sum()
    pr = (num / den.where(den > 0)).rename("pr_w")
    return pd.concat([mw, pr], axis=1).reset_index()


def evolution_by_level(df_evo, ent_meta, level):
    """Serie diaria agregada al nivel elegido."""
    if df_evo is None or df_evo.empty:
        return pd.DataFrame()
    df = df_evo.merge(ent_meta, left_on="ENTITY", right_on="UP", how="left")
    df["SM"] = df["SM"].fillna(df["ENTITY"])
    df["Tech"] = df["Tech"].fillna("(sin tech)")
    if "UP" not in df.columns or df["UP"].isna().all():
        df["UP"] = df["ENTITY"]
    df["UP"] = df["UP"].fillna(df["ENTITY"])
    out = _wgroup(df, ["d", level]).rename(columns={level: "grupo"})
    out["d"] = pd.to_datetime(out["d"])
    return out.sort_values("d")


# ==============================================================================
# PAYLOAD IA
# ==============================================================================
def _build_payload(ups, mkt, d_ini, d_fin, reps_sel):
    tabla = (ups.round(2)
             .rename(columns={"mw_avg": "MW_medio", "pr_w": "precio_pond",
                              "prima_tech": "prima_vs_mediana_tech",
                              "cobertura": "cobertura_periodo"})
             .to_dict(orient="records"))
    return {
        "mercado": mkt["label_es"], "unidad_precio": mkt["price_unit"],
        "periodo": {"inicio": str(d_ini), "fin": str(d_fin)},
        "representantes": list(reps_sel),
        "nota": ("precio_pond = €/MWh ponderado por MW. MW_medio = MW medios "
                 "ofertados por QH. prima_vs_mediana_tech = cuánto más caro (+) "
                 "o barato (−) oferta esa UP que la mediana de su tecnología. "
                 "cobertura_periodo = fracción de cuartos de hora con oferta."),
        "tabla_por_UP": tabla,
    }


def _payload_md(p):
    md = ["# Ofertas de representantes — análisis por UP",
          f"**Mercado:** {p['mercado']} · **Período:** "
          f"{p['periodo']['inicio']} → {p['periodo']['fin']} · "
          f"**Precio en:** {p['unidad_precio']}", "", f"_{p['nota']}_", ""]
    rows = p["tabla_por_UP"]
    if rows:
        cols = list(rows[0].keys())
        md.append("| " + " | ".join(cols) + " |")
        md.append("| " + " | ".join("---" for _ in cols) + " |")
        md += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    md.append("")
    md.append(dedent("""\
        ---
        **Pregunta:** Con esta tabla por UP del mercado de balancing español:
        1. ¿Qué UPs ofertan sistemáticamente por encima de su tecnología
           (prima positiva alta) y qué puede explicarlo (zona, tamaño, agente)?
        2. ¿Qué representantes son agresivos en unas tecnologías y
           conservadores en otras?
        3. ¿La cobertura del período sugiere estrategias de disponibilidad
           distintas entre agentes?
        4. Señales de poder de mercado o zonas poco competidas.
        5. Qué mirarías después para confirmar cada hipótesis."""))
    return "\n".join(md)


# === API HOOK === (patrón A)
def _call_claude(payload):
    import anthropic
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-8", max_tokens=1500,
        messages=[{"role": "user", "content": _payload_md(payload)}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


# ==============================================================================
# GRÁFICOS
# ==============================================================================
def _fig_merit(curve, mkt, caps=None, normalize=False):
    if curve.empty:
        return None
    fig = go.Figure()
    for grp, g in curve.groupby("grupo"):
        x = g["mw_cum"]
        xlab = "MW acumulados"
        if normalize and caps and caps.get(grp) and caps[grp] > 0:
            x = 100 * g["mw_cum"] / caps[grp]
            xlab = _t("% of installed capacity", "% de capacidad instalada")
        fig.add_scatter(x=[0] + list(x), y=[g["precio"].iloc[0]] + list(g["precio"]),
                        mode="lines+markers", name=str(grp),
                        line_shape="hv", marker=dict(size=5))
    fig.update_layout(**_layout(
        height=480,
        title=_t("Merit-order offer curve", "Curva de mérito de la oferta")
              + f" — {_mkt_label(mkt)}",
        xaxis_title=xlab if not curve.empty else "MW",
        yaxis_title=mkt["price_unit"],
        legend=dict(orientation="h", y=1.1)))
    return fig


def _fig_tech_box(ups, mkt):
    d = ups.dropna(subset=["pr_w"])
    if d.empty:
        return None
    fig = px.box(d, x="Tech", y="pr_w", color="SM", points="all",
                 hover_data=["UP", "mw_avg"],
                 labels={"pr_w": mkt["price_unit"], "Tech": "", "SM": ""})
    fig.update_layout(**_layout(
        height=460,
        title=_t("UP weighted price by technology and agent",
                 "Precio ponderado de cada UP por tecnología y agente"),
        legend=dict(orientation="h", y=1.1)))
    return fig


def _fig_evo(evo, mkt, what="pr_w"):
    if evo.empty or evo[what].isna().all():
        return None
    fig = px.line(evo, x="d", y=what, color="grupo", markers=True,
                  labels={"d": "", "grupo": "",
                          what: mkt["price_unit"] if what == "pr_w" else "MW"})
    fig.update_layout(**_layout(
        height=400,
        title=(_t("Daily weighted price", "Precio ponderado diario")
               if what == "pr_w" else _t("Daily offered MW", "MW ofertados diarios")),
        legend=dict(orientation="h", y=1.12)))
    return fig


# ==============================================================================
# RENDER
# ==============================================================================
def render_representantes(start_date=None, end_date=None, pm_map=None):
    _section("🏛️", _t("Agent Offers Analysis", "Análisis de Ofertas de Representantes"))
    st.caption(_t(
        "The offer curve is the object of study: merit-order view, per-technology "
        "price distributions and a per-UP table, switchable across three levels.",
        "La curva de oferta es el objeto de estudio: curva de mérito, distribución "
        "de precios por tecnología y tabla por UP, conmutables en tres niveles."))

    try:
        master = _load_up_master()
    except Exception as e:
        st.error(_t("Could not load UP master: ", "No se pudo cargar el maestro: ") + str(e))
        return
    sm_options = sorted(master["SM"].dropna().unique().tolist())

    # ── Controles ────────────────────────────────────────────────────
    c1, c2 = st.columns([2, 1])
    with c1:
        reps_sel = st.multiselect(
            _t("Agents", "Representantes"), sm_options,
            default=sm_options[:2] if len(sm_options) >= 2 else sm_options,
            key="r3_sel")
    with c2:
        mkt_key = st.selectbox(_t("Market", "Mercado"), list(MARKETS.keys()),
                               format_func=lambda k: _mkt_label(MARKETS[k]),
                               key="r3_mkt")
    mkt = MARKETS[mkt_key]
    is_pm = mkt["entity"] == "PM"

    try:
        dmin, dmax = _data_availability(mkt["mw_table"])
    except Exception as e:
        st.error(str(e))
        return
    if dmax is None:
        st.warning(_t("Empty table for this market.", "Tabla vacía para este mercado."))
        return
    st.info(f"📅 {_t('Data available', 'Datos disponibles')}: **{dmin} → {dmax}** (I90 = D+90)")

    c3, c4, c5 = st.columns([1, 1, 1])
    with c3:
        d_ini = st.date_input(_t("From", "Desde"), value=max(dmin, dmax - dt.timedelta(days=6)),
                              min_value=dmin, max_value=dmax, key=f"r3_dini_{mkt_key}")
    with c4:
        d_fin = st.date_input(_t("To", "Hasta"), value=dmax,
                              min_value=dmin, max_value=dmax, key=f"r3_dfin_{mkt_key}")
    with c5:
        if is_pm:
            level = "SM"
            st.selectbox(_t("Level", "Nivel"), [_t("Agent", "Representante")],
                         key="r3_lvl_pm", disabled=True,
                         help=_t("Participant markets have no UP/Tech breakdown.",
                                 "Los mercados de Participante no desglosan por UP/Tecnología."))
        else:
            lvl_map = {_t("Agent", "Representante"): "SM",
                       _t("Technology", "Tecnología"): "Tech", "UP": "UP"}
            level = lvl_map[st.selectbox(_t("Level", "Nivel"), list(lvl_map.keys()),
                                         key="r3_lvl")]

    # filtro de tecnología (solo mercados UP)
    tech_sel = None
    if not is_pm:
        techs = sorted(master.loc[master["SM"].isin(reps_sel), "Tech"]
                       .dropna().unique().tolist())
        tech_sel = st.multiselect(_t("Technologies (empty = all)",
                                     "Tecnologías (vacío = todas)"),
                                  techs, default=[], key="r3_tech")

    if not reps_sel:
        st.info(_t("Select at least one agent.", "Selecciona al menos un representante."))
        return
    if d_ini > d_fin:
        st.error(_t("Inverted date range.", "Rango de fechas invertido."))
        return

    # ── Resolver entidades ───────────────────────────────────────────
    if not is_pm:
        sub = master[master["SM"].isin(reps_sel)]
        if tech_sel:
            sub = sub[sub["Tech"].isin(tech_sel)]
        entities = sorted(sub["UP"].dropna().unique().tolist())
    else:
        entities = []
        for sm in reps_sel:
            code = (pm_map or {}).get(sm)
            if not code:
                sm2s = master.loc[master["SM"] == sm, "SM2"].dropna()
                code = sm2s.mode().iloc[0] if not sm2s.empty else sm
            entities.append(code)
        entities = sorted(set(entities))
        if not pm_map:
            st.warning(_t("PM market without pm_map: using SM2 (may be wrong).",
                          "Mercado PM sin pm_map: uso SM2 (puede no casar)."))
    if not entities:
        st.error(_t("No entities for that selection.", "Sin entidades para esa selección."))
        return

    if st.button(_t("Analyze offers", "Analizar ofertas"), type="primary"):
        with st.spinner("BigQuery…"):
            try:
                dfb_raw = _q_blocks(mkt, entities, d_ini, d_fin)
                dfe_raw = _q_evolution(mkt, entities, d_ini, d_fin)
            except Exception as e:
                st.error(str(e))
                return
        st.session_state[_SS_KEY] = dict(
            mkt_key=mkt_key, reps=list(reps_sel), tech=list(tech_sel or []),
            d_ini=str(d_ini), d_fin=str(d_fin),
            dfb=dfb_raw, dfe=dfe_raw)

    res = st.session_state.get(_SS_KEY)
    if not res:
        return
    if (res["mkt_key"], res["reps"], res["d_ini"], res["d_fin"], res["tech"]) != \
       (mkt_key, list(reps_sel), str(d_ini), str(d_fin), list(tech_sel or [])):
        st.caption(_t("⚠️ Showing previous run — press *Analyze offers* to refresh.",
                      "⚠️ Mostrando la ejecución anterior — pulsa *Analizar ofertas* para refrescar."))

    r_mkt = MARKETS[res["mkt_key"]]
    dfb = enrich_blocks(res["dfb"], master, r_mkt["entity"])
    if dfb.empty:
        st.warning(_t("No offer data for that selection/period.",
                      "Sin datos de oferta para esa selección y período."))
        return
    period_days = (pd.to_datetime(res["d_fin"]) - pd.to_datetime(res["d_ini"])).days + 1
    ups = up_metrics(dfb, period_days)

    # ── Vistas ────────────────────────────────────────────────────────
    tab_merit, tab_tech, tab_ups, tab_evo, tab_ai = st.tabs([
        _t("⚡ Merit curve", "⚡ Curva de mérito"),
        _t("🔬 By technology", "🔬 Por tecnología"),
        _t("📋 Per UP", "📋 Por UP"),
        _t("📈 Evolution", "📈 Evolución"),
        _t("🤖 AI reading", "🤖 Lectura IA")])

    with tab_merit:
        st.caption(_t(
            "Each group stacks its blocks sorted by price: the real pay-as-bid "
            "supply curve. Normalize by installed capacity to compare sizes.",
            "Cada grupo apila sus bloques ordenados por precio: la curva de oferta "
            "pay-as-bid real. Normaliza por capacidad instalada para comparar tamaños."))
        normalize = False
        if not r_mkt["entity"] == "PM":
            normalize = st.toggle(
                _t("Normalize by installed capacity (%)",
                   "Normalizar por capacidad instalada (%)"), key="r3_norm")
        curve = merit_curve(dfb, level)
        caps = group_capacity(dfb, level) if normalize else None
        f = _fig_merit(curve, r_mkt, caps=caps, normalize=normalize)
        if f:
            st.plotly_chart(f, use_container_width=True)
        else:
            st.caption(_t("No priced blocks.", "Sin bloques con precio."))

    with tab_tech:
        if r_mkt["entity"] == "PM":
            st.info(_t("Not available for Participant markets.",
                       "No disponible en mercados de Participante."))
        else:
            st.caption(_t(
                "Each point is one UP (its MW-weighted price). Boxes show the "
                "spread per technology; colors separate agents: who bids "
                "aggressively WITHIN the same technology.",
                "Cada punto es una UP (su precio ponderado por MW). Las cajas "
                "muestran la dispersión por tecnología; el color separa agentes: "
                "quién oferta agresivo DENTRO de la misma tecnología."))
            f = _fig_tech_box(ups, r_mkt)
            if f:
                st.plotly_chart(f, use_container_width=True)

    with tab_ups:
        st.caption(_t(
            "One row per UP. 'Prima vs tech' = how much above (+) or below (−) "
            "the median of its technology this UP bids.",
            "Una fila por UP. 'Prima vs tech' = cuánto por encima (+) o por "
            "debajo (−) de la mediana de su tecnología oferta esta UP."))
        show = ups.rename(columns={
            "SM": _t("Agent", "Representante"), "Tech": _t("Technology", "Tecnología"),
            "Power_MW": "MW inst.", "mw_avg": _t("Avg MW offered", "MW medio ofertado"),
            "pr_w": f"{_t('W.avg price', 'Precio pond.')} ({r_mkt['price_unit']})",
            "pr_min": _t("Min", "Mín"), "pr_max": _t("Max", "Máx"),
            "blocks": _t("Blocks", "Bloques"),
            "cobertura": _t("Coverage", "Cobertura"),
            "prima_tech": _t("Premium vs tech", "Prima vs tech")}).copy()
        cov_col = _t("Coverage", "Cobertura")
        show[cov_col] = (show[cov_col] * 100).round(1).astype(str) + " %"
        st.dataframe(show.round(2), use_container_width=True, hide_index=True)

    with tab_evo:
        ent_meta = master[["UP", "SM", "Tech"]].drop_duplicates("UP")
        evo = evolution_by_level(res["dfe"], ent_meta, level)
        f = _fig_evo(evo, r_mkt, "pr_w")
        if f:
            st.plotly_chart(f, use_container_width=True)
        f = _fig_evo(evo, r_mkt, "mw")
        if f:
            st.plotly_chart(f, use_container_width=True)

    with tab_ai:
        payload = _build_payload(ups, r_mkt, res["d_ini"], res["d_fin"], res["reps"])
        md = _payload_md(payload)
        st.caption(_t("Copy into a Claude chat for the interpretation.",
                      "Copia en un chat con Claude para la interpretación."))
        st.code(md, language="markdown")
        st.download_button(_t("Download .md", "Descargar .md"), md,
                           file_name=f"ofertas_up_{res['mkt_key']}_{res['d_ini']}_{res['d_fin']}.md")
        with st.expander(_t("Call the API (advanced)", "Llamar a la API (avanzado)")):
            if st.button(_t("Interpret with Claude (API)", "Interpretar con Claude (API)")):
                try:
                    with st.spinner("Claude…"):
                        st.markdown(_call_claude(payload))
                except Exception as e:
                    st.error(str(e))


if __name__ == "__main__":
    st.set_page_config(page_title="Ofertas de representantes", layout="wide")
    set_bq()
    render_representantes()
