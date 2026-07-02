# -*- coding: utf-8 -*-
"""
representantes_explorer.py — Comparador de ofertas de representantes
===================================================================

Sección drop-in para el dashboard de Servicios de Ajuste, gemela estructural
de unit_explorer.py (mismos setters de inyección, mismos fallbacks, misma `t`).

A DIFERENCIA del resto del dashboard (que lee parquets de GCS), este módulo
lee DIRECTAMENTE de BigQuery: las 11 tablas de oferta `i90_diaXX_*offer*_raw`
(pieza `ofertas-fetch-data`). Agrega la curva de oferta de cada representante
en SQL y deriva métricas comparables entre Sujetos del Mercado:

  · MW ofertado total           (capacidad que pone en el mercado)
  · €/MWh ofertado pond. por MW (lo caro/barato que es, de verdad)
  · €/MWh mín y máx             (rango de la curva: agresividad del primer bloque)
  · Nº de bloques medio         (granularidad de la curva)
  · Nº de entidades             (amplitud de cartera)
  · QH con oferta               (constancia / disponibilidad)

El "Precio pond." pondera por MW: comparar el €/MWh a pelo engaña, porque un
bloque marginal de 1 MW a 500 €/MWh pesaría igual que 200 MW a 20.

Incluye intérprete IA en dos modos:
  · Patrón B (por defecto): genera un resumen markdown para pegar en un chat.
  · Patrón A (preparado):   botón que llama a la API de Claude (requiere
    `anthropic` + st.secrets['ANTHROPIC_API_KEY'] + egress permitido).

Integración (4 líneas en app.py): ver bloque al final de este fichero.

Requisito de permisos: el service account de st.secrets['gcp_service_account']
necesita roles BigQuery (jobUser + dataViewer) sobre el dataset, no solo Storage.
"""

import datetime as dt
from textwrap import dedent

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px


# ==============================================================================
# CATÁLOGO DE MERCADOS  (qué tablas, qué entidad, qué lado)
# ==============================================================================
# entity:      'UP' → filtra por UPs del SM ; 'PM' → por código Participante I90
# interleaved: True  → MW y €/MWh en la MISMA tabla y fila (13/15/38)
#              False → MW y precio en tablas distintas que hay que cruzar
# price_unit:  etiqueta UI (banda secundaria es €/MW, el resto €/MWh)
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

C_POS = "#059669"
C_NEG = "#dc2626"
C_GRID = "#e2e8f0"


# ==============================================================================
# INYECCIÓN DE DEPENDENCIAS  (mismo patrón que unit_explorer.py)
# ==============================================================================
_BQ = {}        # cliente BigQuery + project/dataset
_HELPERS = {}   # helpers visuales de app.py


def set_bq(client=None, project="miguel-energia", dataset="red_electrica_data"):
    """
    Inyecta el cliente BigQuery y la ubicación del dataset.
    Si client=None, el módulo lo crea desde st.secrets['gcp_service_account']
    la primera vez que se necesite.
    """
    _BQ["client"] = client
    _BQ["project"] = project
    _BQ["dataset"] = dataset


def set_helpers(metric_card=None, section_header=None, base_layout=None, t=None):
    """Inyecta los helpers visuales de app.py (opcional: hay fallbacks)."""
    if metric_card:     _HELPERS["metric_card"] = metric_card
    if section_header:  _HELPERS["section_header"] = section_header
    if base_layout:     _HELPERS["base_layout"] = base_layout
    if t:               _HELPERS["t"] = t


# --- Fallbacks por si no se inyectan (uso standalone / testing) ---
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
    base = dict(
        template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
        font=dict(family="Inter, sans-serif", color="#475569", size=12),
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
    """Crea un cliente BQ desde st.secrets (mismo secreto que gcs_loader)."""
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


# ==============================================================================
# MAESTRO DE UPs  (resolver entidades por representante)
# ==============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def _load_up_master():
    """Lee el maestro de UPs de BQ (vista latest)."""
    project, dataset = _BQ["project"], _BQ["dataset"]
    sql = f"""
        SELECT UP, Power_MW, Tech, Buy_Sell,
               Sujeto_del_Mercado   AS SM,
               Sujeto_del_Mercado_2 AS SM2, RZ
        FROM `{project}.{dataset}.programming_units_external_table_latest`
    """
    return _client().query(sql).to_dataframe()


# ==============================================================================
# QUERIES BQ  (agregación en el servidor — barato y rápido)
# ==============================================================================
def _q_simple(mkt, entities, d_ini, d_fin):
    """Hojas simples: MW y precio en tablas distintas; se cruzan por bloque."""
    from google.cloud import bigquery
    project, dataset = _BQ["project"], _BQ["dataset"]
    ent_list = ",".join(f"'{e}'" for e in entities)
    side = mkt["side"]
    side_filter = f"AND OFFER_SIDE = '{side}'" if side else ""
    sql = f"""
    WITH mw AS (
      SELECT ENTITY, BLOCK,
             SUM(VALUE_MW)   AS mw_sum,
             COUNT(VALUE_MW) AS qh_count,
             COUNT(DISTINCT DELIVERY_DATE_DAY_CET) AS days
      FROM `{project}.{dataset}.{mkt['mw_table']}`
      WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
        AND ENTITY IN ({ent_list}) {side_filter}
        AND VALUE_MW IS NOT NULL
      GROUP BY ENTITY, BLOCK
    ),
    pr AS (
      SELECT ENTITY, BLOCK,
             AVG(VALUE_EUR) AS pr_avg,
             MIN(VALUE_EUR) AS pr_min,
             MAX(VALUE_EUR) AS pr_max
      FROM `{project}.{dataset}.{mkt['pr_table']}`
      WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
        AND ENTITY IN ({ent_list}) {side_filter}
        AND VALUE_EUR IS NOT NULL
      GROUP BY ENTITY, BLOCK
    )
    SELECT mw.ENTITY, mw.BLOCK, mw.mw_sum, mw.qh_count, mw.days,
           pr.pr_avg AS pr_w, pr.pr_min, pr.pr_max
    FROM mw LEFT JOIN pr USING (ENTITY, BLOCK)
    """
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
        bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin)])
    return _client().query(sql, job_config=cfg).to_dataframe()


def _q_interleaved(mkt, entities, d_ini, d_fin):
    """Hojas interleaved: MW y precio en la misma fila → precio pond. en SQL."""
    from google.cloud import bigquery
    project, dataset = _BQ["project"], _BQ["dataset"]
    ent_list = ",".join(f"'{e}'" for e in entities)
    sql = f"""
    SELECT ENTITY, BLOCK,
           SUM(VALUE_MW) AS mw_sum,
           SAFE_DIVIDE(SUM(VALUE_MW * VALUE_EUR), SUM(VALUE_MW)) AS pr_w,
           MIN(VALUE_EUR) AS pr_min,
           MAX(VALUE_EUR) AS pr_max,
           COUNT(VALUE_MW) AS qh_count,
           COUNT(DISTINCT DELIVERY_DATE_DAY_CET) AS days
    FROM `{project}.{dataset}.{mkt['mw_table']}`
    WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
      AND ENTITY IN ({ent_list})
      AND VALUE_MW IS NOT NULL
    GROUP BY ENTITY, BLOCK
    """
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
        bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin)])
    return _client().query(sql, job_config=cfg).to_dataframe()


def _dry_run_gb(mkt, entities, d_ini, d_fin):
    """Estima GB a escanear sin ejecutar (aviso de coste)."""
    from google.cloud import bigquery
    project, dataset = _BQ["project"], _BQ["dataset"]
    ent_list = ",".join(f"'{e}'" for e in entities) or "''"
    sql = f"""SELECT ENTITY FROM `{project}.{dataset}.{mkt['mw_table']}`
              WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
                AND ENTITY IN ({ent_list})"""
    cfg = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False,
        query_parameters=[
            bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
            bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin)])
    return _client().query(sql, job_config=cfg).total_bytes_processed / (1024 ** 3)


# ==============================================================================
# MÉTRICAS COMPARABLES POR REPRESENTANTE
# ==============================================================================
def _metrics(df_blocks, mkt, entity_to_rep):
    if df_blocks is None or df_blocks.empty:
        return pd.DataFrame()
    df = df_blocks.copy()
    df["rep"] = df["ENTITY"].map(entity_to_rep).fillna(df["ENTITY"])
    unit = mkt["price_unit"]
    rows = []
    for rep, g in df.groupby("rep"):
        mw_total = g["mw_sum"].sum(skipna=True)
        valid = g.dropna(subset=["pr_w"])
        if valid["mw_sum"].sum() > 0:
            pr_w = (valid["pr_w"] * valid["mw_sum"]).sum() / valid["mw_sum"].sum()
        else:
            pr_w = valid["pr_w"].mean()
        rows.append({
            _t("Agent", "Representante"): rep,
            _t("MW offered (Σ)", "MW ofertado (Σ)"):
                round(float(mw_total), 1) if pd.notna(mw_total) else 0.0,
            _t(f"W.avg price ({unit})", f"Precio pond. ({unit})"):
                round(float(pr_w), 2) if pd.notna(pr_w) else None,
            _t("Min price", "Precio mín"):
                round(float(g["pr_min"].min()), 2) if g["pr_min"].notna().any() else None,
            _t("Max price", "Precio máx"):
                round(float(g["pr_max"].max()), 2) if g["pr_max"].notna().any() else None,
            _t("Blocks (avg)", "Nº bloques (medio)"):
                round(float(g.groupby("ENTITY")["BLOCK"].nunique().mean()), 1),
            _t("Entities", "Nº entidades"): int(g["ENTITY"].nunique()),
            _t("QH offered (Σ)", "QH con oferta (Σ)"): int(g["qh_count"].sum()),
            _t("Days", "Días"): int(g["days"].max()) if "days" in g else None,
        })
    sort_col = _t("MW offered (Σ)", "MW ofertado (Σ)")
    return pd.DataFrame(rows).sort_values(sort_col, ascending=False).reset_index(drop=True)


# ==============================================================================
# PAYLOAD IA
# ==============================================================================
def _build_payload(metrics, mkt, d_ini, d_fin, reps_sel):
    return {
        "mercado": mkt["label_es"],
        "unidad_precio": mkt["price_unit"],
        "periodo": {"inicio": str(d_ini), "fin": str(d_fin)},
        "representantes_comparados": list(reps_sel),
        "nota_metrica": ("El 'Precio pond.' es €/(MW·h o MW) ponderado por MW "
                         "ofertado, no la media simple de la curva."),
        "tabla": metrics.to_dict(orient="records"),
    }


def _payload_md(p):
    md = ["# Comparación de ofertas de representantes",
          f"**Mercado:** {p['mercado']} · **Período:** "
          f"{p['periodo']['inicio']} → {p['periodo']['fin']}",
          f"**Unidad de precio:** {p['unidad_precio']}", "",
          f"_{p['nota_metrica']}_", ""]
    if p["tabla"]:
        cols = list(p["tabla"][0].keys())
        md.append("| " + " | ".join(cols) + " |")
        md.append("| " + " | ".join("---" for _ in cols) + " |")
        for r in p["tabla"]:
            md.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    md.append("")
    md.append(dedent("""\
        ---
        **Pregunta:** Interpreta esta comparación de ofertas en el mercado de
        balancing español:
        1. ¿Quién oferta más agresivo en precio y quién más conservador?
        2. ¿Alguien pone mucha capacidad (MW) a precio alto, o poca a precio bajo?
        3. ¿El nº de bloques/entidades sugiere estrategias de curva distintas?
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
def _fig_scatter(metrics, mkt):
    pr_col = _t(f"W.avg price ({mkt['price_unit']})", f"Precio pond. ({mkt['price_unit']})")
    mw_col = _t("MW offered (Σ)", "MW ofertado (Σ)")
    rep_col = _t("Agent", "Representante")
    ent_col = _t("Entities", "Nº entidades")
    if metrics.empty or pr_col not in metrics:
        return None
    fig = px.scatter(metrics, x=mw_col, y=pr_col, text=rep_col,
                     size=ent_col, color=rep_col)
    fig.update_traces(textposition="top center")
    fig.update_layout(**_layout(height=420, showlegend=False,
                                title=_t("Competitive map", "Mapa competitivo") +
                                f" — {_mkt_label(mkt)}"))
    return fig


def _fig_bars(metrics, mkt):
    pr_col = _t(f"W.avg price ({mkt['price_unit']})", f"Precio pond. ({mkt['price_unit']})")
    mw_col = _t("MW offered (Σ)", "MW ofertado (Σ)")
    rep_col = _t("Agent", "Representante")
    if metrics.empty:
        return None
    fig = go.Figure()
    fig.add_bar(x=metrics[rep_col], y=metrics[mw_col], name=mw_col,
                marker_color="#2563eb")
    if pr_col in metrics:
        fig.add_scatter(x=metrics[rep_col], y=metrics[pr_col], name=pr_col,
                        mode="markers+lines", yaxis="y2", marker=dict(size=11),
                        line=dict(color="#d97706"))
    fig.update_layout(**_layout(
        height=400,
        title=_t("MW vs price by agent", "MW vs precio por representante") +
              f" — {_mkt_label(mkt)}",
        yaxis=dict(title=mw_col),
        yaxis2=dict(title=mkt["price_unit"], overlaying="y", side="right",
                    showgrid=False),
        legend=dict(orientation="h", y=1.12)))
    return fig


# ==============================================================================
# RENDER PRINCIPAL
# ==============================================================================
def render_representantes(start_date, end_date, pm_map=None):
    """
    Pinta la sección de comparación de ofertas de representantes.

    Parámetros
    ----------
    start_date, end_date : datetime.date  — rango por defecto (editable en la UI).
    pm_map : dict {SM: codigo_PM_I90}  — necesario SOLO para banda/energía
             secundaria (mercados de Participante). Ej: {'GNERA':'GNE'}.
    """
    _section("🏛️", _t("Agent Offers Comparison", "Comparador de Ofertas de Representantes"))
    st.caption(_t(
        "Pay-as-bid offer curves from BigQuery (`ofertas-fetch-data`). "
        "Compares how different Market Agents bid in each balancing market.",
        "Curvas de oferta pay-as-bid desde BigQuery (`ofertas-fetch-data`). "
        "Compara cómo ofertan los Representantes en cada mercado de balancing."))

    # Maestro de UPs
    try:
        master = _load_up_master()
    except Exception as e:
        st.error(_t("Could not load UP master from BigQuery: ",
                    "No se pudo cargar el maestro de UPs desde BigQuery: ") + str(e))
        st.info(_t(
            "Check the service account has BigQuery roles (jobUser + dataViewer), not just Storage.",
            "Revisa que el service account tenga roles BigQuery (jobUser + dataViewer), no solo Storage."))
        return

    sm_options = sorted(master["SM"].dropna().unique().tolist())

    # Controles
    c1, c2 = st.columns([2, 1])
    with c1:
        reps_sel = st.multiselect(
            _t("Agents to compare", "Representantes a comparar"),
            sm_options,
            default=sm_options[:3] if len(sm_options) >= 3 else sm_options)
    with c2:
        mkt_key = st.selectbox(
            _t("Market", "Mercado"), list(MARKETS.keys()),
            format_func=lambda k: _mkt_label(MARKETS[k]))
    mkt = MARKETS[mkt_key]

    c3, c4 = st.columns(2)
    with c3:
        d_ini = st.date_input(_t("From", "Desde"), value=start_date)
    with c4:
        d_fin = st.date_input(_t("To", "Hasta"), value=end_date)

    if not reps_sel:
        st.info(_t("Select at least one agent.", "Selecciona al menos un representante."))
        return
    if d_ini > d_fin:
        st.error(_t("Date range is inverted.", "El rango de fechas está invertido."))
        return

    # Resolver entidades por representante
    entity_to_rep, entities = {}, []
    if mkt["entity"] == "UP":
        sub = master[master["SM"].isin(reps_sel)]
        for _, r in sub.iterrows():
            if pd.notna(r["UP"]):
                entity_to_rep[r["UP"]] = r["SM"]
                entities.append(r["UP"])
    else:  # PM — banda / energía secundaria
        if not pm_map:
            st.warning(_t(
                "This is a Market-Participant market (secondary band/energy). "
                "Provide pm_map (e.g. GNERA→GNE); falling back to SM2 (likely wrong).",
                "Mercado de Participante del Mercado (banda/energía secundaria). "
                "Pasa pm_map (p.ej. GNERA→GNE); de momento uso el SM2 (probablemente incorrecto)."))
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

    # Aviso de coste
    with st.expander(_t("Estimated query cost (dry-run)",
                        "Coste estimado de la consulta (dry-run)"), expanded=False):
        try:
            gb = _dry_run_gb(mkt, entities, d_ini, d_fin)
            st.write(_t(f"Bytes to scan: **{gb:.3f} GB** (~{gb*6.25:.4f} € beyond free TB).",
                        f"Bytes a escanear: **{gb:.3f} GB** (~{gb*6.25:.4f} € fuera del TB gratis)."))
        except Exception as e:
            st.caption(str(e))

    if not st.button(_t("Compare offers", "Comparar ofertas"), type="primary"):
        return

    with st.spinner(_t("Querying BigQuery…", "Consultando BigQuery…")):
        df_blocks = (_q_interleaved if mkt["interleaved"] else _q_simple)(
            mkt, entities, d_ini, d_fin)
        metrics = _metrics(df_blocks, mkt, entity_to_rep)

    if metrics.empty:
        st.warning(_t(
            "No offer data for that selection/period. I90 is published at D+90: "
            "try dates ~91+ days old.",
            "Sin datos de oferta para esa selección y período. Los I90 se publican "
            "a D+90: prueba fechas de hace ~91 días o más."))
        return

    # Tabla + gráficos
    st.dataframe(metrics, use_container_width=True, hide_index=True)
    g1, g2 = st.columns(2)
    with g1:
        f = _fig_scatter(metrics, mkt)
        if f:
            st.plotly_chart(f, use_container_width=True)
    with g2:
        f = _fig_bars(metrics, mkt)
        if f:
            st.plotly_chart(f, use_container_width=True)

    # Intérprete IA
    _section("🤖", _t("AI Interpretation", "Interpretación con IA"))
    payload = _build_payload(metrics, mkt, d_ini, d_fin, reps_sel)
    md = _payload_md(payload)
    tab_b, tab_a = st.tabs([
        _t("Copy for chat (recommended)", "Copiar para chat (recomendado)"),
        _t("Call the API (advanced)", "Llamar a la API (avanzado)")])
    with tab_b:
        st.caption(_t("Copy and paste into a Claude chat for the reading.",
                      "Copia y pégalo en un chat con Claude para la lectura."))
        st.code(md, language="markdown")
        st.download_button(_t("Download .md", "Descargar .md"), md,
                           file_name=f"ofertas_{mkt_key}_{d_ini}_{d_fin}.md")
    with tab_a:
        st.caption(_t(
            "Requires `anthropic` + ANTHROPIC_API_KEY in secrets. Check egress to api.anthropic.com.",
            "Requiere `anthropic` + ANTHROPIC_API_KEY en secrets. Comprueba el egress a api.anthropic.com."))
        if st.button(_t("Interpret with Claude (API)", "Interpretar con Claude (API)")):
            try:
                with st.spinner("Claude…"):
                    st.markdown(_call_claude(payload))
            except Exception as e:
                st.error(str(e))


# ==============================================================================
# INTEGRACIÓN EN app.py  (4 pasos)
# ==============================================================================
"""
1) Import junto a los demás (sobre la línea 15, donde importas unit_explorer):

    from representantes_explorer import (
        render_representantes,
        set_bq as set_rep_bq,
        set_helpers as set_rep_helpers,
    )

2) Setup, justo donde ya haces set_loader/set_helpers del unit_explorer
   (sobre la línea 430-432). set_rep_bq(None,...) hace que el módulo cree el
   cliente solo, desde st.secrets['gcp_service_account']:

    set_rep_bq(client=None, project="miguel-energia", dataset="red_electrica_data")
    set_rep_helpers(metric_card=metric_card, section_header=section_header,
                    base_layout=base_layout, t=t)

3) Nueva entrada de menú (sobre las líneas 443-445, junto a name_explorer):

    name_repofertas = t("🏛️ Agent Offers", "🏛️ Ofertas Representantes")
    menu_options = [name_main, name_mra, name_rt5, name_gnera, name_verbund,
                    name_evo, name_supply, name_portfolio, name_explorer,
                    name_repofertas]

4) Bloque de render al final, tras el `elif seleccion_menu == name_explorer:`
   (sobre la línea 2817):

    elif seleccion_menu == name_repofertas:
        render_representantes(
            start_date, end_date,
            pm_map={"GNERA": "GNE", "AXPO IBERIA": "AXP"},  # ajusta a tus reps
        )
        gc.collect()
"""

# Prueba aislada: `streamlit run representantes_explorer.py`
if __name__ == "__main__":
    st.set_page_config(page_title="Comparador de ofertas", layout="wide")
    set_bq()  # crea cliente desde secrets
    render_representantes(dt.date.today() - dt.timedelta(days=97),
                          dt.date.today() - dt.timedelta(days=91))
