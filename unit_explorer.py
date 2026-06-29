# -*- coding: utf-8 -*-
"""
unit_explorer.py — Lupa por Unidad de Programación (Unit Explorer)
==================================================================

Sección drop-in para el dashboard de Servicios de Ajuste.
Lee los parquets HORARIOS `allh_{YYYY-MM}.parquet` (grano UP x Day x hour)
ya existentes en GCS `dashboard-energia-data`, filtra a UNA sola UP y produce
una vista de profundidad por unidad:

  1. KPIs de cabecera        (Profit total, captura €/MWh, energía neta, mercado top)
  2. Waterfall de P&L €      (cómo se forma el beneficio mercado a mercado)
  3. Heatmap Día x Hora      (profit / energía / €-MWh, selector)
  4. Perfil horario 24h      (curva media de profit y energía por hora del día)
  5. Evolución diaria        (stacked area del profit por mercado, día a día)
  6. Tabla por mercado       (energía, ingreso, profit, €/MWh, % total, días activos)

Diseño:
  - Sólo carga los meses del rango pedido, y SOLO para la UP elegida -> RAM mínima.
  - No toca el `allh` diario que ya tiene la app en memoria.
  - Defensivo: detecta qué columnas existen; rellena con 0 las que falten.
  - Reutiliza tus helpers (metric_card, section_header, base_layout, t, colores).

Integración (3 líneas en app.py): ver bloque al final de este fichero.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go


# ==============================================================================
# CONFIGURACIÓN DE MERCADOS  (coherente con la sección MRA de app.py)
# ==============================================================================
# Orden = orden del waterfall (P48 spot primero, AASS después, intra al final).
# label_es / label_en para la versión bilingüe. color = paleta de la app.
MARKETS = [
    # key_profit     key_energy      label_es          label_en          color
    ("Profit_p48",   "Energy_p48",   "Spot (P48)",     "Spot (P48)",     "#2563eb"),
    ("Profit_rt",    "Energy_rt",    "RRTT F2",        "RRTT F2",        "#0891b2"),
    ("Profit_tr_s",  "Energy_tr",    "RT5",            "RT5",            "#7c3aed"),
    ("Profit_t",     "Energy_t",     "Terciaria",      "Tertiary",       "#d97706"),
    ("Profit_rr",    "Energy_rr",    "RR",             "RR",             "#65a30d"),
    ("Profit_b",     None,           "Banda Sec.",     "Sec. Band",      "#059669"),
    ("Profit_se",    "Energy_se",    "Energía Sec.",   "Sec. Energy",    "#ea580c"),
    ("Profit_i",     "Energy_i",     "Intradiario",    "Intraday",       "#dc2626"),
]

# Mercados de ajuste (excluye spot P48) para totales "AASS".
AASS_PROFIT_KEYS = ["Profit_rt", "Profit_tr_s", "Profit_t",
                    "Profit_rr", "Profit_b", "Profit_se", "Profit_i"]

C_POS = "#059669"
C_NEG = "#dc2626"
C_GRID = "#e2e8f0"


# ==============================================================================
# CARGA DE DATOS HORARIOS  (sólo la UP pedida, sólo los meses del rango)
# ==============================================================================
def _months_in_range(start_date, end_date):
    """Lista de strings 'YYYY-MM' que cubren el rango inclusivo."""
    pr = pd.period_range(
        start=pd.Timestamp(start_date).to_period("M"),
        end=pd.Timestamp(end_date).to_period("M"),
        freq="M",
    )
    return [str(p) for p in pr]


@st.cache_data(ttl=3600, show_spinner=False)
def load_unit_hourly(up_code, start_date_str, end_date_str, _loader_key="gcs"):
    """
    Carga el horario de UNA UP en el rango pedido.

    Devuelve un DataFrame (Day, hour, + columnas de Profit_/Energy_/Rev_)
    ya filtrado a la UP y al rango exacto de días.

    `_loader_key` se ignora dentro pero rompe el cache si cambia el backend.
    El acceso a GCS se hace vía el `load_parquet` que se inyecta por
    set_loader() — ver más abajo.
    """
    loader = _LOADERS.get("load_parquet")
    if loader is None:
        return pd.DataFrame()

    months = _months_in_range(start_date_str, end_date_str)
    frames = []
    for ym in months:
        fname = f"allh_{ym}.parquet"
        try:
            df_m = loader(fname)
        except Exception:
            df_m = pd.DataFrame()
        if df_m is None or df_m.empty or "UP" not in df_m.columns:
            continue
        # Filtrar a la UP ANTES de hacer nada más -> recorta memoria al máximo.
        df_m = df_m.loc[df_m["UP"] == up_code]
        if not df_m.empty:
            frames.append(df_m)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["Day"] = pd.to_datetime(df["Day"])
    sd = pd.Timestamp(start_date_str)
    ed = pd.Timestamp(end_date_str)
    df = df.loc[(df["Day"] >= sd) & (df["Day"] <= ed)].copy()
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def list_units_in_range(start_date_str, end_date_str, _loader_key="gcs"):
    """
    Lista de UPs disponibles en el primer mes del rango (rápido, un solo fichero).
    Suficiente para poblar el selector sin cargar todo.
    """
    loader = _LOADERS.get("load_parquet")
    if loader is None:
        return []
    ym = _months_in_range(start_date_str, end_date_str)[0]
    try:
        df = loader(f"allh_{ym}.parquet")
    except Exception:
        df = pd.DataFrame()
    if df is None or df.empty or "UP" not in df.columns:
        return []
    return sorted(df["UP"].dropna().unique().tolist())


# Inyección de dependencias (loader + helpers de app.py) para no duplicar código.
_LOADERS = {}
_HELPERS = {}


def set_loader(load_parquet):
    """Inyecta la función load_parquet de gcs_loader."""
    _LOADERS["load_parquet"] = load_parquet


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
        template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
        font=dict(family="Inter, sans-serif", color="#475569", size=12),
        margin=dict(l=10, r=10, t=45, b=10),
    )
    base.update(extra)
    return base


# ==============================================================================
# UTILIDADES DE CÁLCULO
# ==============================================================================
def _ensure_cols(df, keys):
    """Garantiza que existan las columnas numéricas (0.0 si faltan)."""
    for k in keys:
        if k is None:
            continue
        if k not in df.columns:
            df[k] = 0.0
        else:
            df[k] = pd.to_numeric(df[k], errors="coerce").fillna(0.0)
    return df


def _energy_base(df):
    """
    Energía base de captura = Energy_p48 - Energy_tr  (igual que la app).
    Evita divisiones por cero.
    """
    e_p48 = df["Energy_p48"].sum() if "Energy_p48" in df.columns else 0.0
    e_tr  = df["Energy_tr"].sum() if "Energy_tr" in df.columns else 0.0
    base = e_p48 - e_tr
    return base if abs(base) > 1e-9 else np.nan


def _lang_label(es, en):
    """Devuelve label en el idioma activo (heurística vía _t)."""
    return _t(en, es)


# ==============================================================================
# RENDER PRINCIPAL
# ==============================================================================
def render_unit_explorer(start_date, end_date, df_power=None,
                         default_up=None, ma_lookup=None):
    """
    Pinta la sección completa del Unit Explorer.

    Parámetros
    ----------
    start_date, end_date : datetime.date  (rango ya validado por la app)
    df_power : DataFrame opcional con ['UP','Power MW'] para mostrar potencia.
    default_up : str opcional, UP preseleccionada.
    ma_lookup : dict opcional {UP: MA} para enriquecer el selector.
    """
    _section("🔬", _lang_label("Explorador por Unidad — lupa de mercado",
                                "Unit Explorer — market magnifier"))

    start_str, end_str = str(start_date), str(end_date)

    # ---- Selector de UP -----------------------------------------------------
    ups = list_units_in_range(start_str, end_str)
    if not ups:
        st.warning(_lang_label(
            "No hay parquets horarios (allh_YYYY-MM) para este rango.",
            "No hourly parquets (allh_YYYY-MM) for this range."))
        return

    def _fmt(u):
        if ma_lookup and u in ma_lookup:
            return f"{u} · {ma_lookup[u]}"
        return u

    idx = ups.index(default_up) if (default_up in ups) else 0
    col_sel, col_metric = st.columns([2, 3])
    with col_sel:
        sel_up = st.selectbox(
            _lang_label("Unidad de Programación", "Programming Unit"),
            ups, index=idx, format_func=_fmt, key="ue_up",
        )

    # ---- Carga horaria de la UP --------------------------------------------
    with st.spinner(_lang_label("Cargando horario de la unidad…",
                                "Loading unit hourly data…")):
        df = load_unit_hourly(sel_up, start_str, end_str)

    if df.empty:
        st.warning(_lang_label("Sin datos para esta unidad en el rango.",
                               "No data for this unit in range."))
        return

    # Columnas a garantizar
    all_profit = [m[0] for m in MARKETS]
    all_energy = [m[1] for m in MARKETS if m[1]]
    df = _ensure_cols(df, all_profit + all_energy +
                      ["Energy_p48", "Energy_tr", "Rev_spot", "PBF"])

    # Si Profit_p48 viene a 0 pero hay Rev_spot, usar Rev_spot (igual que app)
    if df["Profit_p48"].sum() == 0 and df["Rev_spot"].sum() != 0:
        df["Profit_p48"] = df["Rev_spot"]

    # Potencia de la unidad (si se pasó)
    power_mw = None
    if df_power is not None and not df_power.empty:
        row = df_power.loc[df_power["UP"] == sel_up, "Power MW"]
        if not row.empty:
            power_mw = float(row.iloc[0])

    # ---- Totales por mercado ------------------------------------------------
    ebase = _energy_base(df)
    totals = {m[0]: float(df[m[0]].sum()) for m in MARKETS}
    profit_aass = sum(totals[k] for k in AASS_PROFIT_KEYS)
    profit_total = profit_aass + totals.get("Profit_p48", 0.0)
    energy_net = df["Energy_p48"].sum() if "Energy_p48" in df.columns else 0.0
    n_days = df["Day"].nunique()

    # Mercado dominante por |profit| dentro de AASS
    dom_key = max(AASS_PROFIT_KEYS, key=lambda k: abs(totals.get(k, 0)))
    dom_label = next((_lang_label(m[2], m[3]) for m in MARKETS if m[0] == dom_key),
                     dom_key)

    # ---- KPIs ---------------------------------------------------------------
    with col_metric:
        sub = sel_up
        if power_mw:
            sub += f" · {power_mw:,.0f} MW"
        st.markdown(
            f"<div style='padding-top:1.9rem;color:#64748b;font-size:0.85rem;'>"
            f"<b style='color:#1e293b;'>{sub}</b> · "
            f"{n_days} {_lang_label('días','days')} · "
            f"{df['Day'].min():%d-%b-%Y} → {df['Day'].max():%d-%b-%Y}</div>",
            unsafe_allow_html=True,
        )

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        _metric(_lang_label("Profit Total", "Total Profit"),
                f"{profit_total:,.0f}", unit=" €", positive=profit_total >= 0)
    with k2:
        _metric(_lang_label("Profit AASS", "AASS Profit"),
                f"{profit_aass:,.0f}", unit=" €", positive=profit_aass >= 0)
    with k3:
        cap = (profit_aass / ebase) if not np.isnan(ebase) else 0.0
        _metric(_lang_label("Captura AASS", "AASS Capture"),
                f"{cap:,.2f}", unit=" €/MWh", positive=cap >= 0)
    with k4:
        _metric(_lang_label("Energía neta", "Net Energy"),
                f"{energy_net:,.0f}", unit=" MWh")
    with k5:
        _metric(_lang_label("Mercado top", "Top market"), dom_label)

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- 1) WATERFALL de P&L ------------------------------------------------
    _render_waterfall(totals, ebase)

    # ---- 2) HEATMAP Día x Hora ---------------------------------------------
    _render_heatmap(df)

    # ---- 3) PERFIL HORARIO 24h + EVOLUCIÓN DIARIA --------------------------
    cprofile, cevo = st.columns(2)
    with cprofile:
        _render_hourly_profile(df)
    with cevo:
        _render_daily_stack(df)

    # ---- 4) TABLA por mercado ----------------------------------------------
    _render_market_table(df, ebase)


# ------------------------------------------------------------------------------
# COMPONENTES
# ------------------------------------------------------------------------------
def _render_waterfall(totals, ebase):
    _section("💧", _lang_label(
        "Formación del beneficio por mercado (€)",
        "Profit formation by market (€)"))

    show_unit = st.toggle(
        _lang_label("Mostrar en €/MWh", "Show in €/MWh"),
        value=False, key="ue_wf_unit")

    labels, values, colors = [], [], []
    for key, _e, es, en, color in MARKETS:
        v = totals.get(key, 0.0)
        if abs(v) < 1e-6:
            continue
        if show_unit and not np.isnan(ebase):
            v = v / ebase
        labels.append(_lang_label(es, en))
        values.append(v)
        colors.append(color)

    if not labels:
        st.info(_lang_label("Sin movimientos en el periodo.",
                            "No activity in the period."))
        return

    measures = ["relative"] * len(labels)
    labels.append(_lang_label("TOTAL", "TOTAL"))
    values.append(0)
    measures.append("total")

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=measures,
        x=labels,
        y=values,
        connector=dict(line=dict(color="#cbd5e1", width=1)),
        decreasing=dict(marker=dict(color=C_NEG)),
        increasing=dict(marker=dict(color=C_POS)),
        totals=dict(marker=dict(color="#1e293b")),
        text=[f"{v:,.0f}" if not show_unit else f"{v:,.2f}"
              for v in values[:-1]] + [""],
        textposition="outside",
        textfont=dict(size=11),
    ))
    unit_lbl = "€/MWh" if show_unit else "€"
    fig.update_layout(**_layout(
        height=380,
        yaxis_title=unit_lbl,
        showlegend=False,
    ))
    fig.update_yaxes(gridcolor=C_GRID, zerolinecolor="#94a3b8")
    st.plotly_chart(fig, use_container_width=True)


def _render_heatmap(df):
    _section("🗓️", _lang_label(
        "Patrón Día × Hora", "Day × Hour pattern"))

    metric = st.radio(
        _lang_label("Métrica", "Metric"),
        ["profit_aass", "profit_total", "energy", "eur_mwh"],
        horizontal=True, key="ue_hm_metric",
        format_func=lambda x: {
            "profit_aass":  _lang_label("Profit AASS (€)", "AASS Profit (€)"),
            "profit_total": _lang_label("Profit Total (€)", "Total Profit (€)"),
            "energy":       _lang_label("Energía (MWh)", "Energy (MWh)"),
            "eur_mwh":      _lang_label("Captura (€/MWh)", "Capture (€/MWh)"),
        }[x],
    )

    d = df.copy()
    if "hour" not in d.columns:
        st.info(_lang_label("No hay columna 'hour' en el horario.",
                            "No 'hour' column in hourly data."))
        return

    d["Profit_AASS"] = d[[k for k in AASS_PROFIT_KEYS if k in d.columns]].sum(axis=1)
    d["Profit_TOT"] = d["Profit_AASS"] + d.get("Profit_p48", 0)

    if metric == "profit_aass":
        d["val"] = d["Profit_AASS"]; cs = "RdYlGn"; agg = "sum"
    elif metric == "profit_total":
        d["val"] = d["Profit_TOT"]; cs = "RdYlGn"; agg = "sum"
    elif metric == "energy":
        d["val"] = d.get("Energy_p48", 0); cs = "Blues"; agg = "sum"
    else:  # eur_mwh
        e = d.get("Energy_p48", pd.Series(0, index=d.index)).replace(0, np.nan)
        d["val"] = d["Profit_AASS"] / e; cs = "RdYlGn"; agg = "mean"

    pivot = d.pivot_table(index="hour", columns="Day", values="val",
                          aggfunc=agg)
    pivot = pivot.sort_index()
    cols = [c.strftime("%d-%b") for c in pivot.columns]

    # Escala simétrica para profit/eur (verde-rojo centrado en 0)
    zmid = None
    if metric in ("profit_aass", "profit_total", "eur_mwh"):
        m = np.nanmax(np.abs(pivot.values)) if pivot.size else 1
        zmin, zmax, zmid = -m, m, 0
    else:
        zmin = zmax = None

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=cols,
        y=[f"{h:02d}h" for h in pivot.index],
        colorscale=cs,
        zmin=zmin, zmax=zmax, zmid=zmid,
        colorbar=dict(thickness=12, len=0.9),
        hovertemplate="%{x} · %{y}<br>%{z:,.1f}<extra></extra>",
    ))
    fig.update_layout(**_layout(
        height=460, xaxis_title=None, yaxis_title=None,
    ))
    fig.update_xaxes(showgrid=False, tickangle=-45)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)


def _render_hourly_profile(df):
    _section("🕐", _lang_label("Perfil horario medio (24h)",
                               "Average hourly profile (24h)"))
    if "hour" not in df.columns:
        st.info("—")
        return
    d = df.copy()
    d["Profit_AASS"] = d[[k for k in AASS_PROFIT_KEYS if k in d.columns]].sum(axis=1)
    g = d.groupby("hour").agg(
        profit=("Profit_AASS", "mean"),
        energy=("Energy_p48", "mean") if "Energy_p48" in d.columns else ("Profit_AASS", "size"),
    ).reset_index()

    fig = go.Figure()
    fig.add_bar(
        x=g["hour"], y=g["energy"], name=_lang_label("Energía media (MWh)", "Avg energy (MWh)"),
        marker_color="#cbd5e1", yaxis="y2", opacity=0.6,
    )
    fig.add_trace(go.Scatter(
        x=g["hour"], y=g["profit"], name=_lang_label("Profit AASS medio (€)", "Avg AASS profit (€)"),
        mode="lines+markers", line=dict(color="#2563eb", width=2.5),
        marker=dict(size=5),
    ))
    fig.update_layout(**_layout(
        height=340,
        yaxis=dict(title="€", gridcolor=C_GRID),
        yaxis2=dict(title="MWh", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.12, x=0),
        xaxis=dict(title=_lang_label("Hora", "Hour"), dtick=2),
    ))
    st.plotly_chart(fig, use_container_width=True)


def _render_daily_stack(df):
    _section("📈", _lang_label("Profit diario por mercado",
                               "Daily profit by market"))
    d = df.copy()
    agg = {m[0]: "sum" for m in MARKETS if m[0] in d.columns and m[0] != "Profit_p48"}
    g = d.groupby("Day").agg(agg).reset_index()

    fig = go.Figure()
    for key, _e, es, en, color in MARKETS:
        if key == "Profit_p48" or key not in g.columns:
            continue
        if g[key].abs().sum() < 1e-6:
            continue
        fig.add_trace(go.Scatter(
            x=g["Day"], y=g[key], name=_lang_label(es, en),
            mode="lines", stackgroup="one", line=dict(width=0.5, color=color),
            fillcolor=color, hovertemplate="%{y:,.0f} €<extra></extra>",
        ))
    fig.update_layout(**_layout(
        height=340,
        yaxis=dict(title="€", gridcolor=C_GRID),
        legend=dict(orientation="h", y=-0.25, x=0, font=dict(size=10)),
        xaxis=dict(title=None),
    ))
    st.plotly_chart(fig, use_container_width=True)


def _render_market_table(df, ebase):
    _section("📋", _lang_label("Desglose por mercado",
                               "Market breakdown"))
    rows = []
    profit_total = sum(float(df[m[0]].sum()) for m in MARKETS if m[0] in df.columns)
    for key, ekey, es, en, _c in MARKETS:
        if key not in df.columns:
            continue
        p = float(df[key].sum())
        if abs(p) < 1e-6 and (ekey is None or float(df.get(ekey, pd.Series([0])).sum()) == 0):
            continue
        e = float(df[ekey].sum()) if (ekey and ekey in df.columns) else np.nan
        eur_mwh = (p / ebase) if not np.isnan(ebase) else np.nan
        active = int((df.groupby("Day")[key].sum().abs() > 1e-6).sum())
        pct = (p / profit_total * 100) if abs(profit_total) > 1e-6 else 0
        rows.append({
            _lang_label("Mercado", "Market"): _lang_label(es, en),
            _lang_label("Energía (MWh)", "Energy (MWh)"): e,
            _lang_label("Profit (€)", "Profit (€)"): p,
            _lang_label("€/MWh", "€/MWh"): eur_mwh,
            _lang_label("% Total", "% Total"): pct,
            _lang_label("Días activos", "Active days"): active,
        })
    if not rows:
        st.info(_lang_label("Sin actividad.", "No activity."))
        return

    tbl = pd.DataFrame(rows)
    num_fmt = {c: "{:,.1f}" for c in tbl.columns if tbl[c].dtype != object}
    st.dataframe(
        tbl.style.format({
            _lang_label("Energía (MWh)", "Energy (MWh)"): "{:,.0f}",
            _lang_label("Profit (€)", "Profit (€)"): "{:,.0f}",
            _lang_label("€/MWh", "€/MWh"): "{:,.2f}",
            _lang_label("% Total", "% Total"): "{:,.1f}%",
        }).background_gradient(
            subset=[_lang_label("Profit (€)", "Profit (€)")],
            cmap="RdYlGn", vmin=-abs(tbl[_lang_label("Profit (€)", "Profit (€)")]).max(),
            vmax=abs(tbl[_lang_label("Profit (€)", "Profit (€)")]).max(),
        ),
        use_container_width=True, hide_index=True,
    )


# ==============================================================================
# CÓMO INTEGRARLO EN app.py  (3 pasos)
# ==============================================================================
"""
PASO 1 — import (junto a los otros imports, arriba):

    from unit_explorer import (
        render_unit_explorer, set_loader, set_helpers
    )

PASO 2 — inyección, justo DESPUÉS de definir metric_card/section_header/
base_layout/t y de importar load_parquet de gcs_loader (una vez, al arrancar):

    set_loader(load_parquet)
    set_helpers(metric_card=metric_card,
                section_header=section_header,
                base_layout=base_layout, t=t)

PASO 3 — nuevo item de menú + bloque de sección.

  (a) añade el nombre al menú:
        name_explorer = t("🔬 Unit Explorer", "🔬 Explorador Unidad")
        menu_options = [name_main, name_mra, name_rt5, name_gnera,
                        name_verbund, name_evo, name_supply,
                        name_portfolio, name_explorer]

  (b) al final de la cadena de secciones (tras el bloque name_portfolio):

        elif seleccion_menu == name_explorer:
            ma_lookup = (allh[['UP','MA']].dropna()
                         .drop_duplicates('UP').set_index('UP')['MA'].to_dict())
            render_unit_explorer(
                start_date, end_date,
                df_power=df_power,
                default_up='PEVER',
                ma_lookup=ma_lookup,
            )
"""
