# -*- coding: utf-8 -*-
"""
i90_qh_explorer.py — Análisis operativo cuartohorario I90DIA  (v1)
====================================================================

Réplica interactiva del análisis de i90_analisis_flexible.py / HTML estático,
como módulo del dashboard (patrón unit_explorer / representantes_explorer).

Vistas:
  1. PROGRAMAS   — cascada PDBF→PHF1/2/3→PHFC→P48 + activaciones (RT1/F2/mFRR)
  2. RRTT PDBF   — oferta por bloque (MW y €/MWh, DIA17/22 y DIA41/23) vs
                   casado (DIA03) + precio casación por UP (DIA09) + spot
  3. RRTT TR     — oferta TR por bloque (DIA32/31, DIA42/24) vs casado (DIA08)
                   + precio casación TR (DIA10) + spot
  4. mFRR        — oferta por bloque (DIA15, MW+precio interleaved) vs energía
                   activada (DIA07)
  5. RESUMEN     — totales diarios MWh por mercado (tabla + evolución)

Datos: parquets GCS  gs://{BUCKET}/{PREFIX}/dia{NN}/{YYYYMMDD}.parquet
generados por i90_etl.py. Esquema wide: columnas de metadatos
(entity / sentido / redespacho / bloque según hoja) + q001..q096
(+ p001..p096 en hojas interleaved). Convención: oferta en MW por QH,
casado en MWh por QH → oferta MWh = MW × 0.25.

Degradación elegante: si falta el parquet de una hoja/día, la serie
correspondiente simplemente no se pinta y se anota en el expander de
cobertura. Nunca rompe la página.

Integración en app.py:
    from i90_qh_explorer import render_i90_qh, set_gcs_qh, set_helpers_qh
    set_gcs_qh(project="miguel-energia", bucket="dashboard-energia-data",
               prefix="i90rrtt")
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
_CFG = {
    "project": "miguel-energia",
    "bucket":  "dashboard-energia-data",
    "prefix":  "i90rrtt",
    # Maestro mensual de UPs (para Tech/SM en el selector; opcional)
    "ups_parquet_prefix": "ups_dashboard",
    # BQ para precio spot (opcional; si falla, se omite el overlay)
    "bq_dataset": "red_electrica_data",
    "spot_table": "precios_esios",
    "spot_indicator": 600,
}
_HELPERS = {}


def set_gcs_qh(project=None, bucket=None, prefix=None):
    if project: _CFG["project"] = project
    if bucket:  _CFG["bucket"]  = bucket
    if prefix:  _CFG["prefix"]  = prefix


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
# ACCESO A DATOS (GCS parquets i90rrtt + BQ spot)
# ==============================================================================
QCOLS = [f"q{i:03d}" for i in range(1, 97)]
PCOLS = [f"p{i:03d}" for i in range(1, 97)]

# Paleta coherente con el HTML (tema claro del dashboard)
C_BLOCKS = ["#2563EB", "#7C3AED", "#0891B2", "#D97706", "#DB2777",
            "#059669", "#4F46E5", "#B45309", "#0D9488", "#9333EA"]
C_CAS   = "#DC2626"   # casado / activado
C_CASPR = "#F59E0B"   # precio casación
C_SPOT  = "#94A3B8"   # spot
C_PROG  = {"pdbf": "#64748B", "phf1": "#93C5FD", "phf2": "#60A5FA",
           "phf3": "#3B82F6", "phfc": "#1D4ED8", "p48": "#0F172A",
           "rt1": "#DC2626", "f2": "#F59E0B", "mfrr": "#059669"}


@st.cache_resource(show_spinner=False)
def _fs():
    import gcsfs
    try:
        from google.oauth2 import service_account
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return gcsfs.GCSFileSystem(project=_CFG["project"], token=creds)
    except Exception:
        return gcsfs.GCSFileSystem(project=_CFG["project"])  # ADC / anónimo


@st.cache_data(ttl=3600, show_spinner=False)
def _read_sheet(nn: str, ds: str):
    """Parquet de una hoja I90DIA para un día ('YYYYMMDD'). None si no existe."""
    path = f"{_CFG['bucket']}/{_CFG['prefix']}/dia{nn}/{ds}.parquet"
    fs = _fs()
    try:
        if not fs.exists(path):
            return None
        with fs.open(path, "rb") as f:
            return pd.read_parquet(f)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _load_up_meta(year: int, month: int):
    """Tech / SM / Power_MW desde ups_dashboard_{YYYY-MM}.parquet (opcional)."""
    path = (f"{_CFG['bucket']}/{_CFG['ups_parquet_prefix']}_"
            f"{year}-{month:02d}.parquet")
    fs = _fs()
    try:
        if not fs.exists(path):
            path = f"{_CFG['bucket']}/{_CFG['ups_parquet_prefix']}.parquet"
            if not fs.exists(path):
                return pd.DataFrame()
        with fs.open(path, "rb") as f:
            u = pd.read_parquet(f)
        keep = [c for c in ["UP", "Tech", "SM", "Sujeto_del_Mercado",
                            "Power_MW", "RZ"] if c in u.columns]
        return u[keep].drop_duplicates("UP")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _load_spot(d_ini: dt.date, d_fin: dt.date):
    """Precio spot QH desde BQ (indicador 600). None si no disponible.
    Devuelve DataFrame [datetime, price] o None. Nunca lanza."""
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(info)
        client = bigquery.Client(project=_CFG["project"], credentials=creds)
        tbl = f"`{_CFG['project']}.{_CFG['bq_dataset']}.{_CFG['spot_table']}`"
        for dtcol, vcol, dcol in (("datetime", "value", "Dia"),
                                  ("Datetime", "Value", "Dia"),
                                  ("datetime_utc", "value", "Dia")):
            try:
                sql = (f"SELECT {dtcol} AS ts, {vcol} AS price FROM {tbl} "
                       f"WHERE indicator_id = {_CFG['spot_indicator']} "
                       f"AND {dcol} BETWEEN '{d_ini}' AND '{d_fin}' "
                       f"ORDER BY ts")
                df = client.query(sql).to_dataframe()
                if not df.empty:
                    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None)
                    return df
            except Exception:
                continue
    except Exception:
        pass
    return None


# ==============================================================================
# TRANSFORMACIONES WIDE → SERIES QH
# ==============================================================================
def _qh_index(day: dt.date):
    return pd.date_range(pd.Timestamp(day), periods=96, freq="15min")


def _vals(df_rows) -> np.ndarray:
    """Suma las filas de un sub-DataFrame sobre q001..q096 → array(96)."""
    cols = [c for c in QCOLS if c in df_rows.columns]
    if not cols or df_rows.empty:
        return np.full(96, np.nan)
    a = df_rows[cols].apply(pd.to_numeric, errors="coerce").sum(
        axis=0, min_count=1).to_numpy()
    out = np.full(96, np.nan)
    out[:len(a)] = a
    return out


def _pvals(df_rows) -> np.ndarray:
    """Como _vals pero sobre p001..p096 (precio). Media si hay varias filas."""
    cols = [c for c in PCOLS if c in df_rows.columns]
    if not cols or df_rows.empty:
        return np.full(96, np.nan)
    a = df_rows[cols].apply(pd.to_numeric, errors="coerce").mean(
        axis=0).to_numpy()
    out = np.full(96, np.nan)
    out[:len(a)] = a
    return out


def _filter_ups(df, ups):
    if df is None or df.empty or "entity" not in df.columns:
        return None
    sub = df[df["entity"].isin(ups)]
    return sub if not sub.empty else None


def _programa(nn, ds, ups):
    """DIA01/02/19/20/21/36/26 → array(96) MWh (suma de las UPs)."""
    sub = _filter_ups(_read_sheet(nn, ds), ups)
    return _vals(sub) if sub is not None else None


def _rrtt_activ(nn, ds, ups):
    """DIA03/08 → {'RT1': arr, 'F2': arr} según Redespacho (UP* / ECO)."""
    sub = _filter_ups(_read_sheet(nn, ds), ups)
    if sub is None or "redespacho" not in sub.columns:
        return {"RT1": None, "F2": None}
    rd = sub["redespacho"].astype(str).str.strip().str.upper()
    rt1 = sub[rd.str.startswith("UP")]
    f2  = sub[rd == "ECO"]
    return {"RT1": _vals(rt1) if not rt1.empty else None,
            "F2":  _vals(f2)  if not f2.empty  else None}


def _offer_blocks(nn, ds, ups, interleaved):
    """DIA17/41/32/42 (MW) o DIA22/23/31/24 (interleaved MW+precio).
    → {blk: {'mw': arr|None, 'pr': arr|None}} sumando/mediando entre UPs."""
    sub = _filter_ups(_read_sheet(nn, ds), ups)
    if sub is None:
        return {}
    if "bloque" not in sub.columns:
        sub = sub.assign(bloque="B1")
    out = {}
    for blk, g in sub.groupby(sub["bloque"].astype(str).str.extract(
            r"(\d+)", expand=False).fillna("1").radd("B")):
        out[blk] = {"mw": _vals(g),
                    "pr": _pvals(g) if interleaved else None}
    return out


def _clearing_by_up(nn, ds, ups):
    """DIA09/10 → {'rt1_sub': arr, 'f2_baj': arr} (primer valor no nulo)."""
    sub = _filter_ups(_read_sheet(nn, ds), ups)
    if sub is None or "redespacho" not in sub.columns:
        return {}
    rd = sub["redespacho"].astype(str).str.strip().str.upper()
    sd = sub["sentido"].astype(str).str.strip().str.capitalize() \
        if "sentido" in sub.columns else pd.Series("", index=sub.index)
    out = {}
    for key, mask in (("rt1_sub", rd.str.startswith("UP") & (sd == "Subir")),
                      ("f2_baj",  (rd == "ECO") & (sd == "Bajar"))):
        g = sub[mask]
        if not g.empty:
            arr = g[[c for c in QCOLS if c in g.columns]] \
                .apply(pd.to_numeric, errors="coerce") \
                .apply(lambda col: col.dropna().iloc[0]
                       if col.notna().any() else np.nan, axis=0).to_numpy()
            v = np.full(96, np.nan); v[:len(arr)] = arr
            out[key] = v
    return out


def _mfrr_blocks(ds, ups):
    """DIA15 (interleaved) → {blk: {'mw': arr, 'pr': arr}}."""
    return _offer_blocks("15", ds, ups, interleaved=True)


# ── Serie multi-día: concatena arrays por fecha ──────────────────────────────
def _concat_days(day_arrays):
    """[(date, arr(96)|None)] → (DatetimeIndex, np.array) omitiendo días None."""
    idx, vals = [], []
    for d, a in day_arrays:
        if a is None:
            continue
        idx.append(_qh_index(d)); vals.append(a)
    if not idx:
        return None, None
    return idx[0].append(idx[1:]) if len(idx) > 1 else idx[0], \
        np.concatenate(vals)


# ==============================================================================
# CONSTRUCCIÓN DEL DATASET DEL PERIODO
# ==============================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def _build_period(_key, d_ini: dt.date, d_fin: dt.date, ups: tuple):
    """Carga todas las hojas para el rango. Devuelve dict de series y
    la lista de (hoja, día) ausentes para el informe de cobertura."""
    ups = list(ups)
    days = pd.date_range(d_ini, d_fin, freq="D").date
    missing = []

    def track(nn, ds, res):
        if res is None or (isinstance(res, dict) and not any(
                v is not None and (not isinstance(v, dict) or v)
                for v in res.values())):
            missing.append((nn, ds))
        return res

    prog_keys = {"pdbf": "26", "phf1": "19", "phf2": "20",
                 "phf3": "21", "phfc": "36", "p48": "02"}
    data = {"days": [], "prog": {k: [] for k in prog_keys},
            "rt1": [], "f2": [], "tr_rt1": [], "tr_f2": [], "mfrr_e": [],
            "of_pdbf": {"sub_mw": [], "sub_pr": [], "baj_mw": [], "baj_pr": []},
            "of_tr":   {"sub_mw": [], "sub_pr": [], "baj_mw": [], "baj_pr": []},
            "cas_pdbf": [], "cas_tr": [], "mfrr_blk": []}

    for day in days:
        ds = day.strftime("%Y%m%d")
        if _read_sheet("26", ds) is None:     # ancla: sin PDBF no hay día
            missing.append(("26", ds))
            continue
        data["days"].append(day)

        for k, nn in prog_keys.items():
            data["prog"][k].append((day, track(nn, ds, _programa(nn, ds, ups))))

        act = _rrtt_activ("03", ds, ups)
        data["rt1"].append((day, act["RT1"])); data["f2"].append((day, act["F2"]))
        act_tr = _rrtt_activ("08", ds, ups)
        data["tr_rt1"].append((day, act_tr["RT1"]))
        data["tr_f2"].append((day, act_tr["F2"]))
        data["mfrr_e"].append((day, track("07", ds, _programa("07", ds, ups))))

        data["of_pdbf"]["sub_mw"].append((day, _offer_blocks("17", ds, ups, False)))
        data["of_pdbf"]["sub_pr"].append((day, _offer_blocks("22", ds, ups, True)))
        data["of_pdbf"]["baj_mw"].append((day, _offer_blocks("41", ds, ups, False)))
        data["of_pdbf"]["baj_pr"].append((day, _offer_blocks("23", ds, ups, True)))
        data["of_tr"]["sub_mw"].append((day, _offer_blocks("32", ds, ups, False)))
        data["of_tr"]["sub_pr"].append((day, _offer_blocks("31", ds, ups, True)))
        data["of_tr"]["baj_mw"].append((day, _offer_blocks("42", ds, ups, False)))
        data["of_tr"]["baj_pr"].append((day, _offer_blocks("24", ds, ups, True)))
        data["cas_pdbf"].append((day, _clearing_by_up("09", ds, ups)))
        data["cas_tr"].append((day, _clearing_by_up("10", ds, ups)))
        data["mfrr_blk"].append((day, _mfrr_blocks(ds, ups)))

    return data, missing


def _blk_series(day_blocks, field, to_mwh=False):
    """[(day, {blk:{'mw','pr'}})] → {blk: (idx, vals)} por bloque."""
    blks = sorted({b for _, d in day_blocks for b in (d or {})},
                  key=lambda b: int(b[1:]) if b[1:].isdigit() else 99)
    out = {}
    for b in blks:
        pairs = []
        for day, d in day_blocks:
            arr = (d or {}).get(b, {}).get(field)
            if arr is not None and to_mwh:
                arr = arr * 0.25
            pairs.append((day, arr))
        idx, v = _concat_days(pairs)
        if idx is not None:
            out[b] = (idx, v)
    return out


def _cas_series(day_cas, key):
    idx, v = _concat_days([(d, c.get(key)) for d, c in day_cas])
    return (idx, v) if idx is not None else None


# ==============================================================================
# GRÁFICOS
# ==============================================================================
def _base_layout(ytitle, ytitle2=None, height=380):
    lay = dict(paper_bgcolor="#ffffff", plot_bgcolor="#FBFCFE",
               font=dict(family="Inter", color="#46556B", size=11),
               margin=dict(l=10, r=10, t=30, b=10), height=height,
               legend=dict(orientation="h", y=1.12, x=0),
               hovermode="x unified",
               yaxis=dict(title=ytitle, gridcolor="#E3E8F0"),
               xaxis=dict(gridcolor="#E3E8F0"))
    if ytitle2:
        lay["yaxis2"] = dict(title=ytitle2, overlaying="y", side="right",
                             showgrid=False)
    return lay


def _fig_blocks_vs_cas(blk_mwh, cas_pairs, title, spot=None,
                       cas_pr=None, y1="MWh/QH", y2="€/MWh"):
    """Bloques ofertados (área de líneas) + casado + precios en eje derecho."""
    fig = go.Figure()
    for i, (b, (idx, v)) in enumerate(blk_mwh.items()):
        fig.add_trace(go.Scatter(x=idx, y=v, name=f"Oferta {b}",
                                 line=dict(width=1.4,
                                           color=C_BLOCKS[i % len(C_BLOCKS)]),
                                 connectgaps=False))
    if cas_pairs is not None:
        idx, v = cas_pairs
        fig.add_trace(go.Scatter(x=idx, y=v, name=_t("Matched", "Casado"),
                                 line=dict(width=2.2, color=C_CAS),
                                 connectgaps=False))
    if cas_pr is not None:
        idx, v = cas_pr
        fig.add_trace(go.Scatter(x=idx, y=v, yaxis="y2",
                                 name=_t("Clearing €", "Precio casación"),
                                 line=dict(width=1.6, color=C_CASPR,
                                           dash="dot"), connectgaps=False))
    if spot is not None and not spot.empty:
        fig.add_trace(go.Scatter(x=spot["ts"], y=spot["price"], yaxis="y2",
                                 name="Spot", line=dict(width=1.2,
                                                        color=C_SPOT,
                                                        dash="dash")))
    fig.update_layout(title=dict(text=title, font=dict(size=12,
                                                       color="#13233B")),
                      **_base_layout(y1, y2 if (cas_pr is not None or
                                                spot is not None) else None))
    return fig


def _fig_price_blocks(blk_pr, cas_pr, title, spot=None):
    fig = go.Figure()
    for i, (b, (idx, v)) in enumerate(blk_pr.items()):
        fig.add_trace(go.Scatter(x=idx, y=v, name=f"{b}",
                                 line=dict(width=1.4,
                                           color=C_BLOCKS[i % len(C_BLOCKS)]),
                                 connectgaps=False))
    if cas_pr is not None:
        idx, v = cas_pr
        fig.add_trace(go.Scatter(x=idx, y=v,
                                 name=_t("Clearing", "Casación"),
                                 line=dict(width=2.2, color=C_CAS),
                                 connectgaps=False))
    if spot is not None and not spot.empty:
        fig.add_trace(go.Scatter(x=spot["ts"], y=spot["price"], name="Spot",
                                 line=dict(width=1.2, color=C_SPOT,
                                           dash="dash")))
    fig.update_layout(title=dict(text=title, font=dict(size=12,
                                                       color="#13233B")),
                      **_base_layout("€/MWh"))
    return fig


# ==============================================================================
# RENDER PRINCIPAL
# ==============================================================================
def render_i90_qh(start_date=None, end_date=None, default_ups=None):
    _section("🧭", _t("I90 QH Explorer — offers vs matched",
                     "Explorador QH I90 — ofertas vs casado"))

    today = dt.date.today()
    d_ini = start_date or (today - dt.timedelta(days=95))
    d_fin = end_date or (today - dt.timedelta(days=91))
    if isinstance(d_ini, dt.datetime): d_ini = d_ini.date()
    if isinstance(d_fin, dt.datetime): d_fin = d_fin.date()

    c1, c2 = st.columns([1.2, 3])
    with c1:
        rng = st.date_input(_t("Period", "Periodo"), value=(d_ini, d_fin),
                            key="qh_rng")
        if isinstance(rng, tuple) and len(rng) == 2:
            d_ini, d_fin = rng
        n_days = (d_fin - d_ini).days + 1
        if n_days > 14:
            st.warning(_t("Max 14 days at QH detail.",
                          "Máximo 14 días a detalle QH."))
            d_fin = d_ini + dt.timedelta(days=13)

    # UPs disponibles: entidades presentes en el PDBF del primer día con datos
    ups_avail, probe = [], d_ini
    while probe <= d_fin and not ups_avail:
        df26 = _read_sheet("26", probe.strftime("%Y%m%d"))
        if df26 is not None and "entity" in df26.columns:
            ups_avail = sorted(df26["entity"].dropna().unique().tolist())
        probe += dt.timedelta(days=1)

    meta = _load_up_meta(d_ini.year, d_ini.month)
    with c2:
        if not ups_avail:
            st.error(_t(
                "No DIA26 parquet found in the period. Check that "
                "i90_etl.py has processed these dates into "
                f"gs://{_CFG['bucket']}/{_CFG['prefix']}/.",
                "No hay parquet DIA26 en el periodo. Comprueba que "
                "i90_etl.py ha procesado estas fechas en "
                f"gs://{_CFG['bucket']}/{_CFG['prefix']}/."))
            return
        dflt = [u for u in (default_ups or []) if u in ups_avail] \
            or ups_avail[:1]
        ups_sel = st.multiselect(
            _t("Production Units (aggregated if several)",
               "Unidades (se agregan si eliges varias)"),
            options=ups_avail, default=dflt, key="qh_ups")
        if not meta.empty:
            info = meta[meta["UP"].isin(ups_sel)]
            if not info.empty:
                st.caption(" · ".join(
                    f"{r.UP} ({getattr(r, 'Tech', '?')}, "
                    f"{getattr(r, 'Power_MW', float('nan')):.0f} MW)"
                    for r in info.itertuples()))

    if not ups_sel:
        st.info(_t("Select at least one UP.", "Selecciona al menos una UP."))
        return

    with st.spinner(_t("Reading I90 parquets…", "Leyendo parquets I90…")):
        data, missing = _build_period(
            f"{d_ini}{d_fin}{','.join(sorted(ups_sel))}",
            d_ini, d_fin, tuple(sorted(ups_sel)))
        spot = _load_spot(d_ini, d_fin)

    if not data["days"]:
        st.error(_t("No data for the period.", "Sin datos en el periodo."))
        return

    if missing:
        with st.expander(_t("⚠️ Coverage: missing sheets/days",
                            "⚠️ Cobertura: hojas/días ausentes")):
            mdf = pd.DataFrame(missing, columns=["DIA", _t("Day", "Día")])
            st.dataframe(mdf.groupby("DIA").agg(
                dias=("Día" if "Día" in mdf.columns else "Day", "count")),
                use_container_width=True)
    if spot is None:
        st.caption(_t("Spot overlay unavailable (BQ precios).",
                      "Overlay spot no disponible (BQ precios)."))

    tab_prog, tab_pdbf, tab_tr, tab_mfrr, tab_res = st.tabs([
        _t("Programs", "Programas"), "RRTT PDBF",
        _t("RRTT Real Time", "RRTT Tiempo Real"), "mFRR",
        _t("Period summary", "Resumen periodo")])

    # ── 1 · PROGRAMAS ─────────────────────────────────────────────────────────
    with tab_prog:
        prog_lbl = {"pdbf": "PDBF", "phf1": "PHF1", "phf2": "PHF2",
                    "phf3": "PHF3", "phfc": "PHFC", "p48": "P48"}
        sel_prog = st.multiselect(
            _t("Programs to plot", "Programas a representar"),
            options=list(prog_lbl.values()),
            default=["PDBF", "PHFC", "P48"], key="qh_progsel")
        show_act = st.checkbox(
            _t("Overlay activations (RT1 / F2 / mFRR)",
               "Superponer activaciones (RT1 / F2 / mFRR)"),
            value=True, key="qh_act")
        fig = go.Figure()
        inv = {v: k for k, v in prog_lbl.items()}
        for lbl in sel_prog:
            idx, v = _concat_days(data["prog"][inv[lbl]])
            if idx is not None:
                fig.add_trace(go.Scatter(
                    x=idx, y=v, name=lbl, connectgaps=False,
                    line=dict(width=2 if lbl == "P48" else 1.4,
                              color=C_PROG[inv[lbl]])))
        if show_act:
            for key, lbl, col in (("rt1", "RT1", C_PROG["rt1"]),
                                  ("f2", "RRTT F2", C_PROG["f2"]),
                                  ("mfrr_e", "mFRR", C_PROG["mfrr"])):
                idx, v = _concat_days(data[key])
                if idx is not None:
                    fig.add_trace(go.Scatter(x=idx, y=v, name=lbl,
                                             connectgaps=False,
                                             line=dict(width=1.3, color=col,
                                                       dash="dot")))
        fig.update_layout(**_base_layout("MWh/QH", height=430))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(_t(
            "Program cascade at QH level. Activations shown dotted.",
            "Cascada de programas a nivel QH. Activaciones en punteado."))

    # ── 2 · RRTT PDBF ─────────────────────────────────────────────────────────
    with tab_pdbf:
        cas_sub_pr = _cas_series(data["cas_pdbf"], "rt1_sub")
        cas_baj_pr = _cas_series(data["cas_pdbf"], "f2_baj")
        ca, cb = st.columns(2)
        with ca:
            st.plotly_chart(_fig_blocks_vs_cas(
                _blk_series(data["of_pdbf"]["sub_mw"], "mw", to_mwh=True),
                _concat_days(data["rt1"]) if any(
                    a is not None for _, a in data["rt1"]) else None,
                _t("UP · Offer vs matched (DIA17 vs DIA03·RT1)",
                   "SUBIR · Oferta vs casado (DIA17 vs DIA03·RT1)"),
                spot=spot, cas_pr=cas_sub_pr),
                use_container_width=True)
            st.plotly_chart(_fig_price_blocks(
                _blk_series(data["of_pdbf"]["sub_pr"], "pr"),
                cas_sub_pr,
                _t("UP · Offer price by block (DIA22) vs clearing (DIA09)",
                   "SUBIR · Precio oferta por bloque (DIA22) vs casación (DIA09)"),
                spot=spot), use_container_width=True)
        with cb:
            st.plotly_chart(_fig_blocks_vs_cas(
                _blk_series(data["of_pdbf"]["baj_mw"], "mw", to_mwh=True),
                _concat_days(data["f2"]) if any(
                    a is not None for _, a in data["f2"]) else None,
                _t("DOWN · Offer vs matched (DIA41 vs DIA03·F2)",
                   "BAJAR · Oferta vs casado (DIA41 vs DIA03·F2)"),
                spot=spot, cas_pr=cas_baj_pr),
                use_container_width=True)
            st.plotly_chart(_fig_price_blocks(
                _blk_series(data["of_pdbf"]["baj_pr"], "pr"),
                cas_baj_pr,
                _t("DOWN · Offer price by block (DIA23) vs clearing (DIA09)",
                   "BAJAR · Precio oferta por bloque (DIA23) vs casación (DIA09)"),
                spot=spot), use_container_width=True)

    # ── 3 · RRTT TIEMPO REAL ─────────────────────────────────────────────────
    with tab_tr:
        cas_sub_tr = _cas_series(data["cas_tr"], "rt1_sub")
        cas_baj_tr = _cas_series(data["cas_tr"], "f2_baj")
        ca, cb = st.columns(2)
        with ca:
            st.plotly_chart(_fig_blocks_vs_cas(
                _blk_series(data["of_tr"]["sub_mw"], "mw", to_mwh=True),
                _concat_days(data["tr_rt1"]) if any(
                    a is not None for _, a in data["tr_rt1"]) else None,
                _t("UP · TR offer vs activated (DIA32 vs DIA08)",
                   "SUBIR · Oferta TR vs activado (DIA32 vs DIA08)"),
                spot=spot, cas_pr=cas_sub_tr), use_container_width=True)
            st.plotly_chart(_fig_price_blocks(
                _blk_series(data["of_tr"]["sub_pr"], "pr"), cas_sub_tr,
                _t("UP · TR offer price (DIA31) vs clearing (DIA10)",
                   "SUBIR · Precio oferta TR (DIA31) vs casación (DIA10)"),
                spot=spot), use_container_width=True)
        with cb:
            st.plotly_chart(_fig_blocks_vs_cas(
                _blk_series(data["of_tr"]["baj_mw"], "mw", to_mwh=True),
                _concat_days(data["tr_f2"]) if any(
                    a is not None for _, a in data["tr_f2"]) else None,
                _t("DOWN · TR offer vs activated (DIA42 vs DIA08)",
                   "BAJAR · Oferta TR vs activado (DIA42 vs DIA08)"),
                spot=spot, cas_pr=cas_baj_tr), use_container_width=True)
            st.plotly_chart(_fig_price_blocks(
                _blk_series(data["of_tr"]["baj_pr"], "pr"), cas_baj_tr,
                _t("DOWN · TR offer price (DIA24) vs clearing (DIA10)",
                   "BAJAR · Precio oferta TR (DIA24) vs casación (DIA10)"),
                spot=spot), use_container_width=True)

    # ── 4 · mFRR ─────────────────────────────────────────────────────────────
    with tab_mfrr:
        ca, cb = st.columns(2)
        with ca:
            st.plotly_chart(_fig_blocks_vs_cas(
                _blk_series(data["mfrr_blk"], "mw", to_mwh=True),
                _concat_days(data["mfrr_e"]) if any(
                    a is not None for _, a in data["mfrr_e"]) else None,
                _t("mFRR · Offer by block (DIA15) vs activated (DIA07)",
                   "mFRR · Oferta por bloque (DIA15) vs activado (DIA07)"),
                spot=spot), use_container_width=True)
        with cb:
            st.plotly_chart(_fig_price_blocks(
                _blk_series(data["mfrr_blk"], "pr"), None,
                _t("mFRR · Offer price by block (DIA15)",
                   "mFRR · Precio oferta por bloque (DIA15)"),
                spot=spot), use_container_width=True)

    # ── 5 · RESUMEN PERIODO ──────────────────────────────────────────────────
    with tab_res:
        rows = []
        for i, day in enumerate(data["days"]):
            def _tot(pairs):
                a = dict(pairs).get(day)
                return float(np.nansum(a)) if a is not None else 0.0
            rows.append({
                _t("Day", "Día"): day,
                "P48 (MWh)":   _tot(data["prog"]["p48"]),
                "RT1 (MWh)":   _tot(data["rt1"]),
                "F2 (MWh)":    _tot(data["f2"]),
                "TR RT1 (MWh)": _tot(data["tr_rt1"]),
                "TR F2 (MWh)": _tot(data["tr_f2"]),
                "mFRR (MWh)":  _tot(data["mfrr_e"]),
            })
        res = pd.DataFrame(rows).set_index(_t("Day", "Día"))
        st.dataframe(res.style.format("{:,.1f}"), use_container_width=True)
        fig = go.Figure()
        for col, color in (("RT1 (MWh)", C_PROG["rt1"]),
                           ("F2 (MWh)", C_PROG["f2"]),
                           ("TR RT1 (MWh)", "#7C3AED"),
                           ("TR F2 (MWh)", "#0891B2"),
                           ("mFRR (MWh)", C_PROG["mfrr"])):
            fig.add_trace(go.Bar(x=res.index, y=res[col], name=col,
                                 marker_color=color))
        fig.update_layout(barmode="group",
                          **_base_layout("MWh/" + _t("day", "día"),
                                         height=360))
        st.plotly_chart(fig, use_container_width=True)
