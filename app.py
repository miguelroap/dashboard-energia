# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import glob
import gc
import os
from gcs_loader import (
    gcs_available, load_parquet, load_excel,
    list_files, find_latest_excel, list_parquet_years
)

st.set_page_config(page_title="Dashboard Ancillary Services", layout="wide", page_icon="⚡")

# ==============================================================================
# ESTILOS CSS PROFESIONALES
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Fondo general — blanco roto muy suave */
    .stApp { background: #f5f7fa; }
    [data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid #e2e8f0;
        box-shadow: 2px 0 8px rgba(0,0,0,0.04);
    }

    /* Título principal */
    h1 {
        color: #1e293b !important;
        font-weight: 700; font-size: 1.7rem !important;
        letter-spacing: -0.5px; padding-bottom: 0.3rem;
    }
    h1 span.accent { color: #2563eb; }

    /* Headers de sección */
    .section-header {
        display: flex; align-items: center; gap: 10px;
        background: #ffffff;
        border-left: 4px solid #2563eb;
        border-radius: 0 8px 8px 0;
        padding: 10px 16px;
        margin: 1.2rem 0 1rem 0;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .section-header h3 {
        color: #1e293b !important; font-size: 0.95rem;
        font-weight: 600; margin: 0; letter-spacing: 0.1px;
    }

    /* Metric cards */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px 20px; text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        transition: transform 0.15s, box-shadow 0.15s;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(37,99,235,0.1); }
    .metric-label { color: #64748b; font-size: 0.70rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
    .metric-value { color: #1e293b; font-size: 1.45rem; font-weight: 700;
        font-family: 'JetBrains Mono', monospace; }
    .metric-value.positive { color: #059669; }
    .metric-value.negative { color: #dc2626; }
    .metric-delta { font-size: 0.72rem; margin-top: 4px; color: #94a3b8; }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: #f1f5f9; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }

    div.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# CONFIGURACIÓN DEL TEMA PLOTLY
# ==============================================================================
PLOTLY_THEME = dict(
    template="plotly_white",
    paper_bgcolor="#ffffff",
    plot_bgcolor="#f8fafc",
    font=dict(family="Inter, sans-serif", color="#475569", size=12),
    legend=dict(bgcolor="rgba(255,255,255,0.9)", bordercolor="#e2e8f0", borderwidth=1, font=dict(size=11)),
    margin=dict(l=10, r=10, t=45, b=10),
    colorway=["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#ea580c", "#65a30d"],
)

def base_layout(**extra):
    """Devuelve un dict de layout limpio para update_layout."""
    layout = dict(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8fafc",
        font=dict(family="Inter, sans-serif", color="#475569", size=12),
        title_font=dict(family="Inter, sans-serif", color="#1e293b", size=13),
        legend=dict(bgcolor="rgba(255,255,255,0.9)", bordercolor="#e2e8f0", borderwidth=1, font=dict(size=11)),
        margin=dict(l=10, r=10, t=45, b=10),
    )
    layout.update(extra)
    return layout

C_POS    = "#059669"
C_NEG    = "#dc2626"
C_BASE   = "#2563eb"
C_ACCENT = "#7c3aed"
C_WARN   = "#d97706"

def section_header(icon, title):
    st.markdown(f'<div class="section-header"><h3>{icon} {title}</h3></div>', unsafe_allow_html=True)

def metric_card(label, value, delta=None, positive=None, unit=""):
    cls = "positive" if positive is True else ("negative" if positive is False else "")
    delta_html = f'<div class="metric-delta">{delta}</div>' if delta else ""
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value {cls}">{value}{unit}</div>
        {delta_html}
    </div>"""

# ==============================================================================
# SIDEBAR
# ==============================================================================
cont_date = st.sidebar.container()
st.sidebar.markdown("---")
cont_nav = st.sidebar.container()
st.sidebar.markdown("---")
cont_mode = st.sidebar.container()
st.sidebar.markdown("---")
cont_lang = st.sidebar.container()

lang = cont_lang.radio("🌐 Language / Idioma", ["English", "Español"])

def t(en, es):
    return en if lang == "English" else es

if cont_lang.button(t("🧹 Clear Cache & Reload", "🧹 Borrar Caché y Recargar")):
    st.cache_data.clear()
    st.rerun()

# --- CONTRASEÑA ---
import time as _time
import hashlib as _hashlib

def check_password():
    # Si no hay secret configurado, acceso libre (entorno local)
    try:
        _correct = st.secrets["app_password"]
    except Exception:
        return True

    MAX_INTENTOS  = 5      # intentos antes de bloquear
    BLOQUEO_SEG   = 300    # segundos de bloqueo (5 minutos)

    # Inicializar estado
    if "pw_intentos"  not in st.session_state: st.session_state["pw_intentos"]  = 0
    if "pw_bloqueado" not in st.session_state: st.session_state["pw_bloqueado"] = 0.0
    if "pw_ok"        not in st.session_state: st.session_state["pw_ok"]        = False

    # Ya autenticado
    if st.session_state["pw_ok"]:
        return True

    # Pantalla de login centrada
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown(f"""
        <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;
                    padding:2.5rem 2rem;margin-top:3rem;text-align:center;
                    box-shadow:0 4px 20px rgba(0,0,0,0.07);">
            <div style="font-size:2.8rem;margin-bottom:0.5rem;">🔒</div>
            <h2 style="color:#1e293b;margin:0 0 0.3rem 0;font-size:1.4rem;">
                {t('Restricted Access','Acceso Restringido')}</h2>
            <p style="color:#64748b;font-size:0.85rem;margin:0 0 1.5rem 0;">
                {t('Enter your password to continue.','Introduce tu contraseña para continuar.')}</p>
        </div>""", unsafe_allow_html=True)

        # Comprobar bloqueo
        tiempo_restante = BLOQUEO_SEG - (_time.time() - st.session_state["pw_bloqueado"])
        if st.session_state["pw_intentos"] >= MAX_INTENTOS and tiempo_restante > 0:
            mins = int(tiempo_restante // 60)
            segs = int(tiempo_restante % 60)
            st.error(t(
                f"🚫 Too many failed attempts. Try again in {mins}m {segs}s.",
                f"🚫 Demasiados intentos fallidos. Inténtalo de nuevo en {mins}m {segs}s."
            ))
            st.info(t("Reload the page when the time is up.",
                      "Recarga la página cuando el tiempo haya pasado."))
            return False

        # Si el bloqueo ha expirado, resetear intentos
        if st.session_state["pw_intentos"] >= MAX_INTENTOS and tiempo_restante <= 0:
            st.session_state["pw_intentos"]  = 0
            st.session_state["pw_bloqueado"] = 0.0

        def _on_submit():
            pwd_input = st.session_state.get("pw_input", "")
            # Comparar con hash para evitar timing attacks
            h_input   = _hashlib.sha256(pwd_input.encode()).hexdigest()
            h_correct = _hashlib.sha256(_correct.encode()).hexdigest()
            if h_input == h_correct:
                st.session_state["pw_ok"]       = True
                st.session_state["pw_intentos"] = 0
            else:
                st.session_state["pw_intentos"] += 1
                if st.session_state["pw_intentos"] >= MAX_INTENTOS:
                    st.session_state["pw_bloqueado"] = _time.time()

        st.text_input(
            t("Password","Contraseña"),
            type="password",
            key="pw_input",
            on_change=_on_submit,
            placeholder=t("Enter password…","Introduce la contraseña…"),
            label_visibility="collapsed"
        )

        # Mensajes de error / intentos restantes
        if st.session_state["pw_intentos"] > 0 and not st.session_state["pw_ok"]:
            restantes = MAX_INTENTOS - st.session_state["pw_intentos"]
            if restantes > 0:
                st.warning(t(
                    f"😕 Incorrect password. {restantes} attempt(s) remaining.",
                    f"😕 Contraseña incorrecta. Te quedan {restantes} intento(s)."
                ))
            # Si llega a 0 se mostrará el bloqueo en la siguiente recarga

    return st.session_state["pw_ok"]

if not check_password():
    st.stop()

st.title(t("⚡ Performance Analysis · Ancillary & Intraday Markets", "⚡ Análisis de Desempeño · Mercados de Ajuste e Intradiarios"))

# --- MODO ---
cont_mode.header(t("🔍 Analysis Mode", "🔍 Modo de Análisis"))
modo_opciones = [
    t("📅 Strategic Mode (Daily)", "📅 Modo Estratégico (Diario)"),
    t("⏱️ Operational Mode [DISABLED]", "⏱️ Modo Operativo [DESHABILITADO]")
]
modo_app = cont_mode.radio("Modo", modo_opciones, label_visibility="collapsed")
is_hourly = (modo_app == modo_opciones[1])

if is_hourly:
    st.warning(t("⏳ Operational Mode is temporarily disabled.", "⏳ El Modo Operativo está temporalmente deshabilitado."))
    st.stop()

if 'last_mode' not in st.session_state: st.session_state.last_mode = is_hourly
need_reset = False
if st.session_state.last_mode != is_hourly:
    need_reset = True
    st.session_state.last_mode = is_hourly

# --- CARGA DE DATOS ---
_USE_GCS = gcs_available()

@st.cache_data
def load_daily_data_for_years(years):
    dfs = []
    for y in years:
        filename = f'allh_diario_{y}.parquet'
        if _USE_GCS:
            df_y = load_parquet(filename)
        elif os.path.exists(filename):
            df_y = pd.read_parquet(filename)
        else:
            continue
        if not df_y.empty:
            dfs.append(df_y)
    if not dfs: return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    for col in ['UP', 'MA', 'Tech']:
        if col in df.columns: df[col] = df[col].astype('category')
    return df

@st.cache_data
def get_daily_date_bounds(min_y, max_y):
    try:
        if _USE_GCS:
            df_min = load_parquet(f'allh_diario_{min_y}.parquet')
            df_max = load_parquet(f'allh_diario_{max_y}.parquet')
        else:
            df_min = pd.read_parquet(f'allh_diario_{min_y}.parquet', columns=['Day'])
            df_max = pd.read_parquet(f'allh_diario_{max_y}.parquet', columns=['Day'])
        return df_min['Day'].min().date(), df_max['Day'].max().date()
    except:
        return pd.to_datetime('2023-01-01').date(), pd.to_datetime('today').date()

@st.cache_data
def load_power_data():
    try:
        if _USE_GCS:
            df = load_parquet('ups_dashboard.parquet')
        elif os.path.exists('ups_dashboard.parquet'):
            df = pd.read_parquet('ups_dashboard.parquet')
        else:
            return pd.DataFrame(columns=['UP', 'Power MW'])
        if 'Power MW' not in df.columns:
            return pd.DataFrame(columns=['UP', 'Power MW'])
        df['Power MW'] = pd.to_numeric(df['Power MW'], errors='coerce')
        return df[['UP', 'Power MW']].dropna()
    except:
        return pd.DataFrame(columns=['UP', 'Power MW'])

@st.cache_data
def load_ups_monthly(year_month_str):
    """
    Carga ups_dashboard_YYYY-MM.parquet desde GCS o local.
    Devuelve DataFrame con columnas [UP, RZ, FechaInicio_RZ].
    """
    fname = f'ups_dashboard_{year_month_str}.parquet'
    try:
        if _USE_GCS:
            df = load_parquet(fname)
        elif os.path.exists(fname):
            df = pd.read_parquet(fname)
        else:
            return pd.DataFrame(columns=['UP', 'RZ', 'FechaInicio_RZ'])
        for col in ['UP', 'RZ']:
            if col not in df.columns:
                return pd.DataFrame(columns=['UP', 'RZ', 'FechaInicio_RZ'])
        if 'FechaInicio_RZ' not in df.columns:
            df['FechaInicio_RZ'] = year_month_str
        return df[['UP', 'RZ', 'FechaInicio_RZ']].dropna(subset=['UP', 'RZ'])
    except:
        return pd.DataFrame(columns=['UP', 'RZ', 'FechaInicio_RZ'])

@st.cache_data
def build_rz_map(start_date_str, end_date_str):
    """
    Para el rango de fechas seleccionado construye un mapa UP->RZ mensual.
    Devuelve DataFrame con [UP, Month_str, RZ, FechaInicio_RZ].
    Usa strings de fecha para ser compatible con st.cache_data.
    """
    months = pd.period_range(
        start=pd.to_datetime(start_date_str).to_period('M'),
        end=pd.to_datetime(end_date_str).to_period('M'),
        freq='M'
    )
    frames = []
    for m in months:
        ym = str(m)
        df_m = load_ups_monthly(ym)
        if not df_m.empty:
            df_m = df_m.copy()
            df_m['Month_str'] = ym
            frames.append(df_m)
    if not frames:
        return pd.DataFrame(columns=['UP', 'Month_str', 'RZ', 'FechaInicio_RZ'])
    return pd.concat(frames, ignore_index=True)

# Detectar años disponibles
if _USE_GCS:
    available_years = list_parquet_years('allh_diario_')
else:
    diario_files = glob.glob('allh_diario_*.parquet')
    available_years = sorted([
        int(f.split('_')[-1].split('.')[0])
        for f in diario_files
        if f.split('_')[-1].split('.')[0].isdigit()
    ])

if not available_years:
    if _USE_GCS:
        st.error(t("No allh_diario_*.parquet files found in Google Cloud Storage.",
                   "No se encontraron archivos allh_diario_*.parquet en Google Cloud Storage."))
    else:
        st.error(t("Daily files not found.", "Archivos diarios no encontrados."))
    st.stop()

min_date_val, max_date_val = get_daily_date_bounds(available_years[0], available_years[-1])
default_start = max_date_val - pd.Timedelta(days=30)
if default_start < min_date_val: default_start = min_date_val
default_dates = (default_start, max_date_val)

if need_reset and 'date_picker' in st.session_state:
    del st.session_state['date_picker']

cont_date.header(t("📅 Date Range", "📅 Rango de Fechas"))
selected_dates = cont_date.date_input(
    t("Select period (Max 12 months):", "Selecciona periodo (Máx 12 meses):"),
    value=default_dates, min_value=min_date_val, max_value=max_date_val, key='date_picker'
)

if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
elif isinstance(selected_dates, tuple) and len(selected_dates) == 1:
    start_date = end_date = selected_dates[0]
else:
    start_date = end_date = selected_dates

if (end_date - start_date).days > 366:
    st.sidebar.warning(t("Maximum 12 months. Range truncated.", "⚠️ Máximo 12 meses. Rango acortado a 1 año."))
    start_date = end_date - pd.Timedelta(days=365)

years_to_load = list(range(start_date.year, end_date.year + 1))
allh_full = load_daily_data_for_years(tuple(years_to_load))

if allh_full.empty: st.stop()
allh_full['Day'] = pd.to_datetime(allh_full['Day'])

cols_to_ensure = ['Profit_rt', 'Profit_tr_s', 'Profit_tr', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i',
                  'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se', 'Energy_tr', 'Energy_i', 'Profit_p48', 'Energy_p48', 'PBF', 'Energy_RT1', 'Rev_tr', 'Rev_spot']
for col in cols_to_ensure:
    if col not in allh_full.columns: allh_full[col] = 0.0
    else: allh_full[col] = pd.to_numeric(allh_full[col], errors='coerce').fillna(0)
gc.collect()

allh = allh_full.loc[(allh_full['Day'].dt.date >= start_date) & (allh_full['Day'].dt.date <= end_date)]
df_power = load_power_data()
# Mapa UP->RZ mensual para el periodo seleccionado
df_rz_map = build_rz_map(str(start_date), str(end_date))
gc.collect()

# --- NAVEGACIÓN ---
cont_nav.header(t("🧭 Navigation", "🧭 Menú de Navegación"))
name_main    = t("📈 Main Overview", "📈 Resumen Principal")
name_mra     = t("⚡ MRA Analysis", "⚡ Análisis MRA")
name_rt5     = t("📋 RT5 Detail", "📋 Detalle RT5")
name_gnera   = t("📊 Gnera Analysis", "📊 Análisis Gnera")
name_verbund = t("💶 Verbund Profit", "💶 Beneficio Verbund")
name_evo     = t("📈 Revenue Evolution", "📈 Evolución Ingresos")
name_supply   = t("🏪 Retailers (Supply)", "🏪 Comercializadoras (Supply)")
name_portfolio = t("🗂️ MRA Portfolio", "🗂️ Portfolio MRA")

menu_options = [name_main, name_mra, name_rt5, name_gnera, name_verbund, name_evo, name_supply, name_portfolio]
seleccion_menu = cont_nav.radio("Menu", menu_options, label_visibility="collapsed")

# ==============================================================================
# SECCIÓN 1: RESUMEN PRINCIPAL
# ==============================================================================
if seleccion_menu == name_main:
    section_header("📈", t("Ancillary Services Revenue Dispersion by Technology", "Dispersión de Ingresos en Servicios de Ajuste por Tecnología"))

    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 1, 1])
    with col_f1:
        ups_interes = ['CLIFV30','CLIFV31','CLIFV32','UPBUS','UPLMP','UPSLN','GALPS59','GALPS57','GALPS56','FCTRAV2','EFGNRA','PEVER','PEVER2','EAYAMON','EGST146']
        installation = ['Pinos Puente 1','Pinos Puente 2','Pinos Puente 3','Buseco','Loma','La Solana','Buseco_Galp','Loma_Galp','La Solana_Galp','Calatrava','Bodenaya + Pico + Others','Sorolla 1','Mallen','Ayamonte','Barroso']
        ma_mapping = allh[['UP','MA']].dropna().drop_duplicates(subset=['UP']).set_index('UP')['MA'].to_dict()
        selected_ups = st.multiselect(
            t("🔴 Installations to Highlight:", "🔴 Instalaciones a Resaltar:"),
            options=ups_interes,
            default=[u for u in ['PEVER','EGST146'] if u in ups_interes],
            format_func=lambda x: f"{installation[ups_interes.index(x)]} ({ma_mapping.get(x,'Desc')})"
        )
    with col_f2:
        aass_sel = st.radio(
            t("⚙️ Market Selection:", "⚙️ Selección de Mercados:"),
            options=['no_sec','sec','all'], index=2,
            format_func=lambda x: t("No Secondary","Sin Secundaria") if x=='no_sec' else (t("Only Secondary","Solo Secundaria") if x=='sec' else t("All Markets","Todos los mercados")),
            horizontal=True
        )
    with col_f3:
        include_rt5 = st.checkbox(
            t("Include RT5","Incluir RT5"),
            value=True, key='main_include_rt5'
        )
    with col_f4:
        # Toggle: agrupar por MA o por Zona de Regulación
        group_by_rz = st.checkbox(
            t("Group by RZ","Agrupar por ZR"),
            value=False, key='main_group_by_rz',
            help=t("Aggregate UPs belonging to the same Regulation Zone (RZ) instead of Market Agent (MA)",
                   "Agrega las UPs de la misma Zona de Regulación (ZR) en lugar de por Representante (MA)")
        )

    mask_active = (allh['Profit_rt'] != 0) | (allh['Profit_b'] != 0)
    active_ups = allh[mask_active]['UP'].unique()
    excluded_MAs = ["ENDESA","IBERDROLA","EDP","NATURGY","HOLALUZ","ALDROENERGIA Y SOLUCIONES SL"]
    allh_main = allh.loc[(allh['UP'].isin(active_ups)) & (~allh['MA'].isin(excluded_MAs))].copy()

    if aass_sel == 'no_sec': cols_sel = ['Profit_rt','Profit_tr_s','Profit_t','Profit_rr']
    elif aass_sel == 'sec':  cols_sel = ['Profit_b','Profit_se']
    else:                    cols_sel = ['Profit_rt','Profit_tr_s','Profit_t','Profit_rr','Profit_b','Profit_se']

    if not include_rt5:
        cols_sel = [c for c in cols_sel if c != 'Profit_tr_s']

    allh_main = allh_main.assign(Total_Profit=allh_main[cols_sel].sum(axis=1), Month=allh_main['Day'].dt.to_period('M'))

    # ── Asignar RZ mensual a cada fila de allh_main ───────────────────────────
    # La RZ de cada UP puede cambiar mes a mes, usamos el mapa mensual de GCS
    if group_by_rz and not df_rz_map.empty:
        allh_main['Month_str'] = allh_main['Day'].dt.to_period('M').astype(str)
        allh_main = pd.merge(
            allh_main,
            df_rz_map[['UP','Month_str','RZ']].rename(columns={'RZ':'RZ_monthly'}),
            on=['UP','Month_str'], how='left'
        )
        # Fallback: si el mes no tiene ups_dashboard, usar RZ de allh si existe
        if 'RZ' in allh_main.columns:
            allh_main['RZ_monthly'] = allh_main['RZ_monthly'].fillna(allh_main['RZ'].astype(str))
        allh_main['RZ_monthly'] = allh_main['RZ_monthly'].fillna('Unknown')
        group_col_box = 'RZ_monthly'
        box_title_suffix = t('Profit/MW by Regulation Zone','Profit/MW por Zona de Regulación')
    else:
        group_col_box = 'MA'
        box_title_suffix = t('Profit/MW by Market Agent','Profit/MW por Representante')

    # ── Agrupación mensual ────────────────────────────────────────────────────
    monthly = allh_main.groupby(['UP','Tech','MA','Month'], observed=True).agg(
        Monthly_Profit=('Total_Profit','sum'), Monthly_Energy=('Energy_p48','sum')
    ).reset_index()
    monthly = pd.merge(monthly, df_power, on='UP', how='left')
    monthly['Profit_per_MW'] = (monthly['Monthly_Profit'] / monthly['Power MW']).replace([np.inf,-np.inf], 0).fillna(0)

    if group_by_rz and not df_rz_map.empty:
        # Añadir RZ al monthly (usar el más frecuente del periodo para cada UP)
        rz_dominant = (
            df_rz_map.groupby('UP')['RZ']
            .agg(lambda s: s.mode().iloc[0] if len(s) > 0 else 'Unknown')
            .reset_index()
            .rename(columns={'RZ': 'RZ_monthly'})
        )
        monthly = pd.merge(monthly, rz_dominant, on='UP', how='left')
        monthly['RZ_monthly'] = monthly['RZ_monthly'].fillna('Unknown')
        grouped = monthly.groupby(['UP','Tech','MA','RZ_monthly'], observed=True).agg(
            Profit_per_MW=('Profit_per_MW','mean')
        ).reset_index()
        grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)
        grouped['MA'] = grouped['MA'].astype(str)
    else:
        grouped = monthly.groupby(['UP','Tech','MA'], observed=True).agg(
            Profit_per_MW=('Profit_per_MW','mean')
        ).reset_index()
        grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)
        grouped['MA'] = grouped['MA'].astype(str)
        grouped['RZ_monthly'] = 'N/A'

    def make_boxplot(tech, color_main, color_highlight):
        data = grouped[grouped['Tech'] == tech].copy()
        if data.empty:
            return None

        grp = group_col_box
        order = data.groupby(grp, observed=True)['Profit_per_MW'].mean().sort_values(ascending=False).index.tolist()
        data[grp] = pd.Categorical(data[grp], categories=order, ordered=True)
        data = data.sort_values(grp)

        normal = data[~data['is_Highlighted']]
        highlighted = data[data['is_Highlighted']]

        fig = go.Figure()
        r, g, b = px.colors.hex_to_rgb(color_main)
        fill_rgba = f"rgba({r},{g},{b},0.15)"

        for cat in order:
            cat_data = normal[normal[grp] == cat]['Profit_per_MW']
            if cat_data.empty: continue
            fig.add_trace(go.Box(
                y=cat_data, name=str(cat), boxpoints=False,
                marker_color=color_main,
                line_color=color_main,
                fillcolor=fill_rgba,
                showlegend=False,
                hovertemplate=f"<b>{cat}</b><br>Mediana: %{{median:.1f}} €/MW<br>IQR: %{{q1:.1f}} – %{{q3:.1f}}<extra></extra>"
            ))

        if not highlighted.empty:
            fig.add_trace(go.Scatter(
                x=highlighted[grp].astype(str), y=highlighted['Profit_per_MW'],
                mode='markers',
                marker=dict(color='#f87171', size=10, symbol='diamond', line=dict(color='white', width=1.5)),
                name=t('Highlighted','Resaltadas'),
                hovertemplate="<b>%{x}</b><br>UP: %{customdata}<br>Profit/MW: %{y:.1f} €<extra></extra>",
                customdata=highlighted['UP']
            ))

        fig.add_hline(y=0, line_dash="dot", line_color="#4b5563", line_width=1)
        fig.update_layout(**base_layout(
            title=dict(text=f"<b>{tech}</b> · {box_title_suffix}", font=dict(size=13, color="#1e293b")),
            xaxis_title="",
            yaxis_title=t("Avg Monthly Profit / MW (€)", "Profit Mensual Medio / MW (€)"),
            height=430,
        ))
        fig.update_xaxes(gridcolor="#e2e8f0", tickangle=-35)
        fig.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8")
        return fig

    # Aviso si modo RZ y no hay datos de ups_dashboard mensual
    if group_by_rz and df_rz_map.empty:
        st.warning(t(
            "⚠️ No monthly ups_dashboard files found in GCS (ups_dashboard_YYYY-MM.parquet). Showing by MA instead.",
            "⚠️ No se encontraron archivos ups_dashboard_YYYY-MM.parquet en GCS. Mostrando por representante (MA)."
        ))

    c1, c2 = st.columns(2)
    with c1:
        fig_solar = make_boxplot('Solar PV', '#f59e0b', '#f87171')
        if fig_solar: st.plotly_chart(fig_solar, use_container_width=True)
        else: st.info(t("No Solar PV data.","Sin datos de Solar PV."))
    with c2:
        fig_wind = make_boxplot('Wind', '#34d399', '#f87171')
        if fig_wind: st.plotly_chart(fig_wind, use_container_width=True)

    # ── MATRIZ MA × MERCADO ───────────────────────────────────────────────────
    st.markdown("---")
    section_header("🗺️", t("Market Matrix – Profit by MA and Market",
                             "Matriz de Mercados – Profit por Representante y Mercado"))

    MARKET_COLS = {
        'Profit_rt':   t('RRTT F2','RRTT F2'),
        'Profit_tr_s': t('RT5','RT5'),
        'Profit_t':    t('Tertiary','Terciaria'),
        'Profit_rr':   t('RR','RR'),
        'Profit_b':    t('Sec. Band','Banda Sec.'),
        'Profit_se':   t('Sec. Energy','Energía Sec.'),
    }
    MARKET_AVAIL = {k: v for k, v in MARKET_COLS.items()
                    if k in allh_main.columns and (include_rt5 or k != 'Profit_tr_s')}

    mc1, mc2, mc3, mc4 = st.columns([1.6, 1, 1, 1.5])
    with mc1:
        mat_metric = st.radio(
            t("Metric","Métrica"),
            options=['eur_mw', 'eur_k', 'eur_mwh'],
            format_func=lambda x: {
                'eur_mw':  t("€/MW·month","€/MW·mes"),
                'eur_k':   t("k€ total","k€ total"),
                'eur_mwh': t("€/MWh","€/MWh"),
            }[x],
            horizontal=True, key='mat_metric'
        )
    with mc2:
        mat_qualified = st.checkbox(
            t("Only qualified in SSAA","Solo qualificadas SSAA"),
            value=True, key='mat_qualified'
        )
    with mc3:
        mat_up_filter = st.checkbox(
            t("Filter by UP","Filtrar por UP"),
            value=False, key='mat_up_filter'
        )
    with mc4:
        if mat_up_filter:
            # Selector de MA para cargar sus UPs de una vez
            all_mas_matrix = sorted(allh_main['MA'].astype(str).unique().tolist())
            mat_ma_quick = st.multiselect(
                t("Quick: all UPs of a MA","Rápido: todas las UPs de un MA"),
                options=all_mas_matrix,
                default=[],
                key='mat_ma_quick',
                label_visibility='visible'
            )
        else:
            mat_ma_quick = []

    # Si hay filtro por UP, mostrar selector de UPs debajo (full width), separado por tecnología
    mat_up_sel_solar, mat_up_sel_wind = None, None
    if mat_up_filter:
        st.markdown("")
        # UPs disponibles por tecnología (filtradas por MA seleccionados si los hay)
        def _ups_for_tech(tech):
            df_t = allh_main[allh_main['Tech'] == tech].copy()
            if mat_qualified:
                mask_q = (df_t['Profit_rt'] != 0) | (df_t['Profit_b'] != 0) | (df_t['Profit_t'] != 0)
                df_t = df_t[df_t['UP'].isin(df_t.loc[mask_q, 'UP'].unique())]
            ups_all = sorted(df_t['UP'].astype(str).unique().tolist())
            # UPs de los MA seleccionados en el selector rápido
            ups_from_ma = sorted(
                df_t[df_t['MA'].astype(str).isin(mat_ma_quick)]['UP'].astype(str).unique().tolist()
            ) if mat_ma_quick else []
            return ups_all, ups_from_ma

        fu1, fu2 = st.columns(2)
        with fu1:
            ups_solar_all, ups_solar_ma = _ups_for_tech('Solar PV')
            # Si hay MAs seleccionados, las opciones se limitan a sus UPs
            solar_options = ups_solar_ma if mat_ma_quick else ups_solar_all
            mat_up_sel_solar = st.multiselect(
                t("☀️ Solar PV – UPs to include","☀️ Solar PV – UPs a incluir"),
                options=solar_options,
                default=solar_options,
                key='mat_up_sel_solar'
            )
        with fu2:
            ups_wind_all, ups_wind_ma = _ups_for_tech('Wind')
            wind_options = ups_wind_ma if mat_ma_quick else ups_wind_all
            mat_up_sel_wind = st.multiselect(
                t("🌬️ Wind – UPs to include","🌬️ Wind – UPs a incluir"),
                options=wind_options,
                default=wind_options,
                key='mat_up_sel_wind'
            )

    n_months = max(1, round((end_date - start_date).days / 30.44))

    def build_matrix(tech):
        df_m = allh_main[allh_main['Tech'] == tech].copy()
        if mat_qualified:
            mask_q = (df_m['Profit_rt'] != 0) | (df_m['Profit_b'] != 0) | (df_m['Profit_t'] != 0)
            df_m = df_m[df_m['UP'].isin(df_m.loc[mask_q, 'UP'].unique())]

        # Selección de UPs específica por tecnología
        if mat_up_filter:
            up_sel = mat_up_sel_solar if tech == 'Solar PV' else mat_up_sel_wind
            if up_sel:
                df_m = df_m[df_m['UP'].astype(str).isin(up_sel)]

        if df_m.empty:
            return pd.DataFrame(), ""

        grp_col = 'UP' if mat_up_filter else 'MA'
        agg_cols = list(MARKET_AVAIL.keys())
        extra_cols = ['Energy_p48'] if mat_metric == 'eur_mwh' else []
        agg_src = [c for c in agg_cols + extra_cols if c in df_m.columns]
        df_agg = df_m.groupby([grp_col], observed=True)[agg_src].sum(numeric_only=True).reset_index()
        df_agg[grp_col] = df_agg[grp_col].astype(str)
        market_labels = [MARKET_AVAIL[c] for c in agg_cols if c in df_agg.columns]
        df_agg = df_agg.rename(columns={c: MARKET_AVAIL[c] for c in agg_cols if c in df_agg.columns})
        if mat_metric == 'eur_mw':
            if grp_col == 'UP':
                df_agg = pd.merge(df_agg, df_power, on='UP', how='left')
                denom = (df_agg['Power MW'] * n_months).replace(0, np.nan)
            else:
                power_ma = pd.merge(
                    allh_main[allh_main['Tech'] == tech][['MA','UP']].drop_duplicates(),
                    df_power, on='UP', how='left'
                ).groupby('MA', observed=True)['Power MW'].sum().reset_index()
                df_agg = pd.merge(df_agg, power_ma, left_on='MA', right_on='MA', how='left')
                denom = (df_agg['Power MW'] * n_months).replace(0, np.nan)
            for col in market_labels:
                df_agg[col] = (df_agg[col] / denom).fillna(0)
            df_agg = df_agg.drop(columns=['Power MW'], errors='ignore')
            unit_label = "€/MW·mes"
        elif mat_metric == 'eur_k':
            for col in market_labels:
                df_agg[col] = df_agg[col] / 1000
            unit_label = "k€"
        elif mat_metric == 'eur_mwh':
            energy = df_agg.get('Energy_p48', pd.Series(np.nan, index=df_agg.index)).replace(0, np.nan)
            for col in market_labels:
                df_agg[col] = (df_agg[col] / energy).fillna(0)
            df_agg = df_agg.drop(columns=['Energy_p48'], errors='ignore')
            unit_label = "€/MWh"
        else:
            unit_label = "€"
        df_agg['_total'] = df_agg[market_labels].sum(axis=1)
        df_agg = df_agg.sort_values('_total', ascending=False).drop(columns='_total')
        return df_agg.set_index(grp_col)[market_labels], unit_label

    def render_matrix(tech, title_color):
        df_mat, unit_label = build_matrix(tech)
        if df_mat.empty:
            st.info(t(f"No data for {tech}.", f"Sin datos para {tech}."))
            return
        st.markdown(
            f'<div class="section-header"><h3>📊 '
            f'<span style="color:{title_color};font-weight:700;">{tech}</span>'
            f' — {unit_label}</h3></div>', unsafe_allow_html=True)
        z = df_mat.values
        if unit_label == "k€":
            text_mat = [[f"{v:,.1f}" for v in row] for row in z]; hover_fmt = ":,.1f"
        elif unit_label in ("€/MW·mes","€/MWh"):
            text_mat = [[f"{v:,.1f}" for v in row] for row in z]; hover_fmt = ":,.2f"
        else:
            text_mat = [[f"{v:,.0f}" for v in row] for row in z]; hover_fmt = ":,.0f"
        colorscale = [[0.0,"#b91c1c"],[0.35,"#fca5a5"],[0.5,"#f8fafc"],[0.65,"#86efac"],[1.0,"#15803d"]]
        fig = go.Figure(go.Heatmap(
            z=z, x=df_mat.columns.tolist(), y=df_mat.index.tolist(),
            colorscale=colorscale, zmid=0, text=text_mat,
            texttemplate="<b>%{text}</b>", textfont=dict(size=11),
            hovertemplate=f"<b>%{{y}}</b> · <b>%{{x}}</b><br>%{{z{hover_fmt}}} {unit_label}<extra></extra>",
            colorbar=dict(title=dict(text=unit_label, font=dict(color="#475569",size=11)),
                          tickfont=dict(color="#475569",size=10), thickness=12, outlinewidth=0)
        ))
        sec_cols = [t('Sec. Band','Banda Sec.'), t('Sec. Energy','Energía Sec.')]
        n_before = sum(1 for c in df_mat.columns if c not in sec_cols)
        if any(c in df_mat.columns for c in sec_cols) and 0 < n_before < len(df_mat.columns):
            fig.add_shape(type="line", xref="x", yref="paper",
                          x0=n_before-0.5, x1=n_before-0.5, y0=0, y1=1,
                          line=dict(color="#94a3b8", width=1.5, dash="dot"))
        fig.update_layout(
            paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
            font=dict(family="Inter", color="#475569"),
            title_font=dict(family="Inter", color="#1e293b", size=13),
            margin=dict(l=10,r=70,t=15,b=60),
            height=max(250, len(df_mat)*34+100),
            xaxis=dict(side='bottom', tickangle=-20, tickfont=dict(size=11), gridcolor="rgba(0,0,0,0)"),
            yaxis=dict(tickfont=dict(size=10), gridcolor="rgba(0,0,0,0)", autorange='reversed'),
        )
        st.plotly_chart(fig, use_container_width=True)
        with st.expander(t("📋 Show data table","📋 Ver tabla de datos"), expanded=False):
            fmt_str = {"k€":"{:,.1f} k€","€/MW·mes":"{:,.1f} €/MW·mes",
                       "€/MWh":"{:,.2f} €/MWh"}.get(unit_label,"{:,.0f} €")
            st.dataframe(df_mat.style.format(fmt_str)
                         .background_gradient(cmap='RdYlGn', axis=None),
                         use_container_width=True)

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        render_matrix('Solar PV', '#d97706')
    with col_m2:
        render_matrix('Wind', '#059669')

    # ── RANKING: días como mejor MA por tecnología ────────────────────────────
    st.markdown("---")
    section_header("🏅", t("Days as Best MA by Technology (selected period)",
                            "Días como mejor representante por Tecnología (periodo seleccionado)"))

    profit_cols_main = ['Profit_rt','Profit_tr_s','Profit_t','Profit_rr','Profit_b','Profit_se']
    allh_main2 = allh_main.copy()
    allh_main2['Total_Profit'] = allh_main2[[c for c in profit_cols_main if c in allh_main2.columns]].sum(axis=1)

    # Profit diario por MA y tecnología
    daily_ma = allh_main2.groupby(['Day','Tech','MA'], observed=True)['Total_Profit'].sum().reset_index()

    # Para cada (Day, Tech) → el MA con más profit
    idx_best = daily_ma.groupby(['Day','Tech'], observed=True)['Total_Profit'].idxmax()
    best_daily = daily_ma.loc[idx_best].copy()
    best_daily = best_daily[best_daily['Total_Profit'] > 0]   # solo días con profit positivo

    # Contar días como mejor
    ranking = best_daily.groupby(['Tech','MA'], observed=True).size().reset_index(name='Days_as_Best')
    ranking['MA'] = ranking['MA'].astype(str)

    techs_available = [t for t in ['Solar PV','Wind'] if t in ranking['Tech'].unique()]
    if techs_available:
        rank_cols = st.columns(len(techs_available))
        colors_tech = {'Solar PV':'#f59e0b', 'Wind':'#34d399'}
        for idx_t, tech in enumerate(techs_available):
            rk = ranking[ranking['Tech'] == tech].sort_values('Days_as_Best', ascending=True).tail(15)
            with rank_cols[idx_t]:
                fig_rk = go.Figure(go.Bar(
                    x=rk['Days_as_Best'], y=rk['MA'],
                    orientation='h',
                    marker=dict(
                        color=rk['Days_as_Best'],
                        colorscale=[[0, f"rgba{tuple(list(px.colors.hex_to_rgb(colors_tech[tech]))+[0.3])}"],
                                    [1, colors_tech[tech]]],
                        showscale=False),
                    text=rk['Days_as_Best'].astype(str) + t(' days',' días'),
                    textposition='outside',
                    hovertemplate="<b>%{y}</b><br>" + t('Days as best:','Días como mejor:') + " %{x}<extra></extra>"
                ))
                fig_rk.update_layout(**base_layout(
                    title=dict(text=f"<b>{tech}</b> · " + t('Days as best MA','Días como mejor MA'),
                               font=dict(size=13, color="#1e293b")),
                    xaxis_title=t("Days","Días"), height=max(300, len(rk)*38 + 80),
                    margin=dict(l=10, r=80, t=45, b=10), showlegend=False,
                ))
                fig_rk.update_xaxes(gridcolor="#e2e8f0")
                fig_rk.update_yaxes(gridcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_rk, use_container_width=True)

    # ── ANIMATED BAR CHART RACE: ranking diario de profit/MW por MA ──────────
    st.markdown("---")
    section_header("🎬", t("Animated Daily Ranking – Profit/MW by MA",
                            "Ranking Diario Animado – Profit/MW por Representante"))

    tech_anim = st.radio(
        t("Technology for animation:","Tecnología para la animación:"),
        options=[tc for tc in ['Solar PV','Wind'] if tc in allh_main2['Tech'].unique()],
        horizontal=True, key='anim_tech'
    )

    df_anim = allh_main2[allh_main2['Tech'] == tech_anim].copy()
    df_anim = pd.merge(df_anim, df_power, on='UP', how='left')
    df_anim['Profit_per_MW_day'] = (
        df_anim['Total_Profit'] / df_anim['Power MW'].replace(0, np.nan)
    ).fillna(0)

    # Profit diario (NO acumulado) por MA
    daily_anim = df_anim.groupby(['Day','MA'], observed=True)['Profit_per_MW_day'].sum().reset_index()
    daily_anim = daily_anim.sort_values('Day')
    daily_anim['MA'] = daily_anim['MA'].astype(str)
    daily_anim['Day_str'] = daily_anim['Day'].dt.strftime('%Y-%m-%d')

    # Top 12 por día
    frames_list = []
    for day_val in sorted(daily_anim['Day_str'].unique()):
        snap = daily_anim[daily_anim['Day_str'] == day_val].nlargest(12, 'Profit_per_MW_day')
        snap = snap.sort_values('Profit_per_MW_day', ascending=True)
        frames_list.append(snap)

    if frames_list:
        color_anim = '#f59e0b' if tech_anim == 'Solar PV' else '#34d399'
        r_a, g_a, b_a = px.colors.hex_to_rgb(color_anim)

        # Rango fijo del eje X: máximo de todos los días
        x_max = daily_anim['Profit_per_MW_day'].max() * 1.18

        first = frames_list[0]
        fig_anim = go.Figure(
            data=[go.Bar(
                x=first['Profit_per_MW_day'],
                y=first['MA'],
                orientation='h',
                marker_color=color_anim,
                text=[f"{v:,.1f} €/MW" for v in first['Profit_per_MW_day']],
                textposition='outside',
            )],
            layout=go.Layout(
                title=dict(
                    text=f"<b>{tech_anim}</b> · " + t('Daily Profit/MW – ','Profit/MW Diario – ') + (first['Day_str'].iloc[0] if not first.empty else ''),
                    font=dict(size=13, color="#1e293b"), x=0, xanchor='left'),
                xaxis=dict(
                    title=t("Daily Profit/MW (€)","Profit/MW Diario (€)"),
                    gridcolor="#e2e8f0", range=[0, x_max],
                    fixedrange=True),
                yaxis=dict(gridcolor="rgba(0,0,0,0)", fixedrange=True),
                paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                font=dict(family="Inter", color="#475569"),
                title_font=dict(family="Inter", color="#1e293b", size=13),
                # Botones fijos en esquina superior izquierda, fuera del área del gráfico
                updatemenus=[dict(
                    type="buttons", showactive=False,
                    direction="left",
                    x=0.0, xanchor="left",
                    y=1.18, yanchor="top",
                    pad=dict(r=8, t=0),
                    bgcolor="#f1f5f9", bordercolor="#e2e8f0", borderwidth=1,
                    font=dict(size=12, color="#1e293b"),
                    buttons=[
                        dict(label="▶  Play",
                             method="animate",
                             args=[None, dict(frame=dict(duration=400, redraw=True),
                                              fromcurrent=True,
                                              transition=dict(duration=200, easing="linear"))]),
                        dict(label="⏸  Pause",
                             method="animate",
                             args=[[None], dict(frame=dict(duration=0, redraw=False),
                                                mode="immediate",
                                                transition=dict(duration=0))])
                    ]
                )],
                sliders=[dict(
                    steps=[dict(
                        method="animate",
                        args=[[f"frame_{i}"],
                              dict(mode="immediate",
                                   frame=dict(duration=400, redraw=True),
                                   transition=dict(duration=200))],
                        label=frames_list[i]['Day_str'].iloc[0] if not frames_list[i].empty else str(i)
                    ) for i in range(len(frames_list))],
                    transition=dict(duration=200),
                    x=0.0, y=-0.06,
                    len=1.0,
                    bgcolor="#f1f5f9",
                    bordercolor="#e2e8f0",
                    activebgcolor=color_anim,
                    currentvalue=dict(
                        font=dict(size=11, color="#475569"),
                        prefix=t("Date: ","Fecha: "),
                        visible=True, xanchor="center"),
                )],
                margin=dict(l=10, r=110, t=90, b=60),
                height=500,
                showlegend=False,
            ),
            frames=[go.Frame(
                data=[go.Bar(
                    x=snap['Profit_per_MW_day'],
                    y=snap['MA'],
                    orientation='h',
                    marker_color=[
                        f"rgba({r_a},{g_a},{b_a},{max(0.35, v/snap['Profit_per_MW_day'].max()) if snap['Profit_per_MW_day'].max()>0 else 0.7})"
                        for v in snap['Profit_per_MW_day']],
                    text=[f"{v:,.1f} €/MW" for v in snap['Profit_per_MW_day']],
                    textposition='outside',
                )],
                layout=go.Layout(
                    title=dict(
                        text=f"<b>{tech_anim}</b> · " + t('Daily Profit/MW – ','Profit/MW Diario – ') + (snap['Day_str'].iloc[0] if not snap.empty else ''),
                        font=dict(size=13, color="#1e293b"), x=0, xanchor='left'),
                ),
                name=f"frame_{i}"
            ) for i, snap in enumerate(frames_list)]
        )
        st.plotly_chart(fig_anim, use_container_width=True)
        st.caption(t("Press ▶ Play or drag the slider to navigate day by day.",
                     "Pulsa ▶ Play o arrastra el slider para navegar día a día."))

    gc.collect()

# ==============================================================================
# SECCIÓN 2: ANÁLISIS MRA
# ==============================================================================
elif seleccion_menu == name_mra:
    section_header("⚡", t("MRA Analysis – Technology – Installation", "Análisis MRA – Tecnología – Instalación"))
    try:
        only_qualified = st.checkbox(t("Only qualified in Ancillary Services","Solo cualificadas en Servicios de Ajuste"), value=True)
        if only_qualified:
            mask_active_mra = (allh['Profit_rt'] != 0) | (allh['Profit_b'] != 0) | (allh['Profit_t'] != 0)
            valid_ups_mra = allh.loc[mask_active_mra, 'UP'].unique()
            allh_mra = allh.loc[allh['UP'].isin(valid_ups_mra)]
        else:
            allh_mra = allh

        PROFIT_MAP = {
            'Profit_rt':'RRTT F2','Profit_tr':'RT5','Profit_tr_s':'RT5_strategy',
            'Profit_t':'Tertiary','Profit_rr':'RR','Profit_b':'Sec. Band',
            'Profit_se':'Sec. Activation','Profit_i':'Intraday'
        }

        f_ma, f_tech, f_up = st.columns(3)
        with f_ma:
            qualified_MAs = sorted(allh_mra['MA'].unique()) if not allh_mra.empty else [t('No data','Sin datos')]
            default_ma_idx = list(qualified_MAs).index('GNERA') if 'GNERA' in qualified_MAs else 0
            sel_ma = st.selectbox(t("1. Market Agent (MA)","1. Representante (MA)"), qualified_MAs, index=default_ma_idx)
        with f_tech:
            tech_opts = sorted(allh_mra.loc[allh_mra['MA']==sel_ma,'Tech'].unique()) if sel_ma != t('No data','Sin datos') else [t('No data','Sin datos')]
            default_tech_idx = list(tech_opts).index('Wind') if 'Wind' in tech_opts else 0
            sel_tech = st.selectbox(t("2. Technology","2. Tecnología"), tech_opts, index=default_tech_idx)
        with f_up:
            up_rt5 = allh_mra.loc[(allh_mra['MA']==sel_ma) & (allh_mra['Tech']==sel_tech)]
            up_opts = [t('Any UP','Cualquier UP')] + sorted(up_rt5['UP'].unique().tolist())
            sel_up = st.selectbox(t("3. Production Unit (UP)","3. Unidad (UP)"), up_opts)

        if sel_up == t('Any UP','Cualquier UP'): up_df = allh_mra.loc[allh_mra['UP'].isin(up_rt5['UP'].unique())].copy()
        else: up_df = allh_mra.loc[allh_mra['UP'] == sel_up].copy()

        if up_df.empty:
            st.warning(t("No data available.","No hay datos disponibles."))
        else:
            cols_to_groupby = ['Tech','MA','Day','hour'] if is_hourly else ['Tech','MA','Day']
            numeric_cols_avail = ['PBF','Energy_p48','Energy_RT1','Profit_rt','Profit_t','Profit_rr',
                                  'Profit_se','Profit_b','Profit_i','Profit_tr','Profit_tr_s','Profit_p48','Energy_tr',
                                  'Energy_rt','Energy_t','Energy_rr','Energy_se','Energy_i','Rev_spot']
            for c in numeric_cols_avail:
                if c not in up_df.columns: up_df[c] = 0.0

            up_hourly = up_df.groupby(cols_to_groupby, observed=True)[numeric_cols_avail].sum(numeric_only=True).reset_index()
            up_hourly['Year_Month'] = up_hourly['Day'].dt.to_period('M').astype(str)
            up_hourly['Profit_AASS'] = up_hourly[['Profit_rt','Profit_t','Profit_rr','Profit_se','Profit_b','Profit_tr_s']].sum(axis=1)
            up_hourly['Energy_AASS'] = up_hourly[['Energy_rt','Energy_t','Energy_rr','Energy_se','Energy_tr']].sum(axis=1)
            if up_hourly['Profit_p48'].sum() == 0 and 'Rev_spot' in up_hourly.columns:
                up_hourly['Profit_p48'] = up_hourly['Rev_spot']
            cols_mkts = ['Profit_rt','Profit_t','Profit_rr','Profit_b','Profit_se','Profit_i','Profit_tr_s']
            up_hourly['Profit_total'] = up_hourly[cols_mkts].sum(axis=1)

            # --- KPI CARDS ---
            total_row = up_hourly[cols_mkts + ['Profit_p48','Energy_p48','Energy_tr']].sum(numeric_only=True)
            energy_base = total_row.get('Energy_p48',0) - total_row.get('Energy_tr',0)
            if energy_base == 0: energy_base = 1
            total_aass = total_row[cols_mkts].sum()

            k1, k2, k3, k4 = st.columns(4)
            with k1: st.markdown(metric_card(t("Total AASS Profit","Profit AASS Total"), f"{total_aass:,.0f}", unit=" €", positive=total_aass>=0), unsafe_allow_html=True)
            with k2: st.markdown(metric_card(t("Spot Revenue","Ingreso Spot"), f"{total_row.get('Profit_p48',0):,.0f}", unit=" €"), unsafe_allow_html=True)
            with k3: st.markdown(metric_card(t("Avg AASS €/MWh","AASS €/MWh medio"), f"{total_aass/energy_base:,.2f}", unit=" €/MWh", positive=total_aass>=0), unsafe_allow_html=True)
            with k4: st.markdown(metric_card(t("Days Analyzed","Días analizados"), f"{len(up_hourly['Day'].unique()):,}"), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            # --- WATERFALL ---
            section_header("💧", t("Unit Profit Breakdown (€/MWh)","Desglose de Profit Unitario (€/MWh)"))
            wf_data = {
                'Spot':        total_row.get('Profit_p48',0)/energy_base,
                'RRTT Ph2':    total_row.get('Profit_rt',0)/energy_base,
                'RT5_strategy': total_row.get('Profit_tr_s',0)/energy_base,
                'Tertiary':    total_row.get('Profit_t',0)/energy_base,
                'RR':          total_row.get('Profit_rr',0)/energy_base,
                'Sec. Band':   total_row.get('Profit_b',0)/energy_base,
                'Sec. Energy': total_row.get('Profit_se',0)/energy_base,
                'Intras':      total_row.get('Profit_i',0)/energy_base,
            }
            wf_data = {k:v for k,v in wf_data.items() if abs(v) > 0.01}

            if wf_data:
                wf_labels = list(wf_data.keys()) + ['TOTAL']
                wf_vals   = list(wf_data.values())
                total_val = sum(wf_vals)
                measures = ['absolute'] + ['relative']*(len(wf_vals)-1) + ['total']

                colors_wf = []
                for i, m in enumerate(measures):
                    if m == 'absolute': colors_wf.append(C_BASE)
                    elif m == 'total':  colors_wf.append(C_ACCENT)
                    else: colors_wf.append(C_POS if wf_vals[i] >= 0 else C_NEG)

                fig_wf = go.Figure(go.Waterfall(
                    name="", orientation="v",
                    measure=measures,
                    x=wf_labels,
                    y=wf_vals + [total_val],
                    connector=dict(line=dict(color="#4b5563", width=1, dash="dot")),
                    increasing=dict(marker=dict(color=C_POS)),
                    decreasing=dict(marker=dict(color=C_NEG)),
                    totals=dict(marker=dict(color=C_ACCENT)),
                    text=[f"{v:+,.1f}" for v in wf_vals] + [f"{total_val:,.1f}"],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b><br>%{y:,.2f} €/MWh<extra></extra>"
                ))
                fig_wf.update_layout(
                    title="", yaxis_title="€/MWh",
                    paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                    font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                    margin=dict(l=10,r=10,t=20,b=10), height=380,
                    showlegend=False
                )
                fig_wf.update_xaxes(gridcolor="#e2e8f0")
                fig_wf.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8")

                # Barras acumuladas totales
                profit_total_data = total_row[[c for c in cols_mkts if c in total_row.index]].sort_values(ascending=False)
                profit_total_data.index = [PROFIT_MAP.get(i,i) for i in profit_total_data.index]
                bar_colors = [C_POS if x >= 0 else C_NEG for x in profit_total_data]
                fig_bar = go.Figure(go.Bar(
                    x=profit_total_data.values, y=profit_total_data.index,
                    orientation='h', marker_color=bar_colors,
                    text=[f"{int(v):,} €" for v in profit_total_data.values],
                    textposition='outside',
                    hovertemplate="<b>%{y}</b><br>%{x:,.0f} €<extra></extra>"
                ))
                fig_bar.update_layout(
                    title=t("Total Accumulated Profit by Market","Profit Acumulado por Mercado"),
                    paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                    font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                    xaxis_title="€", yaxis_title="",
                    margin=dict(l=10,r=80,t=40,b=10), height=380,
                    showlegend=False
                )
                fig_bar.update_xaxes(gridcolor="#e2e8f0")
                fig_bar.update_yaxes(gridcolor="#e2e8f0")

                col_wf, col_br = st.columns([1.2, 1])
                with col_wf: st.plotly_chart(fig_wf, use_container_width=True)
                with col_br: st.plotly_chart(fig_bar, use_container_width=True)

            # --- EVOLUCIÓN DIARIA ---
            section_header("📅", t("Daily Profit Breakdown","Desglose Diario de Beneficio"))
            daily_data = up_hourly.groupby('Day')[cols_mkts].sum().reset_index()
            daily_data['Day_str'] = daily_data['Day'].dt.strftime('%d/%m/%Y')

            color_seq = ["#00d4ff","#7c3aed","#f59e0b","#34d399","#f87171","#a78bfa","#fb923c"]
            fig_daily = go.Figure()
            for i, col in enumerate(cols_mkts):
                label = PROFIT_MAP.get(col, col)
                fig_daily.add_trace(go.Bar(
                    x=daily_data['Day'], y=daily_data[col],
                    name=label,
                    marker_color=color_seq[i % len(color_seq)],
                    hovertemplate=f"<b>{label}</b><br>%{{x|%d/%m/%Y}}<br>%{{y:,.0f}} €<extra></extra>"
                ))
            fig_daily.update_layout(
                barmode='stack', yaxis_title="Profit (€)",
                paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                legend=dict(orientation='h', yanchor='bottom', y=1.01, xanchor='right', x=1, font=dict(size=10)),
                hovermode='x unified',
                margin=dict(l=10,r=10,t=50,b=10), height=400
            )
            fig_daily.update_xaxes(gridcolor="#e2e8f0")
            fig_daily.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8")
            st.plotly_chart(fig_daily, use_container_width=True)

            # --- TABLA RESUMEN ---
            st.markdown("---")
            section_header("📋", t("Performance Summary","Resumen de Rendimiento"))
            date_range_days = (up_hourly['Day'].max() - up_hourly['Day'].min()).days
            group_col = 'Day' if date_range_days <= 10 else 'Year_Month'
            group_col_name = 'Date' if group_col == 'Day' else 'Month'

            up_summary = up_hourly.groupby([group_col], observed=True)[['PBF','Energy_p48','Energy_RT1','Profit_AASS','Profit_tr_s','Profit_i']].sum(numeric_only=True).reset_index()
            up_summary['% P48 vs PBF'] = up_summary['Energy_p48'] / up_summary['PBF'].replace(0,np.nan)
            up_summary['% RT1 vs PBF'] = -up_summary['Energy_RT1'] / up_summary['PBF'].replace(0,np.nan)
            up_summary['Intras €/MWh']  = up_summary['Profit_i'] / up_summary['Energy_p48'].replace(0,np.nan)
            up_summary['AASS €/MWh']    = up_summary['Profit_AASS'] / up_summary['Energy_p48'].replace(0,np.nan)

            df_table = up_summary[[group_col,'% P48 vs PBF','% RT1 vs PBF','Profit_tr_s','Profit_AASS','Profit_i','Intras €/MWh','AASS €/MWh']].copy()
            df_table.columns = [group_col_name,'% P48 vs PBF','% RT1 vs PBF','Real Time (€)','AASS (€)','Intras (€)','Intras (€/MWh)','AASS (€/MWh)']
            df_table[group_col_name] = df_table[group_col_name].astype(str)

            st.dataframe(
                df_table.set_index(group_col_name).style
                .format({'% P48 vs PBF':'{:.1%}','% RT1 vs PBF':'{:.1%}',
                         'Real Time (€)':'{:,.0f} €','AASS (€)':'{:,.0f} €',
                         'Intras (€)':'{:,.0f} €','Intras (€/MWh)':'{:.2f} €','AASS (€/MWh)':'{:.2f} €'})
                .background_gradient(subset=['AASS (€)','Real Time (€)'], cmap='RdYlGn'),
                use_container_width=True
            )

    except Exception as e:
        st.error(f"{t('Error processing MRA:','Error procesando MRA:')} {e}")
    gc.collect()

# ==============================================================================
# SECCIÓN 3: DETALLE RT5
# ==============================================================================
elif seleccion_menu == name_rt5:
    section_header("📋", t("RT5 Detail: Prices & Offers","Detalle RT5: Precios y Ofertas"))
    try:
        filtered_rt5 = allh.loc[(allh['Tech'].isin(['Solar PV','Wind'])) & (allh['Profit_tr_s'] != 0)].copy()
        filtered_rt5['Price_RT5'] = filtered_rt5['Rev_tr'] / filtered_rt5['Energy_tr'].replace(0,np.nan)
        filtered_rt5.dropna(subset=['Price_RT5'], inplace=True)

        if filtered_rt5.empty:
            st.info(t("No offers matched in RT5.","No hay ofertas casadas en RT5."))
        else:
            max_name = 'Max Bid (€)' if is_hourly else 'Max Daily Avg (€)'
            min_name = 'Min Bid (€)' if is_hourly else 'Min Daily Avg (€)'

            col_rt_a1, col_rt_a2 = st.columns(2)
            with col_rt_a1:
                st.markdown(f"**{t('All Market Overview','Resumen de Todo el Mercado')}**")
                total_p_ma = filtered_rt5.groupby('MA', observed=True)['Profit_tr_s'].sum()
                e_p48_tr_diff_ma = filtered_rt5['Energy_p48'] - filtered_rt5['Energy_tr']
                eur_mwh_r_ma = filtered_rt5.groupby('MA', observed=True).apply(
                    lambda x: x['Profit_tr_s'].sum() / e_p48_tr_diff_ma[x.index].sum()
                ).replace([np.inf,-np.inf],0).fillna(0)
                w_avg_bid_ma = filtered_rt5.groupby('MA', observed=True).apply(
                    lambda x: (x['Price_RT5']*x['Energy_tr']).sum() / x['Energy_tr'].sum()
                ).replace([np.inf,-np.inf],0).fillna(0)
                res_ma = pd.DataFrame({
                    'Total Profit RT5':total_p_ma,'€/MWh_resource':eur_mwh_r_ma,
                    'Weighted Avg Bid':w_avg_bid_ma,
                    max_name:filtered_rt5.groupby('MA', observed=True)['Price_RT5'].max(),
                    min_name:filtered_rt5.groupby('MA', observed=True)['Price_RT5'].min()
                })
                filtered_res_ma = res_ma.dropna(subset=[min_name]).sort_values('Total Profit RT5', ascending=False)
                if not filtered_res_ma.empty:
                    st.dataframe(
                        filtered_res_ma.style.format({
                            'Total Profit RT5':'{:,.2f} €','€/MWh_resource':'{:.2f}',
                            'Weighted Avg Bid':'{:.2f}',max_name:'{:.2f}',min_name:'{:.2f}'
                        }).background_gradient(subset=['Total Profit RT5'], cmap='RdYlGn'),
                        use_container_width=True
                    )

            with col_rt_a2:
                st.markdown(f"**{t('Specific Installations (FCTRAV2, PEVER)','Instalaciones Específicas')}**")
                up_rt5_v = filtered_rt5.loc[filtered_rt5['UP'].isin(['FCTRAV2','PEVER'])]
                if not up_rt5_v.empty:
                    e_p48_tr_diff_v = up_rt5_v['Energy_p48'] - up_rt5_v['Energy_tr']
                    eur_mwh_r_v = up_rt5_v.groupby('MA', observed=True).apply(
                        lambda x: x['Profit_tr_s'].sum() / e_p48_tr_diff_v[x.index].sum()
                    ).replace([np.inf,-np.inf],0).fillna(0)
                    w_avg_bid_v = up_rt5_v.groupby('MA', observed=True).apply(
                        lambda x: (x['Price_RT5']*x['Energy_tr']).sum() / x['Energy_tr'].sum()
                    ).replace([np.inf,-np.inf],0).fillna(0)
                    res_v = pd.DataFrame({
                        'Total Profit RT5':up_rt5_v.groupby('MA', observed=True)['Profit_tr_s'].sum(),
                        '€/MWh_resource':eur_mwh_r_v,'Weighted Avg Bid':w_avg_bid_v,
                        max_name:up_rt5_v.groupby('MA', observed=True)['Price_RT5'].max(),
                        min_name:up_rt5_v.groupby('MA', observed=True)['Price_RT5'].min()
                    }).dropna(subset=[min_name]).sort_values('Total Profit RT5', ascending=False)
                    st.dataframe(
                        res_v.style.format({
                            'Total Profit RT5':'{:,.2f} €','€/MWh_resource':'{:.2f}',
                            'Weighted Avg Bid':'{:.2f}',max_name:'{:.2f}',min_name:'{:.2f}'
                        }),
                        use_container_width=True
                    )

            # --- TOP 10 POR TECNOLOGÍA ---
            st.markdown("---")
            section_header("🏆", t("Top 10 Market Agents by Total Profit RT5","Top 10 Representantes por Beneficio Total RT5"))
            col_top_s, col_top_w = st.columns(2)

            def plot_top10_plotly(df, tech, color_scale):
                df_t = df[df['Tech'] == tech]
                if df_t.empty: return None
                ma_profit = df_t.groupby('MA', observed=True)['Profit_tr_s'].sum().reset_index()
                top10 = ma_profit.nlargest(10,'Profit_tr_s')
                top10 = top10[top10['Profit_tr_s'] > 0].copy()
                if top10.empty: return None
                top10 = top10.sort_values('Profit_tr_s')
                fig = go.Figure(go.Bar(
                    x=top10['Profit_tr_s'], y=top10['MA'],
                    orientation='h',
                    marker=dict(color=top10['Profit_tr_s'], colorscale=color_scale, showscale=False),
                    text=[f"{int(v):,} €" for v in top10['Profit_tr_s']],
                    textposition='outside',
                    hovertemplate="<b>%{y}</b><br>Profit RT5: %{x:,.0f} €<extra></extra>"
                ))
                fig.update_layout(
                    title=dict(text=f"<b>{tech}</b>", font=dict(size=13, color="#1e293b")),
                    xaxis_title="Total Profit RT5 (€)", yaxis_title="",
                    paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                    font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                    margin=dict(l=10,r=80,t=45,b=10), height=400
                )
                fig.update_xaxes(gridcolor="#e2e8f0")
                fig.update_yaxes(gridcolor="#e2e8f0")
                return fig

            with col_top_s:
                fig_ts = plot_top10_plotly(filtered_rt5,'Solar PV','YlOrRd')
                if fig_ts: st.plotly_chart(fig_ts, use_container_width=True)
                else: st.info(t("No Solar PV data.","Sin datos Solar PV."))
            with col_top_w:
                fig_tw = plot_top10_plotly(filtered_rt5,'Wind','Greens')
                if fig_tw: st.plotly_chart(fig_tw, use_container_width=True)

            # --- EVOLUCIÓN RT5 ---
            st.markdown("---")
            section_header("📈", t("RT5 Profit Evolution (All Agents)","Evolución de Ingresos RT5 (Todos los Representantes)"))

            date_range_days = (filtered_rt5['Day'].max() - filtered_rt5['Day'].min()).days
            if pd.isna(date_range_days): date_range_days = 0
            if date_range_days <= 60:
                filtered_rt5['time_x'] = filtered_rt5['Day']
                time_label = "Day"
            else:
                filtered_rt5['time_x'] = filtered_rt5['Day'].dt.to_period('M').astype(str)
                time_label = "Month"

            col_evo_s, col_evo_w = st.columns(2)

            def plot_evo_plotly(df, tech, color):
                df_t = df[df['Tech'] == tech]
                if df_t.empty: return None
                evo = df_t.groupby('time_x', observed=True)['Profit_tr_s'].sum().reset_index().sort_values('time_x')
                _r, _g, _b = px.colors.hex_to_rgb(color)
                _fill = f"rgba({_r},{_g},{_b},0.08)"
                fig = go.Figure(go.Scatter(
                    x=evo['time_x'], y=evo['Profit_tr_s'],
                    mode='lines+markers',
                    line=dict(color=color, width=2.5),
                    marker=dict(color=color, size=6, line=dict(color='white', width=1)),
                    fill='tozeroy',
                    fillcolor=_fill,
                    hovertemplate="<b>%{x}</b><br>Profit RT5: %{y:,.0f} €<extra></extra>"
                ))
                fig.update_layout(
                    title=dict(text=f"<b>{tech}</b>", font=dict(size=13, color="#1e293b")),
                    xaxis_title="", yaxis_title="Total Profit RT5 (€)",
                    paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                    font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                    margin=dict(l=10,r=10,t=45,b=10), height=360
                )
                fig.update_xaxes(gridcolor="#e2e8f0", tickangle=-30)
                fig.update_yaxes(gridcolor="#e2e8f0")
                return fig

            with col_evo_s:
                fig_es = plot_evo_plotly(filtered_rt5,'Solar PV','#f59e0b')
                if fig_es: st.plotly_chart(fig_es, use_container_width=True)
            with col_evo_w:
                fig_ew = plot_evo_plotly(filtered_rt5,'Wind','#34d399')
                if fig_ew: st.plotly_chart(fig_ew, use_container_width=True)

    except Exception as e:
        st.error(f"Error RT5: {e}")
    gc.collect()

# ==============================================================================
# SECCIÓN 4: ANÁLISIS GNERA
# ==============================================================================
elif seleccion_menu == name_gnera:
    section_header("📊", t("Gnera Analysis","Análisis Gnera"))
    try:
        POTENCIA_INSTALADA = {'EOTMR':87.6,'LECDE':9.6,'PEVER':182.3,'PEVER2':29.8}
        UPS_INTERES = list(POTENCIA_INSTALADA.keys())
        PROFIT_MAP = {
            'Profit_rt':'RRTT F2','Profit_tr':'RT5','Profit_tr_s':'RT5_strategy',
            'Profit_t':'Tertiary','Profit_rr':'RR','Profit_b':'Sec. Band','Profit_se':'Sec. Activation'
        }
        profit_cols_to_sum = list(PROFIT_MAP.keys())

        gnwi = allh.loc[(allh['MA']=='GNERA') & (allh['Tech']=='Wind') & (allh['UP'].isin(UPS_INTERES))].copy()
        if gnwi.empty:
            st.info(t("No data for GNERA Wind.","No hay datos de GNERA Wind."))
        else:
            gnwi['Profit_Total_Extra'] = gnwi[[c for c in profit_cols_to_sum if c in gnwi.columns]].sum(axis=1)
            gnwi['Potencia_MW'] = gnwi['UP'].map(POTENCIA_INSTALADA)
            df_agg = gnwi.groupby('UP', observed=True)[[c for c in profit_cols_to_sum if c in gnwi.columns]+['Profit_Total_Extra']].sum(numeric_only=True).reset_index()
            df_agg['Potencia_MW'] = df_agg['UP'].map(POTENCIA_INSTALADA)
            for col in [c for c in profit_cols_to_sum if c in df_agg.columns]+['Profit_Total_Extra']:
                df_agg[col] = df_agg[col] / df_agg['Potencia_MW']

            # Heatmap Plotly — un único heatmap con todas las columnas incluido TOTAL
            section_header("🌡️", t("Summary (€/MW) Heatmap","Resumen (€/MW) como Heatmap"))
            df_hm = df_agg.set_index('UP').drop(columns=['Potencia_MW'])
            comp_cols = [c for c in df_hm.columns if c != 'Profit_Total_Extra']
            all_cols  = comp_cols + (['Profit_Total_Extra'] if 'Profit_Total_Extra' in df_hm.columns else [])
            display_cols = [PROFIT_MAP.get(c,c) for c in comp_cols] + \
                           ([t('TOTAL','TOTAL')] if 'Profit_Total_Extra' in df_hm.columns else [])

            z_vals = df_hm[all_cols].values
            # Detectar color del texto según contraste
            text_vals = [[f"{v:,.0f}" for v in row] for row in z_vals]

            fig_hm = go.Figure(go.Heatmap(
                z=z_vals,
                x=display_cols,
                y=df_hm.index.tolist(),
                colorscale=[
                    [0.0,  "#b91c1c"],
                    [0.35, "#fca5a5"],
                    [0.5,  "#f8fafc"],
                    [0.65, "#86efac"],
                    [1.0,  "#15803d"],
                ],
                zmid=0,
                text=text_vals,
                texttemplate="<b>%{text}</b>",
                textfont=dict(size=12),
                hovertemplate="<b>%{y}</b> · <b>%{x}</b><br>%{z:,.1f} €/MW<extra></extra>",
                colorbar=dict(
                    title=dict(text="€/MW", font=dict(color="#475569", size=11)),
                    tickfont=dict(color="#475569", size=10),
                    thickness=14, len=0.9,
                    outlinewidth=0,
                    bgcolor="rgba(255,255,255,0)",
                )
            ))

            # Línea vertical separando componentes del total
            if 'Profit_Total_Extra' in df_hm.columns:
                n_comp = len(comp_cols)
                fig_hm.add_shape(
                    type="line", xref="x", yref="paper",
                    x0=n_comp - 0.5, x1=n_comp - 0.5, y0=0, y1=1,
                    line=dict(color="#94a3b8", width=2, dash="dot")
                )

            fig_hm.update_layout(
                paper_bgcolor="#ffffff",
                plot_bgcolor="#ffffff",
                font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                margin=dict(l=10, r=60, t=20, b=60),
                height=max(220, len(df_hm) * 72 + 80),
                xaxis=dict(side='bottom', tickangle=-25, tickfont=dict(size=11),
                           gridcolor="rgba(0,0,0,0)"),
                yaxis=dict(tickfont=dict(size=11), gridcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_hm, use_container_width=True)

            # Gráfico de barras del TOTAL por UP debajo
            if 'Profit_Total_Extra' in df_hm.columns:
                df_bar_gnera = df_hm[['Profit_Total_Extra']].reset_index()
                df_bar_gnera.columns = ['UP', 'Total_EuroMW']
                df_bar_gnera = df_bar_gnera.sort_values('Total_EuroMW', ascending=True)
                bar_colors = [C_POS if v >= 0 else C_NEG for v in df_bar_gnera['Total_EuroMW']]
                fig_bar_g = go.Figure(go.Bar(
                    x=df_bar_gnera['Total_EuroMW'], y=df_bar_gnera['UP'],
                    orientation='h',
                    marker_color=bar_colors,
                    text=[f"{v:,.0f} €/MW" for v in df_bar_gnera['Total_EuroMW']],
                    textposition='outside',
                    hovertemplate="<b>%{y}</b><br>Total: %{x:,.1f} €/MW<extra></extra>"
                ))
                fig_bar_g.update_layout(
                    title=t("Total Profit by Installation (€/MW)","Profit Total por Instalación (€/MW)"),
                    paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                    font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                    margin=dict(l=10, r=100, t=45, b=10),
                    height=max(200, len(df_bar_gnera) * 55 + 60),
                    showlegend=False,
                    xaxis=dict(gridcolor="#e2e8f0", zerolinecolor="#94a3b8"),
                    yaxis=dict(gridcolor="rgba(0,0,0,0)"),
                )
                st.plotly_chart(fig_bar_g, use_container_width=True)

    except Exception as e:
        st.error(f"Error Gnera: {e}")
    gc.collect()

# ==============================================================================
# SECCIÓN 5: BENEFICIO VERBUND
# ==============================================================================
elif seleccion_menu == name_verbund:
    section_header("💶", t("Verbund Profit (€)","Beneficio Verbund Servicios de Ajuste (€)"))
    try:
        INPUT_DATA = {
            'FCTRAV2':['Calatrava',41.0,0.5],'EAYAMON':['Ayamonte',26.0,0.5],
            'UPAYM':['Ayamonte',26.0,0.5],
            'EGST146':['Barroso',21.6,0.5],
            'PEVER':['Sorolla 1',182.3,0.6],'PEVER2':['Sorolla Mallén',29.8,0.6],
            'CLIFV30':['Pinos Puente 1',0.0,0.0],'CLIFV31':['Pinos Puente 2',0.0,0.0],'CLIFV32':['Pinos Puente 3',0.0,0.0],
            'UPBUS':['Buseco',0.0,0.0],'UPLMP':['Loma',0.0,0.0],'UPSLN':['La Solana',0.0,0.0],
            'GALPS59':['Buseco_Galp',0.0,0.0],'GALPS57':['Loma_Galp',0.0,0.0],'GALPS56':['La Solana_Galp',0.0,0.0],
            'CLIWI12':['Buseco_Holaluz',0.0,0.0],'CLIWI15':['Loma_Holaluz',0.0,0.0],'CLIFV20':['La Solana_Holaluz',0.0,0.0],
            'EFGNRA':['Bodenaya + Pico + Others',0.0,0.0]
        }
        profit_cols_v = ['Profit_rt','Profit_tr_s','Profit_t','Profit_rr','Profit_b','Profit_se','Profit_i']
        df_v = allh.loc[allh['UP'].isin(INPUT_DATA.keys())]
        df_agg_v = df_v.groupby('UP', observed=True)[[c for c in profit_cols_v if c in df_v.columns]].sum(numeric_only=True).reindex(list(INPUT_DATA.keys())).reset_index().fillna(0)
        df_agg_v['Total Profit'] = df_agg_v.iloc[:,1:].sum(axis=1)
        df_agg_v['Verbund_Pct'] = [val[2] for val in INPUT_DATA.values()]
        df_agg_v['Profit Verbund'] = df_agg_v['Total Profit'] * df_agg_v['Verbund_Pct']
        df_agg_v['Potencia MW'] = [val[1] for val in INPUT_DATA.values()]
        df_agg_v['Profit Verbund / MW'] = np.where(df_agg_v['Potencia MW']>0, df_agg_v['Profit Verbund']/df_agg_v['Potencia MW'], 0)

        # ── Eliminar filas donde todos los valores numéricos de mercado son cero ──
        profit_avail = [c for c in profit_cols_v if c in df_agg_v.columns]
        mask_nonzero = df_agg_v[profit_avail].abs().sum(axis=1) > 0
        df_agg_v = df_agg_v[mask_nonzero].copy()

        totales = df_agg_v.select_dtypes(include=[np.number]).sum()
        totales['UP'] = 'Total'
        totales['Profit Verbund / MW'] = totales['Profit Verbund']/totales['Potencia MW'] if totales['Potencia MW']>0 else 0
        df_final_v = pd.concat([df_agg_v, pd.DataFrame([totales])], ignore_index=True)
        # Installation column: map from INPUT_DATA, fallback to UP itself
        df_final_v.insert(1,'Installation',
            df_final_v['UP'].map({k: v[0] for k,v in INPUT_DATA.items()}).fillna(df_final_v['UP']))

        rename_dict = {
            'Profit_rt':'Profit RT F2','Profit_tr_s':'RT5','Profit_t':'Tertiary',
            'Profit_rr':'RR','Profit_b':'Secondary band','Profit_se':'Secondary Activation','Profit_i':'Intraday'
        }
        df_final_v = df_final_v.rename(columns=rename_dict)
        renamed_cols = [rename_dict.get(c,c) for c in profit_cols_v]
        cols_to_show = ['UP','Installation'] + [c for c in renamed_cols if c in df_final_v.columns] + ['Total Profit','Profit Verbund','Profit Verbund / MW']

        # KPI summary
        total_profit_verbund = df_final_v.loc[df_final_v['UP']=='Total','Profit Verbund'].values
        if len(total_profit_verbund):
            kv1, kv2, kv3 = st.columns(3)
            with kv1: st.markdown(metric_card(t("Total Verbund Profit","Profit Verbund Total"), f"{total_profit_verbund[0]:,.0f}", unit=" €", positive=total_profit_verbund[0]>=0), unsafe_allow_html=True)
            total_mw = df_agg_v['Potencia MW'].sum()
            if total_mw > 0:
                with kv2: st.markdown(metric_card(t("Verbund MW","MW Verbund"), f"{total_mw:,.0f}", unit=" MW"), unsafe_allow_html=True)
            pvmw = df_final_v.loc[df_final_v['UP']=='Total','Profit Verbund / MW'].values
            if len(pvmw):
                with kv3: st.markdown(metric_card(t("Profit / MW","Profit / MW"), f"{pvmw[0]:,.1f}", unit=" €/MW", positive=pvmw[0]>=0), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        num_cols = cols_to_show[2:]
        st.dataframe(
            df_final_v[cols_to_show].style
            .format({c:"{:,.2f} €" for c in num_cols})
            .background_gradient(subset=['Total Profit','Profit Verbund'], cmap='RdYlGn')
            .apply(lambda row: ['font-weight:bold; background:#f1f5f9' if row['UP']=='Total' else '' for _ in row], axis=1),
            use_container_width=True
        )

        # Gráfico de barras Verbund
        df_chart = df_final_v[df_final_v['UP']!='Total'].copy()
        df_chart = df_chart[df_chart['Profit Verbund'] != 0].sort_values('Profit Verbund', ascending=True)
        if not df_chart.empty:
            fig_v = go.Figure(go.Bar(
                x=df_chart['Profit Verbund'], y=df_chart['Installation'],
                orientation='h',
                marker_color=[C_POS if v>=0 else C_NEG for v in df_chart['Profit Verbund']],
                text=[f"{v:,.0f} €" for v in df_chart['Profit Verbund']],
                textposition='outside',
                hovertemplate="<b>%{y}</b><br>Profit Verbund: %{x:,.0f} €<extra></extra>"
            ))
            fig_v.update_layout(
                title=t("Verbund Profit by Installation","Profit Verbund por Instalación"),
                paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                xaxis_title="€", yaxis_title="",
                margin=dict(l=10,r=100,t=50,b=10), height=420,
                showlegend=False
            )
            fig_v.update_xaxes(gridcolor="#e2e8f0")
            fig_v.update_yaxes(gridcolor="#e2e8f0")
            st.plotly_chart(fig_v, use_container_width=True)

    except Exception as e:
        st.warning(f"Error Verbund: {e}")
    gc.collect()

# ==============================================================================
# SECCIÓN 6: EVOLUCIÓN INGRESOS
# ==============================================================================
elif seleccion_menu == name_evo:
    section_header("📈", t("Revenue Evolution by Market Agent and Technology","Evolución Ingresos por Representante y Tecnología"))
    try:
        col_e1, col_e2, col_e3 = st.columns([2, 2, 1])
        with col_e1:
            ma_input = st.selectbox(
                t("Market Agent (MA):","Representante (MA):"),
                sorted(allh['MA'].unique()),
                index=list(sorted(allh['MA'].unique())).index('GNERA') if 'GNERA' in allh['MA'].unique() else 0
            )
        with col_e2:
            tech_input = st.selectbox(
                t("Technology (Tech):","Tecnología (Tech):"),
                sorted(allh['Tech'].unique()),
                index=list(sorted(allh['Tech'].unique())).index('Wind') if 'Wind' in allh['Tech'].unique() else 0
            )
        with col_e3:
            granularity = st.radio(
                t("Granularity","Granularidad"),
                options=[t("Monthly","Mensual"), t("Daily","Diario")],
                index=0, key='evo_granularity'
            )
        is_daily_evo = (granularity == t("Daily","Diario"))

        df_evo_temp = allh.loc[(allh['MA']==ma_input) & (allh['Tech']==tech_input)]
        mask_active_ups = (df_evo_temp['Profit_rt']!=0) | (df_evo_temp['Profit_b']!=0) | (df_evo_temp['Profit_t']!=0)
        ups_validas = df_evo_temp.loc[mask_active_ups,'UP'].unique()
        df_evo = df_evo_temp.loc[df_evo_temp['UP'].isin(ups_validas)].copy()

        if df_evo.empty:
            st.info(t("No data for this combination.","No hay datos para esta combinación."))
        else:
            df_evo['Total_Profit'] = df_evo[['Profit_rt','Profit_tr_s','Profit_t','Profit_rr','Profit_b','Profit_se']].sum(axis=1)

            # Agrupar según granularidad
            if is_daily_evo:
                df_evo['x_axis'] = df_evo['Day'].dt.strftime('%Y-%m-%d')
                group_col = 'x_axis'
            else:
                df_evo['x_axis'] = df_evo['Day'].dt.to_period('M').astype(str)
                group_col = 'x_axis'

            df_evo_m = df_evo.groupby(['UP', group_col], observed=True).agg(
                Total_Profit=('Total_Profit','sum'), Total_Energy=('Energy_p48','sum')
            ).reset_index().sort_values(group_col)
            df_evo_m.rename(columns={group_col: 'x_axis'}, inplace=True)
            df_evo_m['Profit_per_MWh'] = df_evo_m['Total_Profit'] / df_evo_m['Total_Energy'].replace(0, np.nan)
            df_evo_m['Total_Profit_k'] = df_evo_m['Total_Profit'] / 1000
            df_evo_m['UP'] = df_evo_m['UP'].astype(str)

            # €/MW: join con potencia instalada
            df_evo_m = pd.merge(df_evo_m, df_power, on='UP', how='left')
            df_evo_m['Profit_per_MW'] = (
                df_evo_m['Total_Profit'] / df_evo_m['Power MW'].replace(0, np.nan)
            ).fillna(0)

            if len(ups_validas) > 20:
                st.warning(t("Showing top 20 UPs by Total Profit.","⚠️ Mostrando solo el Top 20 de UPs."))
                top_ups = df_evo_m.groupby('UP', observed=True)['Total_Profit'].sum().nlargest(20).index
                df_evo_m = df_evo_m[df_evo_m['UP'].isin(top_ups)]

            def make_line(df, y_col, title, y_label, color_col='UP'):
                tick_angle = -35 if not is_daily_evo else -50
                tick_size  = 9   if not is_daily_evo else 8
                fig = px.line(
                    df, x='x_axis', y=y_col, color=color_col,
                    markers=not is_daily_evo,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig.update_traces(line=dict(width=2), marker=dict(size=5 if not is_daily_evo else 0))
                fig.update_layout(
                    title=dict(text=title, font=dict(size=12, color="#1e293b")),
                    xaxis_title="", yaxis_title=y_label,
                    paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                    font=dict(family="Inter", color="#475569"),
                    title_font=dict(family="Inter", color="#1e293b", size=13),
                    legend=dict(title="", font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=10,r=10,t=45,b=10), height=360,
                    hovermode='x unified'
                )
                fig.update_xaxes(gridcolor="#e2e8f0", tickangle=tick_angle, tickfont=dict(size=tick_size))
                fig.update_yaxes(gridcolor="#e2e8f0")
                return fig

            # Layout 2×2: €/MWh y €/MW arriba; Producción y Profit k€ abajo
            c_evo1, c_evo2 = st.columns(2)
            c_evo3, c_evo4 = st.columns(2)

            with c_evo1:
                st.plotly_chart(make_line(df_evo_m,'Profit_per_MWh',
                    t("Profit (€/MWh)","Evolución Profit (€/MWh)"),"€/MWh"), use_container_width=True)
            with c_evo2:
                st.plotly_chart(make_line(df_evo_m,'Profit_per_MW',
                    t("Profit (€/MW installed)","Profit (€/MW instalado)"),"€/MW"), use_container_width=True)
            with c_evo3:
                st.plotly_chart(make_line(df_evo_m,'Total_Energy',
                    t("Production (MWh)","Producción (MWh)"),"MWh"), use_container_width=True)
            with c_evo4:
                st.plotly_chart(make_line(df_evo_m,'Total_Profit_k',
                    t("Total Profit (k€)","Profit Total (k€)"),"k€"), use_container_width=True)

    except Exception as e:
        st.warning(f"{t('Error:','Error:')} {e}")
    gc.collect()

# ==============================================================================
# SECCIÓN 7: COMERCIALIZADORAS (SUPPLY) — ANÁLISIS INTRADIARIO
# ==============================================================================
elif seleccion_menu == name_supply:
    section_header("🏪", t("Retailers – Intraday Market Performance (Supply)",
                            "Comercializadoras – Desempeño en Mercado Intradiario (Supply)"))
    try:
        # ── Filtro Tech == Supply ──────────────────────────────────────────────
        sp = allh[allh['Tech'] == 'Supply'].copy()

        if sp.empty:
            st.info(t("No Supply data found in the selected period.",
                      "No hay datos de tipo 'Supply' en el periodo seleccionado."))
            st.stop()

        # ── Conversión de columnas numéricas ──────────────────────────────────
        for col in ['PBF','Energy_p48','Energy_i','Rev_spot','Rev_i','Profit_i','Profit_p48']:
            if col in sp.columns:
                sp[col] = pd.to_numeric(sp[col], errors='coerce').fillna(0)
            else:
                sp[col] = 0.0

        sp['Abs_Energy_i']  = sp['Energy_i'].abs()
        sp['Abs_PBF']       = sp['PBF'].abs()

        # ── KPIs por MA ───────────────────────────────────────────────────────
        ma_kpis = sp.groupby('MA', observed=True).agg(
            Total_Energy_i   =('Energy_i',   'sum'),
            Vol_Abs_i        =('Abs_Energy_i','sum'),
            Vol_Abs_PBF      =('Abs_PBF',    'sum'),
            Total_Rev_i      =('Rev_i',      'sum'),
            Total_Profit_i   =('Profit_i',   'sum'),
            Total_Profit_p48 =('Profit_p48', 'sum'),
            Total_Energy_p48 =('Energy_p48', 'sum'),
        ).reset_index()
        ma_kpis['MA'] = ma_kpis['MA'].astype(str)

        # €/MWh intradiario sobre volumen negociado
        ma_kpis['Profit_per_MWh_i'] = np.where(
            ma_kpis['Vol_Abs_i'] > 0,
            ma_kpis['Total_Profit_i'] / ma_kpis['Vol_Abs_i'], 0)

        # Sobre-ingreso vs spot (%)
        ma_kpis['Inc_vs_Spot_pct'] = np.where(
            ma_kpis['Total_Profit_p48'].abs() > 0,
            (ma_kpis['Total_Profit_i'] / ma_kpis['Total_Profit_p48'].abs()) * 100, 0)

        # €/MWh sobre programa final P48
        ma_kpis['Profit_i_per_p48'] = np.where(
            ma_kpis['Total_Energy_p48'].abs() > 0,
            ma_kpis['Total_Profit_i'] / ma_kpis['Total_Energy_p48'].abs(), 0)

        # Cuota de mercado intradiario y diario
        vol_tot_i   = ma_kpis['Vol_Abs_i'].sum()
        vol_tot_pbf = ma_kpis['Vol_Abs_PBF'].sum()
        ma_kpis['Share_i_pct']   = ma_kpis['Vol_Abs_i']   / vol_tot_i   * 100 if vol_tot_i   > 0 else 0
        ma_kpis['Share_pbf_pct'] = ma_kpis['Vol_Abs_PBF'] / vol_tot_pbf * 100 if vol_tot_pbf > 0 else 0

        best = ma_kpis.sort_values('Total_Profit_i', ascending=False)
        worst = ma_kpis.sort_values('Total_Profit_i', ascending=True)

        # ── KPI CARDS ─────────────────────────────────────────────────────────
        total_profit_supply = ma_kpis['Total_Profit_i'].sum()
        n_ma_supply         = len(ma_kpis)
        best_ma             = best.iloc[0]['MA'] if not best.empty else '—'
        best_profit         = best.iloc[0]['Total_Profit_i'] if not best.empty else 0

        kc1, kc2, kc3, kc4 = st.columns(4)
        with kc1: st.markdown(metric_card(
            t("Total Intraday Profit","Profit Intradiario Total"),
            f"{total_profit_supply:,.0f}", unit=" €",
            positive=total_profit_supply >= 0), unsafe_allow_html=True)
        with kc2: st.markdown(metric_card(
            t("Retailers Analyzed","Comercializadoras Analizadas"),
            str(n_ma_supply)), unsafe_allow_html=True)
        with kc3: st.markdown(metric_card(
            t("Best Retailer","Mejor Comercializadora"),
            best_ma,
            delta=f"{best_profit:,.0f} €",
            positive=True), unsafe_allow_html=True)
        with kc4:
            avg_eur_mwh = (ma_kpis['Total_Profit_i'].sum() / ma_kpis['Vol_Abs_i'].sum()
                           if ma_kpis['Vol_Abs_i'].sum() > 0 else 0)
            st.markdown(metric_card(
                t("Market Avg €/MWh","Media mercado €/MWh"),
                f"{avg_eur_mwh:.3f}", unit=" €/MWh",
                positive=avg_eur_mwh >= 0), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # ── TABS internos ─────────────────────────────────────────────────────
        tab_ranking, tab_scatter, tab_evol, tab_detail = st.tabs([
            t("📊 Ranking","📊 Ranking"),
            t("🎯 Efficiency vs Volume","🎯 Eficiencia vs Volumen"),
            t("📈 Cumulative Evolution","📈 Evolución Acumulada"),
            t("🔍 Individual Analysis","🔍 Análisis Individual"),
        ])

        # ────────────────────────────────────────────────────────
        # TAB 1 — RANKING: Top mejores / peores + cuotas de mercado
        # ────────────────────────────────────────────────────────
        with tab_ranking:
            col_rk1, col_rk2 = st.columns(2)

            # Top 15 mejores — barras horizontales
            with col_rk1:
                section_header("🏆", t("Top 15 – Best Intraday Profit","Top 15 – Mayor Beneficio Intradiario"))
                top15 = best.head(15).copy().sort_values('Total_Profit_i')
                fig_best = go.Figure(go.Bar(
                    x=top15['Total_Profit_i'], y=top15['MA'],
                    orientation='h',
                    marker=dict(
                        color=top15['Total_Profit_i'],
                        colorscale=[[0,"#86efac"],[1,"#15803d"]],
                        showscale=False),
                    text=[f"{v:,.0f} €" for v in top15['Total_Profit_i']],
                    textposition='outside',
                    customdata=np.stack([top15['Profit_per_MWh_i'], top15['Share_i_pct']], axis=-1),
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Profit: %{x:,.0f} €<br>"
                        "€/MWh: %{customdata[0]:.3f}<br>"
                        "Cuota intra: %{customdata[1]:.1f}%<extra></extra>")
                ))
                fig_best.update_layout(**base_layout(
                    xaxis_title="€", height=420,
                    margin=dict(l=10,r=100,t=20,b=10)))
                fig_best.update_xaxes(gridcolor="#e2e8f0")
                fig_best.update_yaxes(gridcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_best, use_container_width=True)

            # Top 15 peores
            with col_rk2:
                section_header("⚠️", t("Top 15 – Worst Intraday Profit","Top 15 – Peor Beneficio Intradiario"))
                bot15 = worst.head(15).copy().sort_values('Total_Profit_i', ascending=False)
                fig_worst = go.Figure(go.Bar(
                    x=bot15['Total_Profit_i'], y=bot15['MA'],
                    orientation='h',
                    marker=dict(
                        color=bot15['Total_Profit_i'],
                        colorscale=[[0,"#b91c1c"],[1,"#fca5a5"]],
                        showscale=False),
                    text=[f"{v:,.0f} €" for v in bot15['Total_Profit_i']],
                    textposition='outside',
                    customdata=np.stack([bot15['Profit_per_MWh_i'], bot15['Share_i_pct']], axis=-1),
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Profit: %{x:,.0f} €<br>"
                        "€/MWh: %{customdata[0]:.3f}<br>"
                        "Cuota intra: %{customdata[1]:.1f}%<extra></extra>")
                ))
                fig_worst.update_layout(**base_layout(
                    xaxis_title="€", height=420,
                    margin=dict(l=10,r=100,t=20,b=10)))
                fig_worst.update_xaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8")
                fig_worst.update_yaxes(gridcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_worst, use_container_width=True)

            st.markdown("---")

            # Cuotas de mercado — pie charts
            section_header("🥧", t("Market Share","Cuotas de Mercado"))
            col_p1, col_p2 = st.columns(2)

            def make_pie(df_sorted, value_col, label, n_top=7):
                top_n = df_sorted.head(n_top)
                otros_val = df_sorted.iloc[n_top:][value_col].sum()
                labels_ = top_n['MA'].tolist() + ([t('Others','Otros')] if otros_val > 0 else [])
                values_ = top_n[value_col].tolist() + ([otros_val] if otros_val > 0 else [])
                fig = go.Figure(go.Pie(
                    labels=labels_, values=values_,
                    hole=0.38,
                    textinfo='label+percent',
                    textfont=dict(size=11),
                    marker=dict(colors=px.colors.qualitative.Set2,
                                line=dict(color='white', width=2)),
                    hovertemplate="<b>%{label}</b><br>%{value:.1f}%<extra></extra>",
                ))
                fig.update_layout(**base_layout(
                    title=dict(text=label, font=dict(size=13, color="#1e293b")),
                    height=360, margin=dict(l=10,r=10,t=50,b=10),
                    showlegend=False))
                return fig

            share_sorted_pbf = ma_kpis.sort_values('Share_pbf_pct', ascending=False)
            share_sorted_i   = ma_kpis.sort_values('Share_i_pct',   ascending=False)

            with col_p1:
                st.plotly_chart(make_pie(share_sorted_pbf, 'Share_pbf_pct',
                    t("Day-Ahead Market Share (PBF Volume)","Cuota Mercado Diario (Volumen PBF)")),
                    use_container_width=True)
            with col_p2:
                st.plotly_chart(make_pie(share_sorted_i, 'Share_i_pct',
                    t("Intraday Market Share (Traded Volume)","Cuota Mercado Intradiario (Volumen Negociado)")),
                    use_container_width=True)

            # Tabla resumen completa
            st.markdown("---")
            section_header("📋", t("Full KPI Table","Tabla Completa de KPIs"))
            df_display = ma_kpis[[
                'MA','Total_Profit_i','Profit_per_MWh_i',
                'Inc_vs_Spot_pct','Profit_i_per_p48',
                'Share_i_pct','Share_pbf_pct','Vol_Abs_i','Total_Energy_p48'
            ]].copy().sort_values('Total_Profit_i', ascending=False)
            df_display.columns = [
                t('Retailer','Comercializadora'),
                t('Intraday Profit (€)','Beneficio Intradiario (€)'),
                t('€/MWh (intra vol)','€/MWh (vol intra)'),
                t('Over-spot Revenue (%)','Sobre-ingreso vs Spot (%)'),
                t('€/MWh (vs P48)','€/MWh (vs P48)'),
                t('Intraday Share (%)','Cuota Intradiario (%)'),
                t('Day-Ahead Share (%)','Cuota Diario (%)'),
                t('Intraday Volume (MWh)','Volumen Intradiario (MWh)'),
                t('P48 Volume (MWh)','Volumen P48 (MWh)'),
            ]
            profit_col  = t('Intraday Profit (€)','Beneficio Intradiario (€)')
            vol_col     = t('Intraday Volume (MWh)','Volumen Intradiario (MWh)')
            eur_mwh_col = t('€/MWh (intra vol)','€/MWh (vol intra)')
            st.dataframe(
                df_display.set_index(t('Retailer','Comercializadora')).style
                .format({
                    t('Intraday Profit (€)','Beneficio Intradiario (€)'): '{:,.0f} €',
                    t('€/MWh (intra vol)','€/MWh (vol intra)'): '{:.3f}',
                    t('Over-spot Revenue (%)','Sobre-ingreso vs Spot (%)'): '{:.2f}%',
                    t('€/MWh (vs P48)','€/MWh (vs P48)'): '{:.4f}',
                    t('Intraday Share (%)','Cuota Intradiario (%)'): '{:.2f}%',
                    t('Day-Ahead Share (%)','Cuota Diario (%)'): '{:.2f}%',
                    t('Intraday Volume (MWh)','Volumen Intradiario (MWh)'): '{:,.0f}',
                    t('P48 Volume (MWh)','Volumen P48 (MWh)'): '{:,.0f}',
                })
                .background_gradient(subset=[profit_col], cmap='RdYlGn')
                .background_gradient(subset=[eur_mwh_col], cmap='RdYlGn'),
                use_container_width=True
            )

        # ────────────────────────────────────────────────────────
        # TAB 2 — SCATTER: Eficiencia (€/MWh) vs Cuota de mercado
        # ────────────────────────────────────────────────────────
        with tab_scatter:
            section_header("🎯", t(
                "Efficiency vs Market Share – where each retailer stands",
                "Eficiencia vs Cuota de Mercado – dónde se posiciona cada comercializadora"))
            st.caption(t(
                "Bubble size = absolute intraday profit. X axis = intraday market share. Y axis = €/MWh efficiency. "
                "Top-right quadrant: high share + high efficiency (best). "
                "Bottom-right: high share but low efficiency (large but inefficient).",
                "Tamaño burbuja = profit intradiario absoluto. Eje X = cuota de mercado intradiario. "
                "Eje Y = eficiencia €/MWh. Cuadrante superior-derecho: alta cuota + alta eficiencia (mejores). "
                "Inferior-derecho: alta cuota pero baja eficiencia (grandes pero poco eficientes)."))

            sc_data = ma_kpis.copy()
            sc_data['abs_profit'] = sc_data['Total_Profit_i'].abs().clip(lower=1)
            sc_data['profit_positive'] = sc_data['Total_Profit_i'] >= 0

            # Top 5 mejores y top 5 peores (por profit) recibirán etiqueta
            top5_label = set(sc_data.nlargest(5, 'Total_Profit_i')['MA'].tolist())
            bot5_label = set(sc_data.nsmallest(5, 'Total_Profit_i')['MA'].tolist())
            labeled_mas = top5_label | bot5_label
            sc_data['show_label'] = sc_data['MA'].isin(labeled_mas)

            abs_max = sc_data['abs_profit'].max()

            fig_sc = go.Figure()

            for positive, color, name_ in [
                (True,  C_POS, t("Profit > 0","Beneficio > 0")),
                (False, C_NEG, t("Profit < 0","Pérdida")),
            ]:
                for labeled in [False, True]:
                    sub = sc_data[(sc_data['profit_positive'] == positive) & (sc_data['show_label'] == labeled)]
                    if sub.empty: continue
                    fig_sc.add_trace(go.Scatter(
                        x=sub['Share_i_pct'],
                        y=sub['Profit_per_MWh_i'],
                        mode='markers+text' if labeled else 'markers',
                        marker=dict(
                            size=np.sqrt(sub['abs_profit']) / np.sqrt(abs_max) * 45 + 8,
                            color=color,
                            opacity=0.85 if labeled else 0.55,
                            line=dict(color='white', width=1.5 if labeled else 0.8)),
                        text=sub['MA'] if labeled else None,
                        textposition='top center',
                        textfont=dict(size=9, color="#1e293b", family="Inter"),
                        name=name_,
                        showlegend=(not labeled),   # una sola entrada por color en la leyenda
                        legendgroup=name_,
                        customdata=np.stack([
                            sub['Total_Profit_i'],
                            sub['Inc_vs_Spot_pct'],
                            sub['Vol_Abs_i'],
                            sub['MA'],
                        ], axis=-1),
                        hovertemplate=(
                            "<b>%{customdata[3]}</b><br>"
                            "Cuota intra: %{x:.2f}%<br>"
                            "€/MWh: %{y:.3f}<br>"
                            "Profit: %{customdata[0]:,.0f} €<br>"
                            "Sobre-ingreso vs spot: %{customdata[1]:.2f}%<br>"
                            "Volumen: %{customdata[2]:,.0f} MWh<extra></extra>")
                    ))

            # Líneas de referencia
            fig_sc.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1.5)
            avg_share = sc_data['Share_i_pct'].mean()
            fig_sc.add_vline(x=avg_share, line_dash="dot", line_color="#94a3b8", line_width=1.5,
                             annotation_text=t("Avg share","Cuota media"),
                             annotation_position="top right",
                             annotation_font=dict(size=10, color="#94a3b8"))

            fig_sc.update_layout(**base_layout(
                xaxis_title=t("Intraday Market Share (%)","Cuota de Mercado Intradiario (%)"),
                yaxis_title=t("Intraday Profit per MWh (€/MWh)","Beneficio Intradiario por MWh (€/MWh)"),
                height=520,
                showlegend=True,
                margin=dict(l=10,r=10,t=20,b=10),
            ))
            fig_sc.update_xaxes(gridcolor="#e2e8f0")
            fig_sc.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8")
            st.plotly_chart(fig_sc, use_container_width=True)

        # ────────────────────────────────────────────────────────
        # TAB 3 — EVOLUCIÓN ACUMULADA Top 5 mejores y peores
        # ────────────────────────────────────────────────────────
        with tab_evol:
            section_header("📈", t("Cumulative Intraday Profit Evolution","Evolución del Beneficio Intradiario Acumulado"))

            top5_mas   = best.head(5)['MA'].astype(str).tolist()
            bot5_mas   = worst.head(5)['MA'].astype(str).tolist()

            sp['MA_str'] = sp['MA'].astype(str)

            def build_cum(df_, ma_list):
                df_f = df_[df_['MA_str'].isin(ma_list)].copy()
                evo = df_f.groupby(['Day','MA_str'], observed=True)['Profit_i'].sum().reset_index()
                evo = evo.sort_values('Day')
                evo['Cum_Profit'] = evo.groupby('MA_str')['Profit_i'].cumsum()
                evo['Cum_Profit_k'] = evo['Cum_Profit'] / 1000
                return evo

            evo_best = build_cum(sp, top5_mas)
            evo_worst = build_cum(sp, bot5_mas)

            col_ev1, col_ev2 = st.columns(2)

            def make_cum_line(evo_df, title, color_seq):
                fig = px.line(
                    evo_df, x='Day', y='Cum_Profit_k', color='MA_str',
                    markers=False,
                    color_discrete_sequence=color_seq,
                    labels={'Cum_Profit_k': 'k€', 'Day': '', 'MA_str': 'MA'},
                )
                fig.update_traces(line=dict(width=2.5))
                for trace in fig.data:
                    ma_name = trace.name
                    last = evo_df[evo_df['MA_str'] == ma_name].iloc[-1]
                    fig.add_annotation(
                        x=last['Day'], y=last['Cum_Profit_k'],
                        text=f"  {ma_name}",
                        showarrow=False, xanchor='left',
                        font=dict(size=10, color=trace.line.color))
                fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1)
                fig.update_layout(**base_layout(
                    title=dict(text=title, font=dict(size=13, color="#1e293b")),
                    yaxis_title=t("Accumulated Profit (k€)","Beneficio Acumulado (k€)"),
                    height=400, showlegend=False,
                    margin=dict(l=10,r=120,t=45,b=10),
                    hovermode='x unified',
                ))
                fig.update_xaxes(gridcolor="#e2e8f0")
                fig.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8")
                return fig

            with col_ev1:
                st.plotly_chart(make_cum_line(
                    evo_best,
                    t("Top 5 Best – Accumulated Profit","Top 5 Mejores – Profit Acumulado"),
                    px.colors.qualitative.Set2), use_container_width=True)
            with col_ev2:
                st.plotly_chart(make_cum_line(
                    evo_worst,
                    t("Top 5 Worst – Accumulated Loss","Top 5 Peores – Pérdida Acumulada"),
                    px.colors.qualitative.Set1), use_container_width=True)

            # Evolución del beneficio DIARIO (no acumulado) del mejor MA
            st.markdown("---")
            section_header("📅", t("Daily Profit – Best Retailer","Beneficio Diario – Mejor Comercializadora"))
            if top5_mas:
                best_ma_str = top5_mas[0]
                evo_daily_best = sp[sp['MA_str'] == best_ma_str].groupby('Day', observed=True).agg(
                    Daily_Profit=('Profit_i','sum'),
                    Daily_Energy=('Energy_p48','sum')
                ).reset_index()
                evo_daily_best['EurMWh'] = np.where(
                    evo_daily_best['Daily_Energy'].abs() > 0,
                    evo_daily_best['Daily_Profit'] / evo_daily_best['Daily_Energy'].abs(), 0)

                fig_daily = make_subplots(specs=[[{"secondary_y": True}]])
                fig_daily.add_trace(go.Bar(
                    x=evo_daily_best['Day'], y=evo_daily_best['Daily_Profit'],
                    name=t("Daily Profit (€)","Beneficio Diario (€)"),
                    marker_color=[C_POS if v >= 0 else C_NEG for v in evo_daily_best['Daily_Profit']],
                    hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.0f} €<extra></extra>"
                ), secondary_y=False)
                fig_daily.add_trace(go.Scatter(
                    x=evo_daily_best['Day'], y=evo_daily_best['EurMWh'],
                    name="€/MWh",
                    mode='lines', line=dict(color=C_ACCENT, width=2),
                    hovertemplate="%{x|%d/%m/%Y}<br>%{y:.4f} €/MWh<extra></extra>"
                ), secondary_y=True)
                fig_daily.update_layout(**base_layout(
                    title=dict(text=f"<b>{best_ma_str}</b> · {t('Daily Intraday Performance','Desempeño Intradiario Diario')}",
                               font=dict(size=13, color="#1e293b")),
                    height=380, hovermode='x unified',
                    margin=dict(l=10,r=10,t=45,b=10),
                    legend=dict(orientation='h', yanchor='bottom', y=1.01, xanchor='right', x=1)
                ))
                fig_daily.update_yaxes(title_text=t("Daily Profit (€)","Beneficio Diario (€)"),
                                       gridcolor="#e2e8f0", secondary_y=False)
                fig_daily.update_yaxes(title_text="€/MWh", secondary_y=True,
                                       gridcolor="rgba(0,0,0,0)")
                fig_daily.update_xaxes(gridcolor="#e2e8f0")
                st.plotly_chart(fig_daily, use_container_width=True)

        # ────────────────────────────────────────────────────────
        # TAB 4 — ANÁLISIS INDIVIDUAL por MA
        # ────────────────────────────────────────────────────────
        with tab_detail:
            section_header("🔍", t("Individual Retailer Analysis","Análisis Individual por Comercializadora"))

            all_mas_supply = sorted(sp['MA_str'].unique().tolist())
            default_sel = [m for m in ['IBERDROLA','GESTERNOVA','ENDESA','NATURGY'] if m in all_mas_supply]
            if not default_sel and all_mas_supply:
                default_sel = all_mas_supply[:3]

            sel_mas_ind = st.multiselect(
                t("Select retailers to compare:","Selecciona comercializadoras a comparar:"),
                options=all_mas_supply,
                default=default_sel,
                max_selections=8
            )

            if not sel_mas_ind:
                st.info(t("Select at least one retailer.","Selecciona al menos una comercializadora."))
            else:
                df_ind = sp[sp['MA_str'].isin(sel_mas_ind)].copy()

                # Evolución diaria en € y €/MWh
                evo_ind = df_ind.groupby(['Day','MA_str'], observed=True).agg(
                    Daily_Profit=('Profit_i','sum'),
                    Daily_Energy=('Energy_p48','sum')
                ).reset_index()
                evo_ind['EurMWh_diario'] = np.where(
                    evo_ind['Daily_Energy'].abs() > 0,
                    evo_ind['Daily_Profit'] / evo_ind['Daily_Energy'].abs(), 0)

                col_i1, col_i2 = st.columns(2)
                color_seq_ind = px.colors.qualitative.Set2

                with col_i1:
                    fig_i1 = px.line(
                        evo_ind, x='Day', y='Daily_Profit', color='MA_str',
                        markers=True, color_discrete_sequence=color_seq_ind,
                        labels={'Daily_Profit': t('Daily Profit (€)','Beneficio Diario (€)'),
                                'Day':'', 'MA_str':'MA'},
                        title=t("Daily Intraday Profit (€)","Beneficio Intradiario Diario (€)")
                    )
                    fig_i1.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
                    fig_i1.update_traces(line=dict(width=2), marker=dict(size=4))
                    fig_i1.update_layout(**base_layout(height=370, hovermode='x unified',
                        margin=dict(l=10,r=10,t=45,b=10)))
                    fig_i1.update_xaxes(gridcolor="#e2e8f0")
                    fig_i1.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8",
                        title_text=t("Daily Profit (€)","Beneficio Diario (€)"))
                    st.plotly_chart(fig_i1, use_container_width=True)

                with col_i2:
                    fig_i2 = px.line(
                        evo_ind, x='Day', y='EurMWh_diario', color='MA_str',
                        markers=True, color_discrete_sequence=color_seq_ind,
                        labels={'EurMWh_diario':'€/MWh', 'Day':'', 'MA_str':'MA'},
                        title=t("Daily Intraday Efficiency (€/MWh vs P48)","Eficiencia Intradiaria Diaria (€/MWh vs P48)")
                    )
                    fig_i2.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
                    fig_i2.update_traces(line=dict(width=2), marker=dict(size=4))
                    fig_i2.update_layout(**base_layout(height=370, hovermode='x unified',
                        margin=dict(l=10,r=10,t=45,b=10)))
                    fig_i2.update_xaxes(gridcolor="#e2e8f0")
                    fig_i2.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8",
                        title_text="€/MWh")
                    st.plotly_chart(fig_i2, use_container_width=True)

                # Mini-tabla KPI de los seleccionados
                st.markdown("---")
                kpi_sel = ma_kpis[ma_kpis['MA'].isin(sel_mas_ind)][[
                    'MA','Total_Profit_i','Profit_per_MWh_i',
                    'Inc_vs_Spot_pct','Profit_i_per_p48','Share_i_pct'
                ]].copy().set_index('MA')
                kpi_sel.columns = [
                    t('Intraday Profit (€)','Beneficio Intradiario (€)'),
                    t('€/MWh (intra)','€/MWh (intra)'),
                    t('Over-spot (%)','Sobre-ingreso (%)'),
                    t('€/MWh vs P48','€/MWh vs P48'),
                    t('Intraday Share (%)','Cuota Intradiario (%)'),
                ]
                p_col = t('Intraday Profit (€)','Beneficio Intradiario (€)')
                st.dataframe(
                    kpi_sel.style
                    .format({
                        t('Intraday Profit (€)','Beneficio Intradiario (€)'): '{:,.0f} €',
                        t('€/MWh (intra)','€/MWh (intra)'): '{:.4f}',
                        t('Over-spot (%)','Sobre-ingreso (%)'): '{:.2f}%',
                        t('€/MWh vs P48','€/MWh vs P48'): '{:.4f}',
                        t('Intraday Share (%)','Cuota Intradiario (%)'): '{:.2f}%',
                    })
                    .background_gradient(subset=[p_col], cmap='RdYlGn'),
                    use_container_width=True
                )

    except Exception as e:
        import traceback
        st.error(f"Error Supply: {e}\n\n{traceback.format_exc()}")
    gc.collect()

# ==============================================================================
# SECCIÓN 8: MRA PORTFOLIO
# ==============================================================================
elif seleccion_menu == name_portfolio:
    section_header("🗂️", t("MRA Portfolio – Current MW by Technology",
                             "Portfolio MRA – MW Actuales por Tecnología"))
    try:
        # ── TECHS EXCLUIDAS ───────────────────────────────────────────────────
        EXCLUDED_TECHS = {
            'Supply', 'Consumo de Servicios Auxiliares', 'Consumos directos en mercado',
            'Unidad instrumental internacional', 'Importacion Francia', 'Porfolio',
            '#N/A', 'Saldo acoplamiento mercado', 'Importacion Marruecos',
            'Exportacion Francia', 'Exportacion Marruecos', 'Exportacion Andorra',
            'Enlace Baleares', 'Genericas',
        }

        # ── FUNCIONES DE CARGA ────────────────────────────────────────────────
        @st.cache_data
        def load_mra_snapshot(path_or_bytes, label=""):
            """Lee el export de UPs activas (snapshot mensual de REE/OMIE)."""
            xl = pd.ExcelFile(path_or_bytes)
            sheet = ('export_unidades-de-programacion'
                     if 'export_unidades-de-programacion' in xl.sheet_names
                     else xl.sheet_names[0])
            raw = pd.read_excel(path_or_bytes, sheet_name=sheet, header=None)
            # Detectar fila de cabecera: la que contenga 'UP'
            header_row = 0
            for i, row in raw.iterrows():
                if 'UP' in row.values:
                    header_row = i
                    break
            df = pd.read_excel(path_or_bytes, sheet_name=sheet, header=header_row)
            df.columns = df.columns.astype(str).str.strip()
            # Renombrar columnas clave
            # MA = "Sujeto del Mercado" (nombre completo, no el código abreviado)
            col_map = {
                'UP':                    'UP',
                'Power MW':              'Power MW',
                'Tech':                  'Tech',
                'Sujeto del Mercado':    'MA',       # ← nombre completo
                'Sujeto del Mercado 2':  'MA_Code',  # código corto (GNRA, etc.)
                'Technologia':           'Technologia',
                'Buy-Sell':              'Buy_Sell',
                'Descrip Long':          'Descrip Long',
                'Regulation Zone':       'Regulation Zone',
                'RZ':                    'RZ',
            }
            df = df.rename(columns={c: col_map[c] for c in df.columns if c in col_map})
            df['Power MW'] = pd.to_numeric(df.get('Power MW', 0), errors='coerce').fillna(0)
            # Asegurar columnas mínimas
            for col in ['MA','MA_Code','Tech','Buy_Sell']:
                if col not in df.columns:
                    df[col] = ''
            df['MA']      = df['MA'].astype(str).str.strip()
            df['MA_Code'] = df['MA_Code'].astype(str).str.strip()
            df['Tech']    = df['Tech'].astype(str).str.strip()
            return df

        @st.cache_data
        def load_evolution(path_or_bytes):
            """Lee el fichero histórico de portfolio por MA y fecha."""
            df = pd.read_excel(path_or_bytes, sheet_name='Sheet1', header=1)
            df.columns = df.columns.astype(str).str.strip()
            df['Day']   = pd.to_numeric(df.get('Day',   1), errors='coerce').fillna(1).astype(int)
            df['Month'] = pd.to_numeric(df.get('Month', 1), errors='coerce').fillna(1).astype(int)
            df['Year']  = pd.to_numeric(df.get('Year',  2024), errors='coerce').fillna(2024).astype(int)
            df['Date']  = pd.to_datetime(dict(year=df['Year'], month=df['Month'], day=df['Day']),
                                         errors='coerce')
            tech_cols = [c for c in ['Biomass + Cogen','CCGT + Coal','Hydro','Hydro Pump',
                                     'Solar Thermal','Solar PV','Wind','Others','TOTAL']
                         if c in df.columns]
            for c in tech_cols:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            df['MRA'] = df['MRA'].astype(str).str.strip()
            return df[['Date','MRA'] + tech_cols].dropna(subset=['Date','MRA'])

        @st.cache_data
        def find_local_snapshot():
            """Busca el fichero ANALISIS MRAexport... más reciente en GCS o en disco."""
            if _USE_GCS:
                matches = sorted(
                    [f for f in list_files('ANALISIS MRAexport_unidades-de-programacion')
                     if f.endswith('.xlsx')],
                    reverse=True
                )
                return matches[0] if matches else None
            else:
                candidates = sorted(
                    glob.glob('ANALISIS MRAexport_unidades-de-programacion*.xlsx'),
                    reverse=True
                )
                return candidates[0] if candidates else None

        # ── PANEL DE CARGA ────────────────────────────────────────────────────
        with st.expander(t("📁 File sources (click to change)",
                           "📁 Fuentes de ficheros (clic para cambiar)"), expanded=False):
            st.markdown(f"""
            <div style="color:#475569;font-size:0.84rem;margin-bottom:0.8rem;">
            {t('Both files are loaded automatically from GCS if configured, or from the repo otherwise. '
               'Upload here only if you want to override.',
               'Ambos ficheros se cargan automáticamente desde GCS si está configurado, o del repo en caso contrario. '
               'Sube aquí solo si quieres usar una versión diferente.')}
            </div>""", unsafe_allow_html=True)
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                st.caption(t("Monthly snapshot (ANALISIS MRAexport…)",
                             "Snapshot mensual (ANALISIS MRAexport…)"))
                uploaded_snap = st.file_uploader(
                    t("Override snapshot","Reemplazar snapshot"),
                    type=['xlsx'], key='portfolio_snap_upload', label_visibility='collapsed')
            with col_u2:
                st.caption(t("Portfolio evolution (Evolution_of_MRA_portfolio.xlsx)",
                             "Evolución portfolio (Evolution_of_MRA_portfolio.xlsx)"))
                uploaded_evo = st.file_uploader(
                    t("Override evolution file","Reemplazar fichero evolución"),
                    type=['xlsx'], key='portfolio_evo_upload', label_visibility='collapsed')

        # ── RESOLUCIÓN DE FUENTES ─────────────────────────────────────────────
        # Snapshot
        df_snap = pd.DataFrame()
        snapshot_label = ""
        if uploaded_snap is not None:
            df_snap = load_mra_snapshot(uploaded_snap, label=uploaded_snap.name)
            snapshot_label = uploaded_snap.name
        else:
            snap_name = find_local_snapshot()
            if snap_name:
                if _USE_GCS:
                    raw_bytes = load_excel(snap_name, sheet_name=None)  # cargar como bytes via GCS
                    # Necesitamos BytesIO — usamos gcsfs directamente
                    import io as _io
                    from gcs_loader import _get_fs, _path
                    _fs = _get_fs()
                    with _fs.open(_path(snap_name), "rb") as _f:
                        _buf = _io.BytesIO(_f.read())
                    df_snap = load_mra_snapshot(_buf, label=snap_name)
                else:
                    df_snap = load_mra_snapshot(snap_name, label=snap_name)
                snapshot_label = snap_name

        # Evolution
        df_evo = pd.DataFrame()
        evo_label = ""
        evo_filename = 'Evolution_of_MRA_portfolio.xlsx'

        def _process_evo(df_raw):
            """Normaliza el DataFrame de evolución independientemente del origen."""
            if df_raw.empty: return df_raw
            df_raw.columns = df_raw.columns.astype(str).str.strip()
            for _col, _def in [('Day',1),('Month',1),('Year',2024)]:
                df_raw[_col] = pd.to_numeric(df_raw.get(_col, _def), errors='coerce').fillna(_def).astype(int)
            df_raw['Date'] = pd.to_datetime(
                dict(year=df_raw['Year'], month=df_raw['Month'], day=df_raw['Day']), errors='coerce')
            _tc = [c for c in ['Biomass + Cogen','CCGT + Coal','Hydro','Hydro Pump',
                                'Solar Thermal','Solar PV','Wind','Others','TOTAL']
                   if c in df_raw.columns]
            for _c in _tc: df_raw[_c] = pd.to_numeric(df_raw[_c], errors='coerce').fillna(0)
            df_raw['MRA'] = df_raw['MRA'].astype(str).str.strip()
            return df_raw[['Date','MRA'] + _tc].dropna(subset=['Date','MRA'])

        if uploaded_evo is not None:
            df_evo = _process_evo(pd.read_excel(uploaded_evo, sheet_name='Sheet1', header=1))
            evo_label = uploaded_evo.name
        elif _USE_GCS:
            _raw_evo = load_excel(evo_filename, sheet_name='Sheet1', header=1)
            df_evo = _process_evo(_raw_evo)
            evo_label = evo_filename
        elif os.path.exists(evo_filename):
            df_evo = _process_evo(pd.read_excel(evo_filename, sheet_name='Sheet1', header=1))
            evo_label = evo_filename

        # ── STATUS BAR ────────────────────────────────────────────────────────
        sc1, sc2 = st.columns(2)
        with sc1:
            if not df_snap.empty:
                st.success(f"✅ Snapshot: **{snapshot_label}** — {len(df_snap):,} UPs")
            else:
                st.warning(t("⚠️ No snapshot loaded. Add ANALISIS_MRAexport_unidades-de-programacion*.xlsx to the repo.",
                             "⚠️ Sin snapshot. Añade ANALISIS_MRAexport_unidades-de-programacion*.xlsx al repositorio."))
        with sc2:
            if not df_evo.empty:
                st.success(f"✅ Evolution: **{evo_label}** — {df_evo['MRA'].nunique()} MAs")
            else:
                st.warning(t("⚠️ Evolution_of_MRA_portfolio.xlsx not found in repo.",
                             "⚠️ Evolution_of_MRA_portfolio.xlsx no encontrado en el repositorio."))

        if df_snap.empty and df_evo.empty:
            st.stop()

        # ── TABS ──────────────────────────────────────────────────────────────
        tab_snap, tab_evo, tab_detail = st.tabs([
            t("📸 Current Snapshot","📸 Snapshot Actual"),
            t("📈 Portfolio Evolution","📈 Evolución del Portfolio"),
            t("🔍 MA Detail","🔍 Detalle por MA"),
        ])

        # ── CONSTANTES ────────────────────────────────────────────────────────
        RENEWABLES = ['Solar PV','Wind','Hydro','Biomass','Other renewables','Solar Thermal',
                      'Hydro Pump-Turb','Hydro Pump-Pump']
        TECH_COLORS = {
            'Solar PV':         '#f59e0b',
            'Wind':             '#34d399',
            'Hydro':            '#38bdf8',
            'Biomass':          '#84cc16',
            'CCGT':             '#6366f1',
            'Coal':             '#78716c',
            'Cogeneration':     '#fb923c',
            'Natural gas':      '#a78bfa',
            'Other renewables': '#10b981',
            'Solar Thermal':    '#fde68a',
            'Nuclear':          '#f87171',
            'Hydro Pump-Turb':  '#7dd3fc',
            'Storage':          '#c084fc',
            'Fuel':             '#d97706',
        }

        # ────────────────────────────────────────────────────────────────────
        # TAB 1: SNAPSHOT ACTUAL
        # ────────────────────────────────────────────────────────────────────
        with tab_snap:
            if df_snap.empty:
                st.info(t("No snapshot loaded.","No hay snapshot cargado."))
            else:
                if snapshot_label:
                    st.caption(f"📂 {snapshot_label}")

                # Filtrar generación: excluir techs no deseadas y filas de compra
                df_gen = df_snap[
                    (~df_snap['Tech'].isin(EXCLUDED_TECHS)) &
                    (~df_snap['Tech'].str.upper().isin({'NAN','#N/A',''})) &
                    (df_snap['Buy_Sell'] == 'Venta')
                ].copy()
                df_gen['Power MW'] = pd.to_numeric(df_gen['Power MW'], errors='coerce').fillna(0)
                df_gen = df_gen[df_gen['Power MW'] > 0]

                # Agrupar por MA y tecnología
                ma_tech = df_gen.groupby(['MA','Tech'], observed=True)['Power MW'].sum().reset_index()
                ma_total = ma_tech.groupby('MA', observed=True)['Power MW'].sum().reset_index()
                ma_total.columns = ['MA','Total MW']
                ma_total = ma_total.sort_values('Total MW', ascending=False)

                # Filtros de visualización
                col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
                with col_f1:
                    top_n = st.slider(t("Top N MAs","Top N representantes"), 5, 40, 15)
                with col_f2:
                    hide_incumbents = st.checkbox(
                        t("Exclude incumbents (Iberdrola, Endesa, Naturgy, EDP)",
                          "Excluir incumbentes (Iberdrola, Endesa, Naturgy, EDP)"),
                        value=True
                    )

                INCUMBENTS = {'IBERDROLA','ENDESA','NATURGY','EDP'}

                if hide_incumbents:
                    # Filtrar cualquier MA cuyo nombre contenga alguno de estos strings
                    mask_inc = ma_total['MA'].str.upper().apply(
                        lambda x: any(inc in x for inc in INCUMBENTS)
                    )
                    ma_total_filt = ma_total[~mask_inc]
                    df_gen_filt = df_gen[~df_gen['MA'].str.upper().apply(
                        lambda x: any(inc in x for inc in INCUMBENTS)
                    )]
                else:
                    ma_total_filt = ma_total
                    df_gen_filt = df_gen

                # Top N ordenados de mayor a menor
                top_mas = ma_total_filt.head(top_n)['MA'].tolist()  # ya ordenado desc
                ma_tech_filt = df_gen_filt.groupby(['MA','Tech'], observed=True)['Power MW'].sum().reset_index()
                df_plot = ma_tech_filt[ma_tech_filt['MA'].isin(top_mas)].copy()
                # Orden categórico de mayor a menor total
                df_plot['MA'] = pd.Categorical(df_plot['MA'], categories=top_mas, ordered=True)
                df_plot = df_plot.sort_values('MA')

                # KPI cards (sobre datos filtrados)
                total_mw_market = ma_total_filt['Total MW'].sum()
                top1 = ma_total_filt.iloc[0] if not ma_total_filt.empty else pd.Series({'MA':'—','Total MW':0})
                renewables_total = df_gen_filt[df_gen_filt['Tech'].isin(RENEWABLES)]['Power MW'].sum()
                k1,k2,k3,k4 = st.columns(4)
                with k1: st.markdown(metric_card(
                    t("Total Market (gen)","Total Mercado (gen)"),
                    f"{total_mw_market/1000:,.1f}", unit=" GW"), unsafe_allow_html=True)
                with k2: st.markdown(metric_card(
                    t("Largest Portfolio","Mayor Portfolio"),
                    top1['MA'], delta=f"{top1['Total MW']:,.0f} MW"), unsafe_allow_html=True)
                with k3: st.markdown(metric_card(
                    t("Total Renewables","Total Renovables"),
                    f"{renewables_total/1000:,.1f}", unit=" GW"), unsafe_allow_html=True)
                with k4: st.markdown(metric_card(
                    t("Active MAs","MAs activos"),
                    f"{len(ma_total_filt):,}"), unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)

                # Stacked bar: MW por tecnología para cada MA, ordenado de mayor a menor
                section_header("📊", t("Portfolio by MA (MW by Technology)",
                                        "Portfolio por Representante (MW por Tecnología)"))

                # Ordenar techs por total desc para que la leyenda sea coherente
                tech_totals = df_plot.groupby('Tech', observed=True)['Power MW'].sum().sort_values(ascending=False)
                all_techs_in_data = tech_totals.index.tolist()

                fig_stack = go.Figure()
                for tech in all_techs_in_data:
                    sub = df_plot[df_plot['Tech'] == tech]
                    fig_stack.add_trace(go.Bar(
                        name=tech,
                        x=sub['MA'].astype(str),
                        y=sub['Power MW'],
                        marker_color=TECH_COLORS.get(tech, '#94a3b8'),
                        hovertemplate=f"<b>%{{x}}</b><br>{tech}: %{{y:,.0f}} MW<extra></extra>",
                    ))
                fig_stack.update_layout(**base_layout(
                    barmode='stack',
                    xaxis_title="", yaxis_title="MW",
                    height=480,
                    legend=dict(orientation='h', yanchor='bottom', y=1.01,
                                xanchor='right', x=1, font=dict(size=10)),
                    margin=dict(l=10,r=10,t=60,b=10),
                    hovermode='x unified',
                ))
                fig_stack.update_xaxes(gridcolor="#e2e8f0", tickangle=-35)
                fig_stack.update_yaxes(gridcolor="#e2e8f0")
                st.plotly_chart(fig_stack, use_container_width=True)

                # Treemap: toda la generación, MA > Tech > MW
                st.markdown("---")
                section_header("🌳", t("Market Treemap (MW)", "Treemap del Mercado (MW)"))
                df_tree = df_gen_filt[df_gen_filt['MA'].isin(top_mas)].groupby(
                    ['MA','Tech'], observed=True)['Power MW'].sum().reset_index()
                df_tree = df_tree[df_tree['Power MW'] > 0]
                fig_tree = px.treemap(
                    df_tree, path=[px.Constant(t("Market","Mercado")), 'MA', 'Tech'],
                    values='Power MW',
                    color='Tech',
                    color_discrete_map=TECH_COLORS,
                    hover_data={'Power MW':':.0f'},
                )
                fig_tree.update_traces(
                    texttemplate="<b>%{label}</b><br>%{value:,.0f} MW",
                    hovertemplate="<b>%{label}</b><br>%{value:,.0f} MW<extra></extra>",
                )
                fig_tree.update_layout(**base_layout(height=520, margin=dict(l=5,r=5,t=20,b=5)))
                st.plotly_chart(fig_tree, use_container_width=True)

                # Tabla resumen: MA × tecnología (pivot)
                st.markdown("---")
                section_header("📋", t("Summary Table (MW)","Tabla Resumen (MW)"))
                pivot = ma_tech_filt[ma_tech_filt['MA'].isin(top_mas)].pivot_table(
                    index='MA', columns='Tech', values='Power MW',
                    aggfunc='sum', fill_value=0).round(1)
                pivot['TOTAL'] = pivot.sum(axis=1)
                pivot = pivot.sort_values('TOTAL', ascending=False)
                # Ordenar columnas: tech por total descendente, TOTAL al final
                tech_order = pivot.drop(columns='TOTAL').sum().sort_values(ascending=False).index.tolist()
                pivot = pivot[tech_order + ['TOTAL']]
                st.dataframe(
                    pivot.style
                    .format("{:,.0f}")
                    .background_gradient(subset=['TOTAL'], cmap='Blues')
                    .background_gradient(subset=[c for c in ['Solar PV','Wind'] if c in pivot.columns], cmap='Greens'),
                    use_container_width=True
                )

        # ────────────────────────────────────────────────────────────────────
        # TAB 2: EVOLUCIÓN HISTÓRICA
        # ────────────────────────────────────────────────────────────────────
        with tab_evo:
            if df_evo.empty:
                st.info(t("Evolution file not found (Evolution_of_MRA_portfolio.xlsx).",
                          "Fichero de evolución no encontrado (Evolution_of_MRA_portfolio.xlsx)."))
            else:
                evo_mas = sorted(df_evo['MRA'].dropna().unique().tolist())
                evo_tech_cols = [c for c in ['Solar PV','Wind','Hydro','CCGT + Coal',
                                              'Biomass + Cogen','Hydro Pump','Solar Thermal',
                                              'Others','TOTAL']
                                 if c in df_evo.columns]

                col_ev1, col_ev2 = st.columns([2,1])
                with col_ev1:
                    sel_evo_mas = st.multiselect(
                        t("Select MAs:","Selecciona Representantes:"),
                        options=evo_mas,
                        default=evo_mas[:8],
                        key='evo_mas_sel'
                    )
                with col_ev2:
                    sel_evo_tech = st.selectbox(
                        t("Technology / Metric:","Tecnología / Métrica:"),
                        options=evo_tech_cols,
                        index=evo_tech_cols.index('TOTAL') if 'TOTAL' in evo_tech_cols else 0,
                        key='evo_tech_sel'
                    )

                if sel_evo_mas:
                    df_evo_plot = df_evo[df_evo['MRA'].isin(sel_evo_mas)].sort_values('Date')

                    # Line chart evolución MW
                    section_header("📈", t(f"Portfolio Evolution – {sel_evo_tech} (MW)",
                                            f"Evolución Portfolio – {sel_evo_tech} (MW)"))
                    fig_evo_line = px.line(
                        df_evo_plot, x='Date', y=sel_evo_tech, color='MRA',
                        markers=True,
                        color_discrete_sequence=px.colors.qualitative.Set2,
                        labels={sel_evo_tech: 'MW', 'Date': '', 'MRA': 'MA'},
                    )
                    fig_evo_line.update_traces(line=dict(width=2.5), marker=dict(size=6))
                    fig_evo_line.update_layout(**base_layout(
                        yaxis_title="MW",
                        height=430,
                        hovermode='x unified',
                        legend=dict(orientation='h', yanchor='bottom', y=1.01,
                                    xanchor='right', x=1, font=dict(size=10)),
                        margin=dict(l=10,r=10,t=60,b=10),
                    ))
                    fig_evo_line.update_xaxes(gridcolor="#e2e8f0")
                    fig_evo_line.update_yaxes(gridcolor="#e2e8f0")
                    st.plotly_chart(fig_evo_line, use_container_width=True)

                    # Heatmap: MA × fecha para la tech seleccionada
                    st.markdown("---")
                    section_header("🌡️", t("Heatmap – MW over time","Heatmap – MW a lo largo del tiempo"))
                    df_hm_evo = df_evo_plot.pivot_table(
                        index='MRA', columns='Date', values=sel_evo_tech, aggfunc='mean')
                    df_hm_evo.columns = [d.strftime('%b %Y') for d in df_hm_evo.columns]

                    z_evo = df_hm_evo.values
                    fig_hm_evo = go.Figure(go.Heatmap(
                        z=z_evo,
                        x=df_hm_evo.columns.tolist(),
                        y=df_hm_evo.index.tolist(),
                        colorscale=[[0,'#dbeafe'],[0.5,'#3b82f6'],[1,'#1e3a8a']],
                        hovertemplate="<b>%{y}</b> · %{x}<br>%{z:,.0f} MW<extra></extra>",
                        colorbar=dict(title=dict(text="MW", font=dict(color="#475569", size=11)),
                                      tickfont=dict(color="#475569"), thickness=12, outlinewidth=0),
                    ))
                    fig_hm_evo.update_layout(
                        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                        font=dict(family="Inter", color="#475569"),
                        title_font=dict(family="Inter", color="#1e293b", size=13),
                        margin=dict(l=10,r=60,t=20,b=40),
                        height=max(280, len(sel_evo_mas)*48 + 80),
                        xaxis=dict(tickangle=-35, tickfont=dict(size=10), gridcolor="rgba(0,0,0,0)"),
                        yaxis=dict(tickfont=dict(size=11), gridcolor="rgba(0,0,0,0)"),
                    )
                    st.plotly_chart(fig_hm_evo, use_container_width=True)

                    # Tabla última fecha disponible
                    st.markdown("---")
                    section_header("📋", t("Last snapshot in evolution file","Último snapshot en fichero de evolución"))
                    last_date = df_evo['Date'].max()
                    df_last = df_evo[df_evo['Date'] == last_date][['MRA'] + evo_tech_cols].set_index('MRA')
                    st.caption(f"📅 {last_date.strftime('%d %b %Y')}")
                    st.dataframe(
                        df_last.style.format("{:,.0f}")
                        .background_gradient(subset=['TOTAL'] if 'TOTAL' in df_last.columns else [], cmap='Blues'),
                        use_container_width=True
                    )

        # ────────────────────────────────────────────────────────────────────
        # TAB 3: DETALLE POR MA
        # ────────────────────────────────────────────────────────────────────
        with tab_detail:
            if df_snap.empty:
                st.info(t("Load a snapshot to see MA detail.","Carga un snapshot para ver el detalle por MA."))
            else:
                all_mas_snap = sorted(df_snap['MA'].dropna().astype(str).unique().tolist())
                # Default: GNERA or similar full name
                default_ma = next((m for m in all_mas_snap if 'GNERA' in m.upper() or 'GESTERNOVA' in m.upper()), all_mas_snap[0])
                sel_ma_detail = st.selectbox(
                    t("Select Market Agent:","Selecciona Representante:"),
                    options=all_mas_snap,
                    index=all_mas_snap.index(default_ma),
                    key='portfolio_ma_detail'
                )

                df_ma = df_snap[df_snap['MA'].astype(str) == sel_ma_detail].copy()
                df_ma_gen = df_ma[
                    (df_ma['Buy_Sell'] == 'Venta') &
                    (~df_ma['Tech'].isin(EXCLUDED_TECHS)) &
                    (~df_ma['Tech'].str.upper().isin({'NAN','#N/A',''}))
                ].copy()
                df_ma_gen['Power MW'] = pd.to_numeric(df_ma_gen['Power MW'], errors='coerce').fillna(0)
                df_ma_gen = df_ma_gen[df_ma_gen['Power MW'] > 0]

                total_mw_ma = df_ma_gen['Power MW'].sum()
                n_ups = len(df_ma_gen)
                tech_breakdown = df_ma_gen.groupby('Tech', observed=True)['Power MW'].sum().sort_values(ascending=False)

                # KPIs
                k1, k2, k3 = st.columns(3)
                with k1: st.markdown(metric_card(
                    t("Total Portfolio (gen)","Portfolio Total (gen)"),
                    f"{total_mw_ma:,.0f}", unit=" MW"), unsafe_allow_html=True)
                with k2: st.markdown(metric_card(
                    t("Active UPs","UPs Activas"), f"{n_ups:,}"), unsafe_allow_html=True)
                dom_tech = tech_breakdown.index[0] if not tech_breakdown.empty else '—'
                dom_mw   = tech_breakdown.iloc[0]  if not tech_breakdown.empty else 0
                with k3: st.markdown(metric_card(
                    t("Dominant Technology","Tecnología Dominante"),
                    dom_tech, delta=f"{dom_mw:,.0f} MW"), unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)

                col_d1, col_d2 = st.columns([1, 1.6])

                # Donut tecnología
                with col_d1:
                    section_header("🥧", t("MW by Technology","MW por Tecnología"))
                    tech_pie = tech_breakdown[tech_breakdown > 0].reset_index()
                    fig_pie = go.Figure(go.Pie(
                        labels=tech_pie['Tech'],
                        values=tech_pie['Power MW'],
                        hole=0.4,
                        textinfo='label+percent',
                        textfont=dict(size=11),
                        marker=dict(
                            colors=[TECH_COLORS.get(tc,'#94a3b8') for tc in tech_pie['Tech']],
                            line=dict(color='white', width=2)),
                        hovertemplate="<b>%{label}</b><br>%{value:,.0f} MW (%{percent})<extra></extra>",
                    ))
                    fig_pie.update_layout(**base_layout(
                        height=360, showlegend=False,
                        margin=dict(l=10,r=10,t=20,b=10),
                        annotations=[dict(text=f"<b>{total_mw_ma:,.0f}</b><br>MW",
                                          x=0.5, y=0.5, font_size=14, showarrow=False,
                                          font=dict(color="#1e293b"))]
                    ))
                    st.plotly_chart(fig_pie, use_container_width=True)

                # Lista de UPs con barras
                with col_d2:
                    section_header("⚙️", t("UPs Detail","Detalle de UPs"))
                    df_ma_gen_disp = df_ma_gen[['UP','Power MW','Tech','Technologia']].copy()
                    df_ma_gen_disp = df_ma_gen_disp[df_ma_gen_disp['Power MW'] > 0].sort_values('Power MW', ascending=False)
                    fig_ups = px.bar(
                        df_ma_gen_disp.head(30), x='Power MW', y='UP',
                        orientation='h',
                        color='Tech',
                        color_discrete_map=TECH_COLORS,
                        labels={'Power MW':'MW', 'UP':'', 'Tech':'Tech'},
                        hover_data={'Power MW':':.1f', 'Tech':True, 'Technologia':True},
                    )
                    fig_ups.update_layout(**base_layout(
                        height=max(360, len(df_ma_gen_disp.head(30))*28 + 80),
                        xaxis_title="MW", yaxis_title="",
                        showlegend=True,
                        legend=dict(orientation='h', yanchor='bottom', y=1.01,
                                    xanchor='right', x=1, font=dict(size=9)),
                        margin=dict(l=10,r=10,t=50,b=10),
                    ))
                    fig_ups.update_xaxes(gridcolor="#e2e8f0")
                    fig_ups.update_yaxes(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=9))
                    st.plotly_chart(fig_ups, use_container_width=True)

                # Tabla completa de UPs del MA seleccionado
                st.markdown("---")
                section_header("📋", t("Full UP List","Lista Completa de UPs"))
                cols_show = [c for c in ['UP','Descrip Long','Power MW','Tech','Technologia',
                                          'Regulation Zone','RZ'] if c in df_ma_gen.columns]
                st.dataframe(
                    df_ma_gen[cols_show].sort_values('Power MW', ascending=False)
                    .reset_index(drop=True)
                    .style.format({'Power MW':'{:,.1f} MW'})
                    .background_gradient(subset=['Power MW'], cmap='Blues'),
                    use_container_width=True, height=400
                )

                # Comparativa con evolución (si existe)
                # Buscar el código corto (MA_Code) del MA seleccionado para cruzar con evolución
                ma_code_match = df_snap.loc[df_snap['MA'] == sel_ma_detail, 'MA_Code'].dropna()
                evo_ma_key = ma_code_match.iloc[0] if not ma_code_match.empty else sel_ma_detail
                evo_match = df_evo[df_evo['MRA'].str.upper() == evo_ma_key.upper()]
                if not df_evo.empty and not evo_match.empty:
                    st.markdown("---")
                    section_header("📈", t("Historical Evolution of this MA",
                                            "Evolución Histórica de este Representante"))
                    df_evo_ma = evo_match.sort_values('Date')
                    evo_plot_cols = [c for c in ['Solar PV','Wind','Hydro','CCGT + Coal',
                                                  'Biomass + Cogen','TOTAL'] if c in df_evo_ma.columns]
                    df_evo_ma_melt = df_evo_ma[['Date'] + evo_plot_cols].melt(
                        id_vars='Date', var_name='Tech', value_name='MW')
                    df_evo_ma_melt = df_evo_ma_melt[df_evo_ma_melt['Tech'] != 'TOTAL']

                    fig_evo_ma = px.area(
                        df_evo_ma_melt, x='Date', y='MW', color='Tech',
                        color_discrete_sequence=px.colors.qualitative.Set2,
                        labels={'MW':'MW', 'Date':'', 'Tech':''},
                    )
                    fig_evo_ma.update_layout(**base_layout(
                        height=380, hovermode='x unified',
                        legend=dict(orientation='h', yanchor='bottom', y=1.01,
                                    xanchor='right', x=1, font=dict(size=10)),
                        margin=dict(l=10,r=10,t=60,b=10),
                    ))
                    fig_evo_ma.update_xaxes(gridcolor="#e2e8f0")
                    fig_evo_ma.update_yaxes(gridcolor="#e2e8f0", title_text="MW")
                    st.plotly_chart(fig_evo_ma, use_container_width=True)

    except Exception as e:
        import traceback
        st.error(f"Error Portfolio: {e}\n\n{traceback.format_exc()}")
    gc.collect()
