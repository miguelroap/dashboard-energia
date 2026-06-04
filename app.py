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
    try:
        _correct = st.secrets["app_password"]
    except Exception:
        return True

    MAX_INTENTOS  = 5
    BLOQUEO_SEG   = 300

    if "pw_intentos"  not in st.session_state: st.session_state["pw_intentos"]  = 0
    if "pw_bloqueado" not in st.session_state: st.session_state["pw_bloqueado"] = 0.0
    if "pw_ok"        not in st.session_state: st.session_state["pw_ok"]        = False

    if st.session_state["pw_ok"]: return True

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

        if st.session_state["pw_intentos"] >= MAX_INTENTOS and tiempo_restante <= 0:
            st.session_state["pw_intentos"]  = 0
            st.session_state["pw_bloqueado"] = 0.0

        def _on_submit():
            pwd_input = st.session_state.get("pw_input", "")
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
            t("Password","Contraseña"), type="password", key="pw_input",
            on_change=_on_submit, placeholder=t("Enter password…","Introduce la contraseña…"),
            label_visibility="collapsed"
        )

        if st.session_state["pw_intentos"] > 0 and not st.session_state["pw_ok"]:
            restantes = MAX_INTENTOS - st.session_state["pw_intentos"]
            if restantes > 0:
                st.warning(t(
                    f"😕 Incorrect password. {restantes} attempt(s) remaining.",
                    f"😕 Contraseña incorrecta. Te quedan {restantes} intento(s)."
                ))

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
def load_power_data(start_date, end_date):
    """Carga archivos mensuales ups_dashboard_YYYY-MM.parquet según el periodo seleccionado."""
    months = pd.period_range(start_date, end_date, freq='M').strftime('%Y-%m').tolist()
    dfs = []
    for m in months:
        filename = f'ups_dashboard_{m}.parquet'
        try:
            if _USE_GCS: df = load_parquet(filename)
            elif os.path.exists(filename): df = pd.read_parquet(filename)
            else: df = pd.DataFrame()
            
            if not df.empty:
                df['Month'] = pd.Period(m, freq='M')
                dfs.append(df)
        except:
            pass
            
    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
        if 'Power MW' not in combined.columns: combined['Power MW'] = np.nan
        if 'RZ' not in combined.columns: combined['RZ'] = 'Unknown'
        if 'FechaInicio_RZ' not in combined.columns: combined['FechaInicio_RZ'] = ''
        combined['Power MW'] = pd.to_numeric(combined['Power MW'], errors='coerce')
        return combined[['UP', 'Month', 'Power MW', 'RZ', 'FechaInicio_RZ']]
    else:
        # Fallback al archivo antiguo ups_dashboard.parquet
        try:
            if _USE_GCS: df = load_parquet('ups_dashboard.parquet')
            elif os.path.exists('ups_dashboard.parquet'): df = pd.read_parquet('ups_dashboard.parquet')
            else: return pd.DataFrame(columns=['UP', 'Month', 'Power MW', 'RZ', 'FechaInicio_RZ'])
            
            df['Power MW'] = pd.to_numeric(df.get('Power MW', np.nan), errors='coerce')
            if 'RZ' not in df.columns: df['RZ'] = 'Unknown'
            if 'FechaInicio_RZ' not in df.columns: df['FechaInicio_RZ'] = ''
            
            df_list = []
            for m in months:
                temp = df.copy()
                temp['Month'] = pd.Period(m, freq='M')
                df_list.append(temp)
            if not df_list: return pd.DataFrame(columns=['UP', 'Month', 'Power MW', 'RZ', 'FechaInicio_RZ'])
            return pd.concat(df_list, ignore_index=True)[['UP', 'Month', 'Power MW', 'RZ', 'FechaInicio_RZ']]
        except:
            return pd.DataFrame(columns=['UP', 'Month', 'Power MW', 'RZ', 'FechaInicio_RZ'])

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

# Cargar maestro mensual de potencias y RZ
df_power = load_power_data(start_date, end_date)
# Para cruces donde la fecha no importa (ej: matriz global), nos quedamos con el último dato
df_power_unique = df_power.drop_duplicates(subset=['UP'], keep='last') if not df_power.empty else df_power
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

    col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1.5, 1, 1.5])
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
        group_opt = st.radio(
            t("📊 Group by:", "📊 Agrupar por:"),
            options=['MA', 'RZ'],
            format_func=lambda x: t("Market Agent", "Representante (MA)") if x == 'MA' else t("Regulation Zone", "Zona Regulación (RZ)"),
            horizontal=True
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
    monthly = allh_main.groupby(['UP','Tech','MA','Month'], observed=True).agg(
        Monthly_Profit=('Total_Profit','sum'), Monthly_Energy=('Energy_p48','sum')
    ).reset_index()
    
    # Merge con dataframe mensual que trae la RZ de cada mes
    monthly = pd.merge(monthly, df_power, on=['UP','Month'], how='left')
    monthly['Profit_per_MW'] = (monthly['Monthly_Profit'] / monthly['Power MW']).replace([np.inf,-np.inf], 0).fillna(0)
    
    if 'RZ' not in monthly.columns: monthly['RZ'] = 'Desconocida'
    if 'FechaInicio_RZ' not in monthly.columns: monthly['FechaInicio_RZ'] = ''
    
    grouped = monthly.groupby(['UP','Tech','MA','RZ','FechaInicio_RZ'], observed=True).agg(Profit_per_MW=('Profit_per_MW','mean')).reset_index()
    grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)
    grouped['MA'] = grouped['MA'].astype(str)
    grouped['RZ'] = grouped['RZ'].astype(str).replace('nan','Desconocida')

    def make_boxplot(tech, color_main, color_highlight, group_col):
        data = grouped[grouped['Tech'] == tech].copy()
        if data.empty:
            return None
        order = data.groupby(group_col, observed=True)['Profit_per_MW'].mean().sort_values(ascending=False).index.tolist()
        data[group_col] = pd.Categorical(data[group_col], categories=order, ordered=True)
        data = data.sort_values(group_col)

        normal = data[~data['is_Highlighted']]
        highlighted = data[data['is_Highlighted']]

        fig = go.Figure()
        r, g, b = px.colors.hex_to_rgb(color_main)
        fill_rgba = f"rgba({r},{g},{b},0.15)"
        
        for grp_val in order:
            grp_data = normal[normal[group_col] == grp_val]['Profit_per_MW']
            if grp_data.empty: continue
            fig.add_trace(go.Box(
                y=grp_data, name=str(grp_val), boxpoints=False,
                marker_color=color_main,
                line_color=color_main,
                fillcolor=fill_rgba,
                showlegend=False,
                hovertemplate=f"<b>{grp_val}</b><br>Mediana: %{{median:.1f}} €/MW<br>IQR: %{{q1:.1f}} – %{{q3:.1f}}<extra></extra>"
            ))
            
        if not highlighted.empty:
            custom_data = np.stack((
                highlighted['UP'], 
                highlighted['FechaInicio_RZ']
            ), axis=-1)
            
            ht = "<b>%{x}</b><br>UP: %{customdata[0]}<br>Profit/MW: %{y:.1f} €<extra></extra>"
            if group_col == 'RZ':
                ht = "<b>%{x}</b><br>UP: %{customdata[0]}<br>Profit/MW: %{y:.1f} €<br>Inicio RZ: %{customdata[1]}<extra></extra>"

            fig.add_trace(go.Scatter(
                x=highlighted[group_col].astype(str), y=highlighted['Profit_per_MW'],
                mode='markers',
                marker=dict(color='#f87171', size=10, symbol='diamond', line=dict(color='white', width=1.5)),
                name=t('Highlighted','Resaltadas'),
                hovertemplate=ht,
                customdata=custom_data
            ))

        fig.add_hline(y=0, line_dash="dot", line_color="#4b5563", line_width=1)
        fig.update_layout(**base_layout(
            title=dict(text=f"<b>{tech}</b> · {t('Profit/MW by ' + group_col, 'Profit/MW por ' + group_col)}", font=dict(size=13, color="#1e293b")),
            xaxis_title="",
            yaxis_title=t("Avg Monthly Profit / MW (€)", "Profit Mensual Medio / MW (€)"),
            height=430,
        ))
        fig.update_xaxes(gridcolor="#e2e8f0", tickangle=-35)
        fig.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8")
        return fig

    c1, c2 = st.columns(2)
    with c1:
        fig_solar = make_boxplot('Solar PV', '#f59e0b', '#f87171', group_opt)
        if fig_solar: st.plotly_chart(fig_solar, use_container_width=True)
        else: st.info(t("No Solar PV data.","Sin datos de Solar PV."))
    with c2:
        fig_wind = make_boxplot('Wind', '#34d399', '#f87171', group_opt)
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

    mat_up_sel_solar, mat_up_sel_wind = None, None
    if mat_up_filter:
        st.markdown("")
        def _ups_for_tech(tech):
            df_t = allh_main[allh_main['Tech'] == tech].copy()
            if mat_qualified:
                mask_q = (df_t['Profit_rt'] != 0) | (df_t['Profit_b'] != 0) | (df_t['Profit_t'] != 0)
                df_t = df_t[df_t['UP'].isin(df_t.loc[mask_q, 'UP'].unique())]
            ups_all = sorted(df_t['UP'].astype(str).unique().tolist())
            ups_from_ma = sorted(
                df_t[df_t['MA'].astype(str).isin(mat_ma_quick)]['UP'].astype(str).unique().tolist()
            ) if mat_ma_quick else []
            return ups_all, ups_from_ma

        fu1, fu2 = st.columns(2)
        with fu1:
            ups_solar_all, ups_solar_ma = _ups_for_tech('Solar PV')
            solar_options = ups_solar_ma if mat_ma_quick else ups_solar_all
            mat_up_sel_solar = st.multiselect(
                t("☀️ Solar PV – UPs
