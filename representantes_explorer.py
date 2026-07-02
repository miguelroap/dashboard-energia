# -*- coding: utf-8 -*-
"""
representantes_explorer.py — Comparador de ofertas de representantes  (v2)
==========================================================================

Sección drop-in para el dashboard de Servicios de Ajuste, gemela estructural
de unit_explorer.py (mismos setters de inyección, mismos fallbacks, misma `t`).

Lee DIRECTAMENTE de BigQuery las 11 tablas `i90_diaXX_*offer*_raw`
(pieza `ofertas-fetch-data`) y ofrece TRES vistas analíticas:

  1. COMPARATIVA   — métricas agregadas del período por representante
                     (MW, precio ponderado por MW, rango, bloques, cobertura)
  2. EVOLUCIÓN     — precio ponderado y MW ofertado día a día por representante
                     (para ver cambios de estrategia en el tiempo)
  3. CURVA         — forma de la curva por bloques B1→Bn de cada representante
                     (agresividad del primer bloque, escalado del precio)

Novedades v2 respecto a v1:
  · Muestra el rango de fechas REALMENTE disponible en la tabla (I90 = D+90)
    y propone por defecto la última semana disponible, no las fechas del sidebar.
  · Los resultados se guardan en session_state: cambiar de pestaña o tocar un
    control no borra el análisis; solo el botón "Comparar" recalcula.
  · Intérprete IA (patrón B: copiar para chat; patrón A: API preparada).

Integración en app.py: idéntica a v1 (import + set_rep_bq + set_rep_helpers +
entrada de menú + elif final). Ver bloque comentado al final del fichero.

Permisos: el SA de st.secrets['gcp_service_account'] necesita
roles/bigquery.jobUser + roles/bigquery.dataViewer (+ storage.objectViewer
sobre gs://miguel-energia-programming-units para la external table de UPs).
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
# entity:      'UP' → filtra por UPs del SM ; 'PM' → por código Participante I90
# interleaved: True  → MW y €/MWh en la MISMA tabla y fila (13/15/38)
#              False → MW y precio en tablas distintas que hay que cruzar
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

_SS_KEY = "repofertas_result"   # session_state: resultados persistentes


# ==============================================================================
# INYECCIÓN DE DEPENDENCIAS  (mismo patrón que unit_explorer.py)
# ==============================================================================
_BQ = {}
_HELPERS = {}


def set_bq(client=None, project="miguel-energia", dataset="red_electrica_data"):
    """Inyecta cliente BQ y dataset. Con client=None se crea desde st.secrets."""
    _BQ["client"] = client
    _BQ["project"] = project
    _BQ["dataset"] = dataset


def set_helpers(metric_card=None, section_header=None, base_layout=None, t=None):
    """Inyecta los helpers visuales de app.py (opcional: hay fallbacks)."""
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


def _metric(label, value, unit="", positive=None, delta=None):
    fn = _HELPERS.get("metric_card")
    if fn:
        st.markdown(fn(label, value, delta=delta, positive=positive, unit=unit),
                    unsafe_allow_html=True)
    else:
        st.metric(label, f"{value}{unit}", delta=delta)


def _layout(**extra):
    fn = _HELPERS.get("base_layout")
    if fn:
        return fn(**extra)
    base = dict(
        template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#FBFCFE",
        font=dict(family="Inter, sans-serif", color="#46556B", size=12),
        margin=dict(l=10, r=10, t=45, b=10),
    )
    base.update(extra)
    return base


def _mkt_label(mkt):
    return _t(mkt["label_en"], mkt["label_es"])


# ==============================================================================
# CLIENTE BIGQUERY
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
    if c is not None:
        return c
    c = _build_bq_client(_BQ.get("project", "miguel-energia"))
    _BQ["client"] = c
    return c


def _qp(d_ini, d_fin):
    from google.cloud import bigquery
    return bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
        bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin)])


# ==============================================================================
# MAESTRO DE UPs Y DISPONIBILIDAD DE DATOS
# ==============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def _load_up_master():
    project, dataset = _BQ["project"], _BQ["dataset"]
    sql = f"""
        SELECT UP, Power_MW, Tech,
               Sujeto_del_Mercado   AS SM,
               Sujeto_del_Mercado_2 AS SM2, RZ
        FROM `{project}.{dataset}.programming_units_external_table_latest`
    """
    return _client().query(sql).to_dataframe()


@st.cache_data(ttl=3600, show_spinner=False)
def _data_availability(table):
    """Rango de fechas con datos en la tabla (solo lee la columna de partición)."""
    project, dataset = _BQ["project"], _BQ["dataset"]
    sql = f"""SELECT MIN(DELIVERY_DATE_DAY_CET) AS dmin,
                     MAX(DELIVERY_DATE_DAY_CET) AS dmax
              FROM `{project}.{dataset}.{table}`"""
    df = _client().query(sql).to_dataframe()
    if df.empty or pd.isna(df.loc[0, "dmax"]):
        return None, None
    return pd.to_datetime(df.loc[0, "dmin"]).date(), pd.to_datetime(df.loc[0, "dmax"]).date()


# ==============================================================================
# QUERIES  (agregación en BQ; solo bajan filas ya agregadas)
# ==============================================================================
def _q_blocks(mkt, entities, d_ini, d_fin):
    """Agregado del período por (ENTITY, BLOCK): MW total y precio."""
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
        side_f = f"AND OFFER_SIDE = '{mkt['side']}'" if mkt["side"] else ""
        sql = f"""
        WITH mw AS (
          SELECT ENTITY, BLOCK, SUM(VALUE_MW) AS mw_sum,
                 COUNT(VALUE_MW) AS qh_count,
                 COUNT(DISTINCT DELIVERY_DATE_DAY_CET) AS days
          FROM `{project}.{dataset}.{mkt['mw_table']}`
          WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
            AND ENTITY IN ({ent_list}) {side_f} AND VALUE_MW IS NOT NULL
          GROUP BY ENTITY, BLOCK),
        pr AS (
          SELECT ENTITY, BLOCK, AVG(VALUE_EUR) AS pr_w,
                 MIN(VALUE_EUR) AS pr_min, MAX(VALUE_EUR) AS pr_max
          FROM `{project}.{dataset}.{mkt['pr_table']}`
          WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
            AND ENTITY IN ({ent_list}) {side_f} AND VALUE_EUR IS NOT NULL
          GROUP BY ENTITY, BLOCK)
        SELECT mw.ENTITY, mw.BLOCK, mw.mw_sum, mw.qh_count, mw.days,
               pr.pr_w, pr.pr_min, pr.pr_max
        FROM mw LEFT JOIN pr USING (ENTITY, BLOCK)"""
    return _client().query(sql, job_config=_qp(d_ini, d_fin)).to_dataframe()


def _q_evolution(mkt, entities, d_ini, d_fin):
    """Serie diaria por ENTITY: MW total y precio (pond. si interleaved)."""
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
        side_f = f"AND OFFER_SIDE = '{mkt['side']}'" if mkt["side"] else ""
        sql = f"""
        WITH mw AS (
          SELECT DELIVERY_DATE_DAY_CET AS d, ENTITY, SUM(VALUE_MW) AS mw_sum
          FROM `{project}.{dataset}.{mkt['mw_table']}`
          WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
            AND ENTITY IN ({ent_list}) {side_f} AND VALUE_MW IS NOT NULL
          GROUP BY d, ENTITY),
        pr AS (
          SELECT DELIVERY_DATE_DAY_CET AS d, ENTITY, AVG(VALUE_EUR) AS pr_w
          FROM `{project}.{dataset}.{mkt['pr_table']}`
          WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
            AND ENTITY IN ({ent_list}) {side_f} AND VALUE_EUR IS NOT NULL
          GROUP BY d, ENTITY)
        SELECT mw.d, mw.ENTITY, mw.mw_sum, pr.pr_w
        FROM mw LEFT JOIN pr USING (d, ENTITY)"""
    return _client().query(sql, job_config=_qp(d_ini, d_fin)).to_dataframe()


def _dry_run_gb(mkt, entities, d_ini, d_fin):
    from google.cloud import bigquery
    project, dataset = _BQ["project"], _BQ["dataset"]
    ent_list = ",".join(f"'{e}'" for e in entities) or "''"
    sql = f"""SELECT ENTITY FROM `{project}.{dataset}.{mkt['mw_table']}`
              WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
                AND ENTITY IN ({ent_list})"""
    cfg = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False,
        query_parameters=_qp(d_ini, d_fin).query_parameters)
    return _client().query(sql, job_config=cfg).total_bytes_processed / (1024 ** 3)


# ==============================================================================
# AGREGACIONES EN PANDAS  (mapear ENTITY→representante y consolidar)
# ==============================================================================
def _wavg(g, val, w):
    """Media de `val` ponderada por `w`, tolerante a NaN y peso cero."""
    v = g.dropna(subset=[val])
    tw = v[w].sum()
    if tw and tw > 0:
        return float((v[val] * v[w]).sum() / tw)
    return float(v[val].mean()) if not v.empty else None


def _rep_metrics(df_blocks, entity_to_rep):
    """Una fila por representante: métricas agregadas del período."""
    if df_blocks is None or df_blocks.empty:
        return pd.DataFrame()
    df = df_blocks.copy()
    df["rep"] = df["ENTITY"].map(entity_to_rep).fillna(df["ENTITY"])
    rows = []
    for rep, g in df.groupby("rep"):
        rows.append(dict(
            rep=rep,
            mw=round(float(g["mw_sum"].sum()), 1),
            pr_w=_wavg(g, "pr_w", "mw_sum"),
            pr_min=float(g["pr_min"].min()) if g["pr_min"].notna().any() else None,
            pr_max=float(g["pr_max"].max()) if g["pr_max"].notna().any() else None,
            blocks=round(float(g.groupby("ENTITY")["BLOCK"].nunique().mean()), 1),
            n_ent=int(g["ENTITY"].nunique()),
            qh=int(g["qh_count"].sum()),
            days=int(g["days"].max()),
        ))
    return pd.DataFrame(rows).sort_values("mw", ascending=False).reset_index(drop=True)


def _wgroup(df, keys):
    """Agrega por `keys`: mw = Σ mw_sum; pr_w = media ponderada por mw_sum.
    Vectorizado (sin groupby.apply) para compatibilidad con cualquier pandas."""
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


def _rep_evolution(df_evo, entity_to_rep):
    """Serie diaria por representante: MW y precio ponderado por MW."""
    if df_evo is None or df_evo.empty:
        return pd.DataFrame()
    df = df_evo.copy()
    df["rep"] = df["ENTITY"].map(entity_to_rep).fillna(df["ENTITY"])
    out = _wgroup(df, ["d", "rep"])
    out["d"] = pd.to_datetime(out["d"])
    return out.sort_values("d")


def _rep_curve(df_blocks, entity_to_rep):
    """Forma de curva: por representante y bloque, MW y precio ponderado."""
    if df_blocks is None or df_blocks.empty:
        return pd.DataFrame()
    df = df_blocks.copy()
    df["rep"] = df["ENTITY"].map(entity_to_rep).fillna(df["ENTITY"])
    return _wgroup(df, ["rep", "BLOCK"]).sort_values(["rep", "BLOCK"])


# ==============================================================================
# PAYLOAD IA
# ==============================================================================
def _build_payload(metrics, curve, mkt, d_ini, d_fin, reps_sel):
    tabla = metrics.rename(columns={
        "rep": "representante", "mw": "MW_ofertado_total",
        "pr_w": f"precio_pond_{mkt['price_unit']}",
        "pr_min": "precio_min", "pr_max": "precio_max",
        "blocks": "n_bloques_medio", "n_ent": "n_entidades",
        "qh": "qh_con_oferta", "days": "dias_con_datos",
    }).round(2).to_dict(orient="records")
    curva = (curve.round(2).rename(columns={"rep": "representante", "BLOCK": "bloque",
                                            "mw": "MW", "pr_w": "precio_pond"})
                  .to_dict(orient="records")) if not curve.empty else []
    return {
        "mercado": mkt["label_es"],
        "unidad_precio": mkt["price_unit"],
        "periodo": {"inicio": str(d_ini), "fin": str(d_fin)},
        "representantes": list(reps_sel),
        "nota": ("Precios ponderados por MW ofertado (no media simple). "
                 "La curva por bloques muestra la escalera B1→Bn de cada agente."),
        "resumen_por_representante": tabla,
        "curva_por_bloques": curva,
    }


def _payload_md(p):
    md = ["# Comparación de ofertas de representantes",
          f"**Mercado:** {p['mercado']} · **Período:** "
          f"{p['periodo']['inicio']} → {p['periodo']['fin']} · "
          f"**Precio en:** {p['unidad_precio']}", "",
          f"_{p['nota']}_", "", "## Resumen por representante"]

    def _table(rows):
        if not rows:
            return ["(sin datos)"]
        cols = list(rows[0].keys())
        out = ["| " + " | ".join(cols) + " |",
               "| " + " | ".join("---" for _ in cols) + " |"]
        out += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
        return out

    md += _table(p["resumen_por_representante"])
    md += ["", "## Curva por bloques (escalera de oferta)"]
    md += _table(p["curva_por_bloques"])
    md.append("")
    md.append(dedent("""\
        ---
        **Pregunta:** Interpreta esta comparación de ofertas del mercado de
        balancing español:
        1. ¿Quién oferta más agresivo en precio y quién más conservador?
        2. ¿Alguien pone mucha capacidad a precio alto, o poca a precio bajo?
        3. ¿Qué dice la forma de la escalera B1→Bn de la estrategia de cada uno
           (primer bloque barato para asegurar casación vs escalera plana)?
        4. Señales de poder de mercado o de zona de regulación poco competida.
        5. Qué mirarías después para confirmar cada hipótesis."""))
    return "\n".join(md)


# === API HOOK ===  patrón A (requiere `anthropic` + ANTHROPIC_API_KEY)
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
def _fig_scatter(m, mkt):
    if m.empty or m["pr_w"].isna().all():
        return None
    fig = px.scatter(m, x="mw", y="pr_w", text="rep", size="n_ent", color="rep",
                     labels={"mw": _t("MW offered (Σ)", "MW ofertado (Σ)"),
                             "pr_w": f"{_t('W.avg price', 'Precio pond.')} ({mkt['price_unit']})"})
    fig.update_traces(textposition="top center")
    fig.update_layout(**_layout(height=420, showlegend=False,
                                title=_t("Competitive map", "Mapa competitivo")))
    return fig


def _fig_bars(m, mkt):
    if m.empty:
        return None
    fig = go.Figure()
    fig.add_bar(x=m["rep"], y=m["mw"],
                name=_t("MW offered (Σ)", "MW ofertado (Σ)"), marker_color="#1F5EDC")
    if m["pr_w"].notna().any():
        fig.add_scatter(x=m["rep"], y=m["pr_w"], yaxis="y2", mode="markers+lines",
                        name=f"{_t('W.avg price', 'Precio pond.')} ({mkt['price_unit']})",
                        marker=dict(size=11), line=dict(color="#C2660E"))
    fig.update_layout(**_layout(
        height=420, title=_t("MW vs price", "MW vs precio"),
        yaxis=dict(title="MW"),
        yaxis2=dict(title=mkt["price_unit"], overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.12)))
    return fig


def _fig_evo_price(evo, mkt):
    if evo.empty or evo["pr_w"].isna().all():
        return None
    fig = px.line(evo, x="d", y="pr_w", color="rep", markers=True,
                  labels={"d": "", "pr_w": mkt["price_unit"], "rep": ""})
    fig.update_layout(**_layout(height=400,
                                title=_t("Daily weighted price", "Precio ponderado diario"),
                                legend=dict(orientation="h", y=1.12)))
    return fig


def _fig_evo_mw(evo):
    if evo.empty:
        return None
    fig = px.line(evo, x="d", y="mw", color="rep", markers=True,
                  labels={"d": "", "mw": "MW", "rep": ""})
    fig.update_layout(**_layout(height=400,
                                title=_t("Daily MW offered", "MW ofertado diario"),
                                legend=dict(orientation="h", y=1.12)))
    return fig


def _fig_curve_price(curve, mkt):
    if curve.empty or curve["pr_w"].isna().all():
        return None
    fig = px.line(curve, x="BLOCK", y="pr_w", color="rep", markers=True,
                  labels={"BLOCK": _t("Block", "Bloque"),
                          "pr_w": mkt["price_unit"], "rep": ""})
    fig.update_xaxes(dtick=1)
    fig.update_layout(**_layout(height=400,
                                title=_t("Price ladder B1→Bn", "Escalera de precio B1→Bn"),
                                legend=dict(orientation="h", y=1.12)))
    return fig


def _fig_curve_mw(curve):
    if curve.empty:
        return None
    fig = px.bar(curve, x="BLOCK", y="mw", color="rep", barmode="group",
                 labels={"BLOCK": _t("Block", "Bloque"), "mw": "MW", "rep": ""})
    fig.update_xaxes(dtick=1)
    fig.update_layout(**_layout(height=400,
                                title=_t("MW per block", "MW por bloque"),
                                legend=dict(orientation="h", y=1.12)))
    return fig


# ==============================================================================
# RENDER PRINCIPAL
# ==============================================================================
def render_representantes(start_date=None, end_date=None, pm_map=None):
    """
    Pinta la sección de comparación de ofertas de representantes.

    start_date/end_date se ignoran a efectos de valor por defecto si quedan
    fuera del rango con datos (I90 = D+90): el módulo propone la última semana
    realmente disponible en la tabla del mercado elegido.
    pm_map : dict {SM: codigo_PM_I90} — solo para banda/energía secundaria.
    """
    _section("🏛️", _t("Agent Offers Comparison", "Comparador de Ofertas de Representantes"))
    st.caption(_t(
        "Pay-as-bid offer curves from BigQuery. Three views: period comparison, "
        "daily evolution, and B1→Bn curve shape per agent.",
        "Curvas de oferta pay-as-bid desde BigQuery. Tres vistas: comparativa del "
        "período, evolución diaria y forma de curva B1→Bn por representante."))

    # ── Maestro de UPs ────────────────────────────────────────────────
    try:
        master = _load_up_master()
    except Exception as e:
        st.error(_t("Could not load UP master from BigQuery: ",
                    "No se pudo cargar el maestro de UPs desde BigQuery: ") + str(e))
        return
    sm_options = sorted(master["SM"].dropna().unique().tolist())

    # ── Controles ─────────────────────────────────────────────────────
    c1, c2 = st.columns([2, 1])
    with c1:
        reps_sel = st.multiselect(
            _t("Agents to compare", "Representantes a comparar"), sm_options,
            default=sm_options[:3] if len(sm_options) >= 3 else sm_options,
            key="rep_sel")
    with c2:
        mkt_key = st.selectbox(_t("Market", "Mercado"), list(MARKETS.keys()),
                               format_func=lambda k: _mkt_label(MARKETS[k]),
                               key="rep_mkt")
    mkt = MARKETS[mkt_key]

    # ── Disponibilidad real de datos (I90 = D+90) ────────────────────
    try:
        dmin, dmax = _data_availability(mkt["mw_table"])
    except Exception as e:
        st.error(_t("Could not check data availability: ",
                    "No se pudo comprobar la disponibilidad de datos: ") + str(e))
        return
    if dmax is None:
        st.warning(_t("This market's table is empty in BigQuery.",
                      "La tabla de este mercado está vacía en BigQuery."))
        return
    st.info(_t(f"📅 Data available: **{dmin} → {dmax}** (I90 is published at D+90).",
               f"📅 Datos disponibles: **{dmin} → {dmax}** (los I90 se publican a D+90)."))

    # Fechas por defecto: última semana DISPONIBLE (no el rango del sidebar)
    def_fin = dmax
    def_ini = max(dmin, dmax - dt.timedelta(days=6))
    c3, c4 = st.columns(2)
    with c3:
        d_ini = st.date_input(_t("From", "Desde"), value=def_ini,
                              min_value=dmin, max_value=dmax,
                              key=f"rep_dini_{mkt_key}")
    with c4:
        d_fin = st.date_input(_t("To", "Hasta"), value=def_fin,
                              min_value=dmin, max_value=dmax,
                              key=f"rep_dfin_{mkt_key}")

    if not reps_sel:
        st.info(_t("Select at least one agent.", "Selecciona al menos un representante."))
        return
    if d_ini > d_fin:
        st.error(_t("Date range is inverted.", "El rango de fechas está invertido."))
        return

    # ── Resolver entidades por representante ─────────────────────────
    entity_to_rep, entities = {}, []
    if mkt["entity"] == "UP":
        sub = master[master["SM"].isin(reps_sel)]
        for _, r in sub.iterrows():
            if pd.notna(r["UP"]):
                entity_to_rep[r["UP"]] = r["SM"]
                entities.append(r["UP"])
    else:
        if not pm_map:
            st.warning(_t(
                "Market-Participant market: provide pm_map (e.g. GNERA→GNE). "
                "Falling back to SM2 (likely wrong).",
                "Mercado de Participante: pasa pm_map (p.ej. GNERA→GNE). "
                "De momento uso el SM2 (probablemente incorrecto)."))
        for sm in reps_sel:
            code = (pm_map or {}).get(sm)
            if not code:
                sm2s = master.loc[master["SM"] == sm, "SM2"].dropna()
                code = sm2s.mode().iloc[0] if not sm2s.empty else sm
            entity_to_rep[code] = sm
            entities.append(code)
    entities = sorted(set(entities))
    if not entities:
        st.error(_t("No entities found for selection.",
                    "Ningún representante seleccionado tiene entidades."))
        return

    # ── Coste + botón ─────────────────────────────────────────────────
    with st.expander(_t("Estimated query cost (dry-run)",
                        "Coste estimado de la consulta (dry-run)")):
        try:
            gb = _dry_run_gb(mkt, entities, d_ini, d_fin)
            st.write(f"**{gb:.3f} GB** (~{gb*6.25:.4f} € "
                     + _t("beyond free TB", "fuera del TB gratis mensual") + ")")
        except Exception as e:
            st.caption(str(e))

    if st.button(_t("Compare offers", "Comparar ofertas"), type="primary"):
        with st.spinner(_t("Querying BigQuery…", "Consultando BigQuery…")):
            try:
                df_blocks = _q_blocks(mkt, entities, d_ini, d_fin)
                df_evo = _q_evolution(mkt, entities, d_ini, d_fin)
            except Exception as e:
                st.error(str(e))
                return
        st.session_state[_SS_KEY] = dict(
            mkt_key=mkt_key, reps=list(reps_sel),
            d_ini=str(d_ini), d_fin=str(d_fin),
            metrics=_rep_metrics(df_blocks, entity_to_rep),
            evo=_rep_evolution(df_evo, entity_to_rep),
            curve=_rep_curve(df_blocks, entity_to_rep))

    res = st.session_state.get(_SS_KEY)
    if not res:
        return
    if res["mkt_key"] != mkt_key or res["reps"] != list(reps_sel) \
            or res["d_ini"] != str(d_ini) or res["d_fin"] != str(d_fin):
        st.caption(_t("⚠️ Showing previous results — press *Compare offers* to refresh.",
                      "⚠️ Mostrando resultados anteriores — pulsa *Comparar ofertas* para refrescar."))

    metrics, evo, curve = res["metrics"], res["evo"], res["curve"]
    r_mkt = MARKETS[res["mkt_key"]]

    if metrics.empty:
        st.warning(_t("No offer data for that selection/period.",
                      "Sin datos de oferta para esa selección y período."))
        return

    # ── KPIs de cabecera ──────────────────────────────────────────────
    k = st.columns(min(4, len(metrics)) or 1)
    for i, (_, row) in enumerate(metrics.head(4).iterrows()):
        with k[i]:
            pr_txt = f"{row['pr_w']:.1f}" if pd.notna(row["pr_w"]) else "—"
            _metric(row["rep"], pr_txt, unit=f" {r_mkt['price_unit']}",
                    delta=f"{row['mw']:,.0f} MW · {row['n_ent']} UPs")

    # ── Vistas ────────────────────────────────────────────────────────
    tab_cmp, tab_evo, tab_curve, tab_ai = st.tabs([
        _t("📊 Comparison", "📊 Comparativa"),
        _t("📈 Evolution", "📈 Evolución"),
        _t("🪜 Curve shape", "🪜 Curva por bloques"),
        _t("🤖 AI reading", "🤖 Lectura IA")])

    with tab_cmp:
        show = metrics.rename(columns={
            "rep": _t("Agent", "Representante"),
            "mw": _t("MW offered (Σ)", "MW ofertado (Σ)"),
            "pr_w": f"{_t('W.avg price', 'Precio pond.')} ({r_mkt['price_unit']})",
            "pr_min": _t("Min", "Mín"), "pr_max": _t("Max", "Máx"),
            "blocks": _t("Blocks (avg)", "Bloques (medio)"),
            "n_ent": _t("Entities", "Entidades"),
            "qh": _t("QH offered", "QH con oferta"),
            "days": _t("Days", "Días")}).round(2)
        st.dataframe(show, use_container_width=True, hide_index=True)
        g1, g2 = st.columns(2)
        with g1:
            f = _fig_scatter(metrics, r_mkt)
            st.plotly_chart(f, use_container_width=True) if f else \
                st.caption(_t("No price data.", "Sin datos de precio."))
        with g2:
            f = _fig_bars(metrics, r_mkt)
            if f:
                st.plotly_chart(f, use_container_width=True)

    with tab_evo:
        st.caption(_t(
            "How each agent's weighted price and offered MW move day by day — "
            "the view for spotting strategy shifts (e.g. after a regulatory change).",
            "Cómo se mueven día a día el precio ponderado y los MW de cada agente — "
            "la vista para detectar cambios de estrategia (p.ej. tras un cambio regulatorio)."))
        f = _fig_evo_price(evo, r_mkt)
        st.plotly_chart(f, use_container_width=True) if f else \
            st.caption(_t("No price series.", "Sin serie de precios."))
        f = _fig_evo_mw(evo)
        if f:
            st.plotly_chart(f, use_container_width=True)

    with tab_curve:
        st.caption(_t(
            "The B1→Bn ladder: a cheap first block secures dispatch; a flat ladder "
            "signals indifference; a steep one, opportunistic pricing of the margin.",
            "La escalera B1→Bn: un primer bloque barato asegura casación; una escalera "
            "plana señala indiferencia; una empinada, precio oportunista del margen."))
        g1, g2 = st.columns(2)
        with g1:
            f = _fig_curve_price(curve, r_mkt)
            st.plotly_chart(f, use_container_width=True) if f else \
                st.caption(_t("No price data.", "Sin datos de precio."))
        with g2:
            f = _fig_curve_mw(curve)
            if f:
                st.plotly_chart(f, use_container_width=True)

    with tab_ai:
        payload = _build_payload(metrics, curve, r_mkt,
                                 res["d_ini"], res["d_fin"], res["reps"])
        md = _payload_md(payload)
        st.caption(_t("Copy and paste into a Claude chat for the interpretation.",
                      "Copia y pégalo en un chat con Claude para la interpretación."))
        st.code(md, language="markdown")
        st.download_button(_t("Download .md", "Descargar .md"), md,
                           file_name=f"ofertas_{res['mkt_key']}_{res['d_ini']}_{res['d_fin']}.md")
        with st.expander(_t("Call the API instead (advanced)",
                            "Llamar a la API directamente (avanzado)")):
            st.caption(_t(
                "Requires `anthropic` + ANTHROPIC_API_KEY in secrets and egress to api.anthropic.com.",
                "Requiere `anthropic` + ANTHROPIC_API_KEY en secrets y egress a api.anthropic.com."))
            if st.button(_t("Interpret with Claude (API)", "Interpretar con Claude (API)")):
                try:
                    with st.spinner("Claude…"):
                        st.markdown(_call_claude(payload))
                except Exception as e:
                    st.error(str(e))


# ==============================================================================
# INTEGRACIÓN EN app.py — idéntica a v1 (sin cambios si ya integraste v1)
# ==============================================================================
"""
    from representantes_explorer import (
        render_representantes, set_bq as set_rep_bq, set_helpers as set_rep_helpers)

    set_rep_bq(client=None, project="miguel-energia", dataset="red_electrica_data")
    set_rep_helpers(metric_card=metric_card, section_header=section_header,
                    base_layout=base_layout, t=t)

    name_repofertas = t("🏛️ Agent Offers", "🏛️ Ofertas Representantes")
    # añadir name_repofertas a menu_options

    elif seleccion_menu == name_repofertas:
        render_representantes(start_date, end_date,
                              pm_map={"GNERA": "GNE", "AXPO IBERIA": "AXP"})
        gc.collect()
"""

if __name__ == "__main__":
    st.set_page_config(page_title="Comparador de ofertas", layout="wide")
    set_bq()
    render_representantes()
