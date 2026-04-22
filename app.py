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
def check_password():
    try:
        app_pass = st.secrets["app_password"]
    except Exception:
        return True
    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.markdown(f"<h1 style='text-align:center;'>🔒 {t('Restricted Access','Acceso Restringido')}</h1>", unsafe_allow_html=True)
        st.text_input(f"🔑 {t('Enter password:','Introduce la contraseña:')}", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(f"🔑 {t('Enter password:','Introduce la contraseña:')}", type="password", on_change=password_entered, key="password")
        st.error(t("😕 Incorrect password.", "😕 Contraseña incorrecta."))
        return False
    return True

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
@st.cache_data
def load_daily_data_for_years(years):
    dfs = []
    for y in years:
        archivo = f'allh_diario_{y}.parquet'
        if os.path.exists(archivo):
            dfs.append(pd.read_parquet(archivo))
    if not dfs: return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    for col in ['UP', 'MA', 'Tech']:
        if col in df.columns: df[col] = df[col].astype('category')
    return df

@st.cache_data
def get_daily_date_bounds(min_y, max_y):
    try:
        min_d = pd.read_parquet(f'allh_diario_{min_y}.parquet', columns=['Day'])['Day'].min().date()
        max_d = pd.read_parquet(f'allh_diario_{max_y}.parquet', columns=['Day'])['Day'].max().date()
        return min_d, max_d
    except:
        return pd.to_datetime('2023-01-01').date(), pd.to_datetime('today').date()

@st.cache_data
def load_power_data():
    try:
        if os.path.exists('ups_dashboard.parquet'):
            df = pd.read_parquet('ups_dashboard.parquet', columns=['UP', 'Power MW'])
            df['Power MW'] = pd.to_numeric(df['Power MW'], errors='coerce')
            return df.dropna(subset=['Power MW', 'UP'])
        return pd.DataFrame(columns=['UP', 'Power MW'])
    except:
        return pd.DataFrame(columns=['UP', 'Power MW'])

diario_files = glob.glob('allh_diario_*.parquet')
available_years = sorted([int(f.split('_')[-1].split('.')[0]) for f in diario_files if f.split('_')[-1].split('.')[0].isdigit()])

if not available_years:
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
gc.collect()

# --- NAVEGACIÓN ---
cont_nav.header(t("🧭 Navigation", "🧭 Menú de Navegación"))
name_main    = t("📈 Main Overview", "📈 Resumen Principal")
name_mra     = t("⚡ MRA Analysis", "⚡ Análisis MRA")
name_rt5     = t("📋 RT5 Detail", "📋 Detalle RT5")
name_gnera   = t("📊 Gnera Analysis", "📊 Análisis Gnera")
name_verbund = t("💶 Verbund Profit", "💶 Beneficio Verbund")
name_evo     = t("📈 Revenue Evolution", "📈 Evolución Ingresos")
name_supply  = t("🏪 Retailers (Supply)", "🏪 Comercializadoras (Supply)")

menu_options = [name_main, name_mra, name_rt5, name_gnera, name_verbund, name_evo, name_supply]
seleccion_menu = cont_nav.radio("Menu", menu_options, label_visibility="collapsed")

# ==============================================================================
# SECCIÓN 1: RESUMEN PRINCIPAL
# ==============================================================================
if seleccion_menu == name_main:
    section_header("📈", t("Ancillary Services Revenue Dispersion by Technology", "Dispersión de Ingresos en Servicios de Ajuste por Tecnología"))

    col_f1, col_f2 = st.columns(2)
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

    mask_active = (allh['Profit_rt'] != 0) | (allh['Profit_b'] != 0)
    active_ups = allh[mask_active]['UP'].unique()
    excluded_MAs = ["ENDESA","IBERDROLA","EDP","NATURGY","HOLALUZ","ALDROENERGIA Y SOLUCIONES SL"]
    allh_main = allh.loc[(allh['UP'].isin(active_ups)) & (~allh['MA'].isin(excluded_MAs))].copy()

    if aass_sel == 'no_sec': cols_sel = ['Profit_rt','Profit_tr_s','Profit_t','Profit_rr']
    elif aass_sel == 'sec':  cols_sel = ['Profit_b','Profit_se']
    else:                    cols_sel = ['Profit_rt','Profit_tr_s','Profit_t','Profit_rr','Profit_b','Profit_se']

    allh_main = allh_main.assign(Total_Profit=allh_main[cols_sel].sum(axis=1), Month=allh_main['Day'].dt.to_period('M'))
    monthly = allh_main.groupby(['UP','Tech','MA','Month'], observed=True).agg(
        Monthly_Profit=('Total_Profit','sum'), Monthly_Energy=('Energy_p48','sum')
    ).reset_index()
    monthly = pd.merge(monthly, df_power, on='UP', how='left')
    monthly['Profit_per_MW'] = (monthly['Monthly_Profit'] / monthly['Power MW']).replace([np.inf,-np.inf], 0).fillna(0)
    grouped = monthly.groupby(['UP','Tech','MA'], observed=True).agg(Profit_per_MW=('Profit_per_MW','mean')).reset_index()
    grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)
    grouped['MA'] = grouped['MA'].astype(str)

    def make_boxplot(tech, color_main, color_highlight):
        data = grouped[grouped['Tech'] == tech].copy()
        if data.empty:
            return None
        order = data.groupby('MA', observed=True)['Profit_per_MW'].mean().sort_values(ascending=False).index.tolist()
        data['MA'] = pd.Categorical(data['MA'], categories=order, ordered=True)
        data = data.sort_values('MA')

        normal = data[~data['is_Highlighted']]
        highlighted = data[data['is_Highlighted']]

        fig = go.Figure()
        # Construir fillcolor seguro desde hex
        r, g, b = px.colors.hex_to_rgb(color_main)
        fill_rgba = f"rgba({r},{g},{b},0.15)"
        for ma in order:
            ma_data = normal[normal['MA'] == ma]['Profit_per_MW']
            if ma_data.empty: continue
            fig.add_trace(go.Box(
                y=ma_data, name=str(ma), boxpoints=False,
                marker_color=color_main,
                line_color=color_main,
                fillcolor=fill_rgba,
                showlegend=False,
                hovertemplate=f"<b>{ma}</b><br>Mediana: %{{median:.1f}} €/MW<br>IQR: %{{q1:.1f}} – %{{q3:.1f}}<extra></extra>"
            ))
        if not highlighted.empty:
            fig.add_trace(go.Scatter(
                x=highlighted['MA'].astype(str), y=highlighted['Profit_per_MW'],
                mode='markers',
                marker=dict(color='#f87171', size=10, symbol='diamond', line=dict(color='white', width=1.5)),
                name=t('Highlighted','Resaltadas'),
                hovertemplate="<b>%{x}</b><br>UP: %{customdata}<br>Profit/MW: %{y:.1f} €<extra></extra>",
                customdata=highlighted['UP']
            ))

        fig.add_hline(y=0, line_dash="dot", line_color="#4b5563", line_width=1)
        fig.update_layout(**base_layout(
            title=dict(text=f"<b>{tech}</b> · {t('Profit/MW by Market Agent','Profit/MW por Representante')}", font=dict(size=13, color="#1e293b")),
            xaxis_title="",
            yaxis_title=t("Avg Monthly Profit / MW (€)", "Profit Mensual Medio / MW (€)"),
            height=430,
        ))
        fig.update_xaxes(gridcolor="#e2e8f0", tickangle=-35)
        fig.update_yaxes(gridcolor="#e2e8f0", zerolinecolor="#94a3b8")
        return fig

    c1, c2 = st.columns(2)
    with c1:
        fig_solar = make_boxplot('Solar PV', '#f59e0b', '#f87171')
        if fig_solar: st.plotly_chart(fig_solar, use_container_width=True)
        else: st.info(t("No Solar PV data.","Sin datos de Solar PV."))
    with c2:
        fig_wind = make_boxplot('Wind', '#34d399', '#f87171')
        if fig_wind: st.plotly_chart(fig_wind, use_container_width=True)
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
            sel_ma = st.selectbox(t("1. Market Agent (MA)","1. Representante (MA)"), qualified_MAs)
        with f_tech:
            tech_opts = sorted(allh_mra.loc[allh_mra['MA']==sel_ma,'Tech'].unique()) if sel_ma != t('No data','Sin datos') else [t('No data','Sin datos')]
            sel_tech = st.selectbox(t("2. Technology","2. Tecnología"), tech_opts)
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
                                  'Profit_se','Profit_b','Profit_i','Profit_tr','Profit_p48','Energy_tr',
                                  'Energy_rt','Energy_t','Energy_rr','Energy_se','Energy_i','Rev_spot']
            for c in numeric_cols_avail:
                if c not in up_df.columns: up_df[c] = 0.0

            up_hourly = up_df.groupby(cols_to_groupby, observed=True)[numeric_cols_avail].sum(numeric_only=True).reset_index()
            up_hourly['Year_Month'] = up_hourly['Day'].dt.to_period('M').astype(str)
            up_hourly['Profit_AASS'] = up_hourly[['Profit_rt','Profit_t','Profit_rr','Profit_se','Profit_b','Profit_tr']].sum(axis=1)
            up_hourly['Energy_AASS'] = up_hourly[['Energy_rt','Energy_t','Energy_rr','Energy_se','Energy_tr']].sum(axis=1)
            if up_hourly['Profit_p48'].sum() == 0 and 'Rev_spot' in up_hourly.columns:
                up_hourly['Profit_p48'] = up_hourly['Rev_spot']
            cols_mkts = ['Profit_rt','Profit_t','Profit_rr','Profit_b','Profit_se','Profit_i','Profit_tr']
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
                'RT5':         total_row.get('Profit_tr',0)/energy_base,
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

            up_summary = up_hourly.groupby([group_col], observed=True)[['PBF','Energy_p48','Energy_RT1','Profit_AASS','Profit_tr','Profit_i']].sum(numeric_only=True).reset_index()
            up_summary['% P48 vs PBF'] = up_summary['Energy_p48'] / up_summary['PBF'].replace(0,np.nan)
            up_summary['% RT1 vs PBF'] = -up_summary['Energy_RT1'] / up_summary['PBF'].replace(0,np.nan)
            up_summary['Intras €/MWh']  = up_summary['Profit_i'] / up_summary['Energy_p48'].replace(0,np.nan)
            up_summary['AASS €/MWh']    = up_summary['Profit_AASS'] / up_summary['Energy_p48'].replace(0,np.nan)

            df_table = up_summary[[group_col,'% P48 vs PBF','% RT1 vs PBF','Profit_tr','Profit_AASS','Profit_i','Intras €/MWh','AASS €/MWh']].copy()
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
            'FCTRAV2':['Calatrava',41.0,0.5],'EAYAMON':['Ayamonte',26.0,0.5],'EGST146':['Barroso',21.6,0.5],
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

        totales = df_agg_v.select_dtypes(include=[np.number]).sum()
        totales['UP'] = 'Total'
        totales['Profit Verbund / MW'] = totales['Profit Verbund']/totales['Potencia MW'] if totales['Potencia MW']>0 else 0
        df_final_v = pd.concat([df_agg_v, pd.DataFrame([totales])], ignore_index=True)
        df_final_v.insert(1,'Installation',[val[0] for val in INPUT_DATA.values()]+['Total'])

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
            .apply(lambda row: ['font-weight:bold; background:#0d1424' if row['UP']=='Total' else '' for _ in row], axis=1),
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
        col_e1, col_e2 = st.columns(2)
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

        df_evo_temp = allh.loc[(allh['MA']==ma_input) & (allh['Tech']==tech_input)]
        mask_active_ups = (df_evo_temp['Profit_rt']!=0) | (df_evo_temp['Profit_b']!=0) | (df_evo_temp['Profit_t']!=0)
        ups_validas = df_evo_temp.loc[mask_active_ups,'UP'].unique()
        df_evo = df_evo_temp.loc[df_evo_temp['UP'].isin(ups_validas)].copy()

        if df_evo.empty:
            st.info(t("No data for this combination.","No hay datos para esta combinación."))
        else:
            df_evo['YearMonth'] = df_evo['Day'].dt.to_period('M').astype(str)
            df_evo['Total_Profit'] = df_evo[['Profit_rt','Profit_tr_s','Profit_t','Profit_rr','Profit_b','Profit_se']].sum(axis=1)

            df_evo_m = df_evo.groupby(['UP','YearMonth'], observed=True).agg(
                Total_Profit=('Total_Profit','sum'), Total_Energy=('Energy_p48','sum')
            ).reset_index().sort_values('YearMonth')
            df_evo_m['Profit_per_MWh'] = df_evo_m['Total_Profit'] / df_evo_m['Total_Energy'].replace(0,np.nan)
            df_evo_m['Total_Profit_k'] = df_evo_m['Total_Profit'] / 1000
            df_evo_m['UP'] = df_evo_m['UP'].astype(str)

            if len(ups_validas) > 20:
                st.warning(t("Showing top 20 UPs by Total Profit.","⚠️ Mostrando solo el Top 20 de UPs."))
                top_ups = df_evo_m.groupby('UP', observed=True)['Total_Profit'].sum().nlargest(20).index
                df_evo_m = df_evo_m[df_evo_m['UP'].isin(top_ups)]

            # 3 gráficos Plotly interactivos
            c_evo1, c_evo2, c_evo3 = st.columns(3)

            def make_line(df, y_col, title, y_label, color_col='UP'):
                fig = px.line(
                    df, x='YearMonth', y=y_col, color=color_col,
                    markers=True,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    hover_data={'YearMonth':True, y_col:':.2f', color_col:True}
                )
                fig.update_traces(line=dict(width=2), marker=dict(size=5))
                fig.update_layout(
                    title=dict(text=title, font=dict(size=12, color="#1e293b")),
                    xaxis_title="", yaxis_title=y_label,
                    paper_bgcolor="#ffffff", plot_bgcolor="#f8fafc",
                    font=dict(family="Inter", color="#475569"), title_font=dict(family="Inter", color="#1e293b", size=13),
                    legend=dict(title="", font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=10,r=10,t=45,b=10), height=380,
                    hovermode='x unified'
                )
                fig.update_xaxes(gridcolor="#e2e8f0", tickangle=-35, tickfont=dict(size=9))
                fig.update_yaxes(gridcolor="#e2e8f0")
                return fig

            with c_evo1:
                st.plotly_chart(make_line(df_evo_m,'Profit_per_MWh',t("Profit (€/MWh)","Evolución Profit (€/MWh)"),"€/MWh"), use_container_width=True)
            with c_evo2:
                st.plotly_chart(make_line(df_evo_m,'Total_Energy',t("Production (MWh)","Producción (MWh)"),"MWh"), use_container_width=True)
            with c_evo3:
                st.plotly_chart(make_line(df_evo_m,'Total_Profit_k',t("Total Profit (k€)","Profit Total (k€)"),"k€"), use_container_width=True)

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

            fig_sc = go.Figure()
            for positive, color, name_ in [
                (True,  C_POS, t("Profit > 0","Beneficio > 0")),
                (False, C_NEG, t("Profit < 0","Pérdida")),
            ]:
                sub = sc_data[sc_data['profit_positive'] == positive]
                if sub.empty: continue
                fig_sc.add_trace(go.Scatter(
                    x=sub['Share_i_pct'],
                    y=sub['Profit_per_MWh_i'],
                    mode='markers+text',
                    marker=dict(
                        size=np.sqrt(sub['abs_profit']) / np.sqrt(sub['abs_profit'].max()) * 45 + 8,
                        color=color, opacity=0.75,
                        line=dict(color='white', width=1)),
                    text=sub['MA'],
                    textposition='top center',
                    textfont=dict(size=9, color="#475569"),
                    name=name_,
                    customdata=np.stack([
                        sub['Total_Profit_i'],
                        sub['Inc_vs_Spot_pct'],
                        sub['Vol_Abs_i']
                    ], axis=-1),
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        "Cuota intra: %{x:.1f}%<br>"
                        "€/MWh: %{y:.3f}<br>"
                        "Profit: %{customdata[0]:,.0f} €<br>"
                        "Sobre-ingreso vs spot: %{customdata[1]:.2f}%<br>"
                        "Volumen: %{customdata[2]:,.0f} MWh<extra></extra>")
                ))

            # Líneas de referencia en (0,0) del eje Y y media de cuota
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
