# -*- coding: utf-8 -*-
"""
i90_qh_explorer.py — Análisis operativo cuartohorario I90DIA  (v2 · BigQuery)
==============================================================================

Réplica interactiva del análisis de i90_analisis_flexible.py / HTML estático,
como módulo del dashboard (patrón unit_explorer / representantes_explorer).

FUENTE: tablas raw de BigQuery pobladas por i90-fetch-data y ofertas-fetch-data
(dataset red_electrica_data). Dos familias de esquema:

  · RESULTADO (dia01/02/19/20/21/26/36 programas; dia03/08 activaciones;
    dia09/10 precios casación; dia07 mFRR):
        DELIVERY_DATE (TIMESTAMP QH) · PROGRAMMING_UNIT · VALUE_MWH /
        VALUE_EUR_PER_MWH · REDISPATCH · DIRECTION
  · OFERTA (dia17/22/41/23 PDBF; dia32/31/42/24 TR; dia15 mFRR):
        DELIVERY_DATE (TIMESTAMP QH) · ENTITY · BLOCK · VALUE_MW · VALUE_EUR

Convención: oferta en MW por QH; casado/activado en MWh por QH
→ oferta comparable = MW × 0.25.

Vistas: Programas · RRTT PDBF · RRTT TR · mFRR · Resumen periodo.
Degradación elegante: tabla ausente o vacía → la serie no se pinta y se
lista en el expander de cobertura. Nunca rompe la página.

Integración en app.py:
    from i90_qh_explorer import render_i90_qh, set_bq_qh, set_helpers_qh
    set_bq_qh(project="miguel-energia", dataset="red_electrica_data")
    set_helpers_qh(t=t, section_header=section_header)
    ...
    elif seleccion_menu == name_qh:
        render_i90_qh(start_date, end_date, default_ups=['PEVER'])
"""

import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ==============================================================================
# CONFIG / HOOKS
# ==============================================================================
_BQ = {"project": "miguel-energia", "dataset": "red_electrica_data"}
_HELPERS = {}

RESULT_TABLES = {
    "pdbf": "i90_dia26_hourly_programming_result_pbf_raw",
    "pvp":  "i90_dia01_hourly_programming_result_pvp_raw",
    "p48":  "i90_dia02_programming_result_p48_raw",
    "phf1": "i90_dia19_hourly_programming_result_phf1_raw",
    "phf2": "i90_dia20_hourly_programming_result_phf2_raw",
    "phf3": "i90_dia21_hourly_programming_result_phf3_raw",
    "phfc": "i90_dia36_hourly_programming_result_phfc_raw",
}
ACT_TABLES = {"pdbf": "i90_dia03_resolution_restrictions_daily_market_results_raw",
              "tr":   "i90_dia08_real_time_restrictions_results_raw"}
PRICE_TABLES = {"pdbf": "i90_dia09_resolution_restrictions_daily_market_prices_raw",
                "tr":   "i90_dia10_real_time_restrictions_prices_raw"}
MFRR_E_TABLE = "i90_dia07_tertiary_market_energy_allocated_results_raw"
OFFER_TABLES = {
    ("pdbf", "sub", "mw"): "i90_dia17_rrtt_pdbf_offer_up_mw_raw",
    ("pdbf", "sub", "pr"): "i90_dia22_rrtt_pdbf_offer_up_price_raw",
    ("pdbf", "baj", "mw"): "i90_dia41_rrtt_pdbf_offer_dn_mw_raw",
    ("pdbf", "baj", "pr"): "i90_dia23_rrtt_pdbf_offer_dn_price_raw",
    ("tr",   "sub", "mw"): "i90_dia32_rrtt_tr_offer_up_mw_raw",
    ("tr",   "sub", "pr"): "i90_dia31_rrtt_tr_offer_up_price_raw",
    ("tr",   "baj", "mw"): "i90_dia42_rrtt_tr_offer_dn_mw_raw",
    ("tr",   "baj", "pr"): "i90_dia24_rrtt_tr_offer_dn_price_raw",
}
MFRR_OFFER_TABLE = "i90_dia15_tertiary_offer_raw"

SPOT_TABLE, SPOT_INDICATOR = "precios_esios", 600

# Paleta (tema claro del dashboard)
C_BLOCKS = ["#2563EB", "#7C3AED", "#0891B2", "#D97706", "#DB2777",
            "#059669", "#4F46E5", "#B45309", "#0D9488", "#9333EA"]
C_CAS, C_CASPR, C_SPOT = "#DC2626", "#F59E0B", "#94A3B8"
C_PROG = {"pdbf": "#64748B", "pvp": "#A78BFA", "phf1": "#93C5FD",
          "phf2": "#60A5FA", "phf3": "#3B82F6", "phfc": "#1D4ED8",
          "p48": "#0F172A", "rt1": "#DC2626", "f2": "#F59E0B",
          "mfrr": "#059669"}


def set_bq_qh(project=None, dataset=None):
    if project: _BQ["project"] = project
    if dataset: _BQ["dataset"] = dataset


def set_helpers_qh(t=None, section_header=None):
    if t:              _HELPERS["t"] = t
    if section_header: _HELPERS["section_header"] = section_header


def _t(en, es):
    fn = _HELPERS.get("t")
    return fn(en, es) if fn else es


def _section(icon, title):
    fn = _HELPERS.get("section_header")
    if fn: fn(icon, title)
    else:  st.markdown(f"### {icon} {title}")


# ==============================================================================
# BIGQUERY
# ==============================================================================
@st.cache_resource(show_spinner=False)
def _client():
    from google.cloud import bigquery
    try:
        from google.oauth2 import service_account
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(info)
        return bigquery.Client(project=_BQ["project"], credentials=creds)
    except Exception:
        return bigquery.Client(project=_BQ["project"])  # ADC


def _jc(d_ini, d_fin, ups=None):
    from google.cloud import bigquery
    params = [bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
              bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin)]
    if ups is not None:
        params.append(bigquery.ArrayQueryParameter("ups", "STRING", list(ups)))
    return bigquery.QueryJobConfig(query_parameters=params)


@st.cache_data(ttl=1800, show_spinner=False)
def _run(sql: str, d_ini: dt.date, d_fin: dt.date, ups: tuple):
    """Ejecuta una query parametrizada. DataFrame vacío si falla (tabla
    ausente, columna distinta…), para degradar sin romper."""
    try:
        df = _client().query(sql, job_config=_jc(d_ini, d_fin, ups)) \
            .to_dataframe()
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


def _tbl(name):
    return f"`{_BQ['project']}.{_BQ['dataset']}.{name}`"


# ── Queries por familia ───────────────────────────────────────────────────────
def q_program(table, d_ini, d_fin, ups):
    """Programas / mFRR energía: serie QH sumada sobre las UPs elegidas."""
    sql = f"""
        SELECT DELIVERY_DATE AS ts, SUM(VALUE_MWH) AS v
        FROM {_tbl(table)}
        WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
          AND PROGRAMMING_UNIT IN UNNEST(@ups) AND VALUE_MWH IS NOT NULL
        GROUP BY ts ORDER BY ts"""
    return _run(sql, d_ini, d_fin, tuple(ups))


def q_activations(kind, d_ini, d_fin, ups):
    """DIA03/08 → serie QH por grupo RT1 (REDISPATCH UP*) / F2 (ECO)."""
    sql = f"""
        SELECT DELIVERY_DATE AS ts,
               CASE WHEN UPPER(REDISPATCH) LIKE 'UP%' THEN 'RT1'
                    WHEN UPPER(REDISPATCH) = 'ECO'    THEN 'F2' END AS grp,
               SUM(VALUE_MWH) AS v
        FROM {_tbl(ACT_TABLES[kind])}
        WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
          AND PROGRAMMING_UNIT IN UNNEST(@ups) AND VALUE_MWH IS NOT NULL
        GROUP BY ts, grp HAVING grp IS NOT NULL ORDER BY ts"""
    return _run(sql, d_ini, d_fin, tuple(ups))


def q_clearing(kind, d_ini, d_fin, ups):
    """DIA09/10 → precio casación QH por grupo rt1_sub / f2_baj."""
    sql = f"""
        SELECT DELIVERY_DATE AS ts,
               CASE WHEN UPPER(REDISPATCH) LIKE 'UP%'
                         AND UPPER(DIRECTION) LIKE 'SUB%' THEN 'rt1_sub'
                    WHEN UPPER(REDISPATCH) = 'ECO'
                         AND UPPER(DIRECTION) LIKE 'BAJ%' THEN 'f2_baj'
               END AS grp,
               AVG(VALUE_EUR_PER_MWH) AS v
        FROM {_tbl(PRICE_TABLES[kind])}
        WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
          AND PROGRAMMING_UNIT IN UNNEST(@ups)
          AND VALUE_EUR_PER_MWH IS NOT NULL
        GROUP BY ts, grp HAVING grp IS NOT NULL ORDER BY ts"""
    return _run(sql, d_ini, d_fin, tuple(ups))


def q_offer_blocks(table, field, d_ini, d_fin, ups):
    """Ofertas por bloque: MW sumados o precio medio por (ts, BLOCK)."""
    agg = "SUM(VALUE_MW)" if field == "mw" else "AVG(VALUE_EUR)"
    notnull = "VALUE_MW" if field == "mw" else "VALUE_EUR"
    sql = f"""
        SELECT DELIVERY_DATE AS ts, BLOCK AS blk, {agg} AS v
        FROM {_tbl(table)}
        WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
          AND ENTITY IN UNNEST(@ups) AND {notnull} IS NOT NULL
        GROUP BY ts, blk ORDER BY ts"""
    return _run(sql, d_ini, d_fin, tuple(ups))


@st.cache_data(ttl=3600, show_spinner=False)
def _load_up_master():
    sql = f"""
        SELECT UP, Tech, Power_MW,
               Sujeto_del_Mercado AS SM
        FROM {_tbl('programming_units_external_table_latest')}"""
    try:
        df = _client().query(sql).to_dataframe()
        df["Power_MW"] = pd.to_numeric(df["Power_MW"], errors="coerce")
        return df.drop_duplicates("UP")
    except Exception:
        return pd.DataFrame(columns=["UP", "Tech", "Power_MW", "SM"])


@st.cache_data(ttl=3600, show_spinner=False)
def _load_spot(d_ini, d_fin):
    """Spot QH desde precios_esios (indicador 600). None si el esquema
    no coincide — el overlay simplemente se omite."""
    for dtcol, vcol in (("datetime", "value"), ("Datetime", "Value"),
                        ("fecha", "valor")):
        sql = f"""
            SELECT {dtcol} AS ts, {vcol} AS price
            FROM {_tbl(SPOT_TABLE)}
            WHERE indicator_id = {SPOT_INDICATOR}
              AND DATE({dtcol}) BETWEEN @d_ini AND @d_fin
            ORDER BY ts"""
        df = _run(sql, d_ini, d_fin, tuple())
        if not df.empty:
            return df
    return None


# ==============================================================================
# GRÁFICOS
# ==============================================================================
def _lay(ytitle, ytitle2=None, height=380, title=None):
    lay = dict(paper_bgcolor="#ffffff", plot_bgcolor="#FBFCFE",
               font=dict(family="Inter", color="#46556B", size=11),
               margin=dict(l=10, r=10, t=42, b=10), height=height,
               legend=dict(orientation="h", yanchor="top", y=-0.18, x=0),
               hovermode="x unified",
               yaxis=dict(title=ytitle, gridcolor="#E3E8F0"),
               xaxis=dict(gridcolor="#E3E8F0"))
    if ytitle2:
        lay["yaxis2"] = dict(title=ytitle2, overlaying="y", side="right",
                             showgrid=False)
    if title:
        lay["title"] = dict(text=title, font=dict(size=12, color="#13233B"))
    return lay


_GRID = {"idx": None}   # malla QH del periodo activo (la fija render_i90_qh)


def _set_grid(d_ini: dt.date, d_fin: dt.date):
    _GRID["idx"] = pd.date_range(pd.Timestamp(d_ini),
                                 pd.Timestamp(d_fin) + pd.Timedelta(days=1),
                                 freq="15min", inclusive="left")


def _on_grid(d: pd.DataFrame):
    """Serie [ts, v] reindexada a la malla QH completa: los QH sin dato
    quedan como NaN y connectgaps=False rompe la línea (sin rectas falsas)."""
    grid = _GRID["idx"]
    if grid is None or d.empty:
        return d["ts"], d["v"]
    s = d.drop_duplicates("ts").set_index("ts")["v"].reindex(grid)
    return grid, s.to_numpy()


def _add_blocks(fig, df_blk, to_mwh=False, prefix=""):
    if df_blk.empty:
        return False
    blks = sorted(df_blk["blk"].unique(),
                  key=lambda b: int("".join(filter(str.isdigit, str(b))) or 99))
    for i, b in enumerate(blks):
        g = df_blk[df_blk["blk"] == b]
        x, y = _on_grid(g)
        if to_mwh:
            y = y * 0.25
        fig.add_trace(go.Scatter(x=x, y=y, name=f"{prefix}{b}",
                                 line=dict(width=1.4,
                                           color=C_BLOCKS[i % len(C_BLOCKS)]),
                                 connectgaps=False))
    return True


def _add_series(fig, df, name, color, width=2.0, dash=None, yaxis=None,
                grp=None):
    d = df if grp is None else df[df["grp"] == grp]
    if d.empty:
        return False
    kw = dict(yaxis=yaxis) if yaxis else {}
    x, y = _on_grid(d)
    fig.add_trace(go.Scatter(x=x, y=y, name=name,
                             line=dict(width=width, color=color, dash=dash),
                             connectgaps=False, **kw))
    return True


def _add_spot(fig, spot, yaxis="y2"):
    if spot is not None and not spot.empty:
        fig.add_trace(go.Scatter(x=spot["ts"], y=spot["price"], name="Spot",
                                 yaxis=yaxis,
                                 line=dict(width=1.2, color=C_SPOT,
                                           dash="dash")))


def _panel_mw(df_blk, df_act, act_grp, act_name, df_pr, pr_grp, spot, title):
    fig = go.Figure()
    has = _add_blocks(fig, df_blk, to_mwh=True, prefix="Of.")
    has |= _add_series(fig, df_act, act_name, C_CAS, grp=act_grp)
    haspr = _add_series(fig, df_pr, _t("Clearing €", "Precio casación"),
                        C_CASPR, width=1.6, dash="dot", yaxis="y2",
                        grp=pr_grp)
    _add_spot(fig, spot)
    fig.update_layout(**_lay("MWh/QH",
                             "€/MWh" if (haspr or spot is not None) else None,
                             title=title))
    return fig if has or haspr else None


def _panel_pr(df_blk_pr, df_pr, pr_grp, spot, title):
    fig = go.Figure()
    has = _add_blocks(fig, df_blk_pr, prefix="")
    has |= _add_series(fig, df_pr, _t("Clearing", "Casación"), C_CAS,
                       grp=pr_grp)
    _add_spot(fig, spot, yaxis=None or "y")
    fig.update_layout(**_lay("€/MWh", title=title))
    return fig if has else None


def _show(fig, missing_msg):
    if fig is None:
        st.info(missing_msg)
    else:
        st.plotly_chart(fig, use_container_width=True)


# ==============================================================================
# RENDER PRINCIPAL
# ==============================================================================
def render_i90_qh(start_date=None, end_date=None, default_ups=None):
    _section("🧭", _t("I90 QH Explorer — offers vs matched",
                     "Explorador QH I90 — ofertas vs casado"))

    today = dt.date.today()
    d_ini = start_date or (today - dt.timedelta(days=98))
    d_fin = end_date or (today - dt.timedelta(days=92))
    if isinstance(d_ini, dt.datetime): d_ini = d_ini.date()
    if isinstance(d_fin, dt.datetime): d_fin = d_fin.date()

    master = _load_up_master()

    c1, c2 = st.columns([1.2, 3])
    with c1:
        rng = st.date_input(_t("Period", "Periodo"), value=(d_ini, d_fin),
                            key="qh_rng")
        if isinstance(rng, tuple) and len(rng) == 2:
            d_ini, d_fin = rng
        if (d_fin - d_ini).days + 1 > 14:
            st.warning(_t("Max 14 days at QH detail — trimmed.",
                          "Máximo 14 días a detalle QH — recortado."))
            d_fin = d_ini + dt.timedelta(days=13)
    with c2:
        ups_avail = sorted(master["UP"].dropna().unique().tolist()) \
            if not master.empty else []
        dflt = [u for u in (default_ups or []) if u in ups_avail]
        ups_sel = st.multiselect(
            _t("Production Units (aggregated if several)",
               "Unidades (se agregan si eliges varias)"),
            options=ups_avail or (default_ups or []),
            default=dflt or (ups_avail[:1] if ups_avail else []),
            key="qh_ups")
        if not master.empty and ups_sel:
            info = master[master["UP"].isin(ups_sel)]
            st.caption(" · ".join(
                f"{r.UP} ({r.Tech}, {r.Power_MW:.0f} MW, {r.SM})"
                if pd.notna(r.Power_MW) else f"{r.UP} ({r.Tech}, {r.SM})"
                for r in info.itertuples()))

    if not ups_sel:
        st.info(_t("Select at least one UP.", "Selecciona al menos una UP."))
        return

    _set_grid(d_ini, d_fin)
    ups = tuple(sorted(ups_sel))
    missing = []

    with st.spinner(_t("Querying BigQuery…", "Consultando BigQuery…")):
        prog = {k: q_program(tbl, d_ini, d_fin, ups)
                for k, tbl in RESULT_TABLES.items()}
        act_pdbf = q_activations("pdbf", d_ini, d_fin, ups)
        act_tr   = q_activations("tr",   d_ini, d_fin, ups)
        pr_pdbf  = q_clearing("pdbf", d_ini, d_fin, ups)
        pr_tr    = q_clearing("tr",   d_ini, d_fin, ups)
        mfrr_e   = q_program(MFRR_E_TABLE, d_ini, d_fin, ups)
        offers = {k: q_offer_blocks(tbl, k[2], d_ini, d_fin, ups)
                  for k, tbl in OFFER_TABLES.items()}
        mfrr_mw = q_offer_blocks(MFRR_OFFER_TABLE, "mw", d_ini, d_fin, ups)
        mfrr_pr = q_offer_blocks(MFRR_OFFER_TABLE, "pr", d_ini, d_fin, ups)
        spot = _load_spot(d_ini, d_fin)

    for name, df in [("Programas " + k.upper(), v) for k, v in prog.items()] \
            + [("DIA03", act_pdbf), ("DIA08", act_tr), ("DIA09", pr_pdbf),
               ("DIA10", pr_tr), ("DIA07", mfrr_e), ("DIA15", mfrr_mw)] \
            + [(f"DIA {k}", v) for k, v in offers.items()]:
        if df.empty:
            missing.append(str(name))

    if all(df.empty for df in prog.values()) and act_pdbf.empty \
            and all(df.empty for df in offers.values()):
        st.error(_t("No data in BigQuery for this period/UPs.",
                    "Sin datos en BigQuery para este periodo/UPs."))
        return

    if missing:
        with st.expander(_t("⚠️ Coverage: empty sources this period",
                            "⚠️ Cobertura: fuentes vacías en el periodo")):
            st.write(", ".join(missing))
    if spot is None:
        st.caption(_t("Spot overlay unavailable.",
                      "Overlay spot no disponible."))

    no_data = _t("No data for this panel in the period.",
                 "Sin datos para este panel en el periodo.")

    tab_prog, tab_pdbf, tab_tr, tab_mfrr, tab_res = st.tabs([
        _t("Programs", "Programas"), "RRTT PDBF",
        _t("RRTT Real Time", "RRTT Tiempo Real"), "mFRR",
        _t("Period summary", "Resumen periodo")])

    # ── 1 · PROGRAMAS ────────────────────────────────────────────────────────
    with tab_prog:
        prog_lbl = {"pdbf": "PDBF", "pvp": "PVP", "phf1": "PHF1",
                    "phf2": "PHF2", "phf3": "PHF3", "phfc": "PHFC",
                    "p48": "P48"}
        sel = st.multiselect(_t("Programs to plot", "Programas a representar"),
                             options=list(prog_lbl.values()),
                             default=["PDBF", "PHFC", "P48"],
                             key="qh_progsel")
        show_act = st.checkbox(
            _t("Overlay activations (RT1 / F2 / mFRR)",
               "Superponer activaciones (RT1 / F2 / mFRR)"),
            value=True, key="qh_act")
        fig = go.Figure()
        inv = {v: k for k, v in prog_lbl.items()}
        for lbl in sel:
            k = inv[lbl]
            _add_series(fig, prog[k], lbl, C_PROG[k],
                        width=2.2 if k == "p48" else 1.4)
        if show_act:
            _add_series(fig, act_pdbf, "RT1", C_PROG["rt1"], width=1.3,
                        dash="dot", grp="RT1")
            _add_series(fig, act_pdbf, "RRTT F2", C_PROG["f2"], width=1.3,
                        dash="dot", grp="F2")
            _add_series(fig, mfrr_e, "mFRR", C_PROG["mfrr"], width=1.3,
                        dash="dot")
        fig.update_layout(**_lay("MWh/QH", height=430))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(_t("Program cascade at QH level; activations dotted.",
                      "Cascada de programas a nivel QH; activaciones en "
                      "punteado."))

    # ── 2 · RRTT PDBF ────────────────────────────────────────────────────────
    with tab_pdbf:
        ca, cb = st.columns(2)
        with ca:
            _show(_panel_mw(offers[("pdbf", "sub", "mw")], act_pdbf, "RT1",
                            _t("Matched RT1", "Casado RT1"),
                            pr_pdbf, "rt1_sub", spot,
                            _t("UP · Offer (DIA17) vs matched (DIA03·RT1)",
                               "SUBIR · Oferta (DIA17) vs casado (DIA03·RT1)")),
                  no_data)
            _show(_panel_pr(offers[("pdbf", "sub", "pr")], pr_pdbf, "rt1_sub",
                            spot,
                            _t("UP · Offer price (DIA22) vs clearing (DIA09)",
                               "SUBIR · Precio oferta (DIA22) vs casación "
                               "(DIA09)")), no_data)
        with cb:
            _show(_panel_mw(offers[("pdbf", "baj", "mw")], act_pdbf, "F2",
                            _t("Matched F2", "Casado F2"),
                            pr_pdbf, "f2_baj", spot,
                            _t("DOWN · Offer (DIA41) vs matched (DIA03·F2)",
                               "BAJAR · Oferta (DIA41) vs casado (DIA03·F2)")),
                  no_data)
            _show(_panel_pr(offers[("pdbf", "baj", "pr")], pr_pdbf, "f2_baj",
                            spot,
                            _t("DOWN · Offer price (DIA23) vs clearing (DIA09)",
                               "BAJAR · Precio oferta (DIA23) vs casación "
                               "(DIA09)")), no_data)

    # ── 3 · RRTT TIEMPO REAL ─────────────────────────────────────────────────
    with tab_tr:
        ca, cb = st.columns(2)
        with ca:
            _show(_panel_mw(offers[("tr", "sub", "mw")], act_tr, "RT1",
                            _t("Activated RT1", "Activado RT1"),
                            pr_tr, "rt1_sub", spot,
                            _t("UP · TR offer (DIA32) vs activated (DIA08)",
                               "SUBIR · Oferta TR (DIA32) vs activado "
                               "(DIA08)")), no_data)
            _show(_panel_pr(offers[("tr", "sub", "pr")], pr_tr, "rt1_sub",
                            spot,
                            _t("UP · TR offer price (DIA31) vs clearing "
                               "(DIA10)",
                               "SUBIR · Precio oferta TR (DIA31) vs casación "
                               "(DIA10)")), no_data)
        with cb:
            _show(_panel_mw(offers[("tr", "baj", "mw")], act_tr, "F2",
                            _t("Activated F2", "Activado F2"),
                            pr_tr, "f2_baj", spot,
                            _t("DOWN · TR offer (DIA42) vs activated (DIA08)",
                               "BAJAR · Oferta TR (DIA42) vs activado "
                               "(DIA08)")), no_data)
            _show(_panel_pr(offers[("tr", "baj", "pr")], pr_tr, "f2_baj",
                            spot,
                            _t("DOWN · TR offer price (DIA24) vs clearing "
                               "(DIA10)",
                               "BAJAR · Precio oferta TR (DIA24) vs casación "
                               "(DIA10)")), no_data)

    # ── 4 · mFRR ─────────────────────────────────────────────────────────────
    with tab_mfrr:
        ca, cb = st.columns(2)
        with ca:
            _show(_panel_mw(mfrr_mw, mfrr_e.assign(grp="T"), "T",
                            _t("Activated", "Activado"), pd.DataFrame(),
                            None, spot,
                            _t("mFRR · Offer (DIA15) vs activated (DIA07)",
                               "mFRR · Oferta (DIA15) vs activado (DIA07)")),
                  no_data)
        with cb:
            _show(_panel_pr(mfrr_pr, pd.DataFrame(), None, spot,
                            _t("mFRR · Offer price by block (DIA15)",
                               "mFRR · Precio oferta por bloque (DIA15)")),
                  no_data)

    # ── 5 · RESUMEN PERIODO ──────────────────────────────────────────────────
    with tab_res:
        def _daily(df, grp=None):
            d = df if grp is None else df[df["grp"] == grp]
            if d.empty:
                return pd.Series(dtype=float)
            return d.groupby(d["ts"].dt.date)["v"].sum()

        res = pd.DataFrame({
            "P48 (MWh)":    _daily(prog["p48"]),
            "RT1 (MWh)":    _daily(act_pdbf, "RT1"),
            "F2 (MWh)":     _daily(act_pdbf, "F2"),
            "TR RT1 (MWh)": _daily(act_tr, "RT1"),
            "TR F2 (MWh)":  _daily(act_tr, "F2"),
            "mFRR (MWh)":   _daily(mfrr_e),
        }).fillna(0.0)
        res.index.name = _t("Day", "Día")
        st.dataframe(res.style.format("{:,.1f}"), use_container_width=True)

        fig = go.Figure()
        for col, color in (("RT1 (MWh)", C_PROG["rt1"]),
                           ("F2 (MWh)", C_PROG["f2"]),
                           ("TR RT1 (MWh)", "#7C3AED"),
                           ("TR F2 (MWh)", "#0891B2"),
                           ("mFRR (MWh)", C_PROG["mfrr"])):
            fig.add_trace(go.Bar(x=res.index.astype(str), y=res[col],
                                 name=col, marker_color=color))
        fig.update_layout(barmode="group",
                          **_lay("MWh/" + _t("day", "día"), height=360))
        st.plotly_chart(fig, use_container_width=True)
