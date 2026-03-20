# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.ticker as mtick
import matplotlib.patches as patches
from matplotlib.ticker import FuncFormatter
import glob
import gc
import os

st.set_page_config(page_title="Dashboard Ancillary Services", layout="wide", page_icon="📊")

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
<style>
    [data-testid="stDataFrame"] > div { margin-bottom: 20px; }
    .section-title { color: #40466e; font-size: 20px; font-weight: bold; margin-bottom: 15px; margin-top: 10px; border-bottom: 2px solid #f0f2f6; padding-bottom: 5px; }
    div.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# --- IDIOMA (BILINGÜE) ---
lang = st.sidebar.radio("🌐 Language / Idioma", ["English", "Español"])

def t(en, es):
    return en if lang == "English" else es

# --- SISTEMA DE CONTRASEÑA ---
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
        st.markdown(f"<h1 style='text-align: center;'>🔒 {t('Restricted Access', 'Acceso Restringido')}</h1>", unsafe_allow_html=True)
        st.text_input(f"🔑 {t('Enter password:', 'Introduce la contraseña:')}", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(f"🔑 {t('Enter password:', 'Introduce la contraseña:')}", type="password", on_change=password_entered, key="password")
        st.error(t("😕 Incorrect password.", "😕 Contraseña incorrecta."))
        return False
    else:
        return True

if not check_password():
    st.stop()

st.title(t("📊 Performance Analysis: Ancillary & Intraday Markets", "📊 Análisis de Desempeño: Mercados de Ajuste e Intradiarios"))

if st.sidebar.button(t("🧹 Clear Cache & Reload", "🧹 Borrar Caché y Recargar Datos")):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")

# ==============================================================================
# INTERRUPTOR MAESTRO Y CARGA DE DATOS (ARQUITECTURA DUAL)
# ==============================================================================
modo_opciones = [
    t("📅 Strategic Mode (Daily - Full Year)", "📅 Modo Estratégico (Diario - Año Completo)"),
    t("⏱️ Operational Mode (Hourly - 1 Month)", "⏱️ Modo Operativo (Horario - 1 Mes)")
]
modo_app = st.sidebar.radio(t("🔍 Analysis Mode:", "🔍 Modo de Análisis:"), modo_opciones)

is_hourly = (modo_app == modo_opciones[1])

# --- FUNCIONES DE CARGA ---
@st.cache_data
def load_daily_data():
    if not os.path.exists('allh_diario_2025.parquet'):
        st.error(t("Daily file 'allh_diario_2025.parquet' not found.", "Archivo diario 'allh_diario_2025.parquet' no encontrado en GitHub."))
        return pd.DataFrame()
    df = pd.read_parquet('allh_diario_2025.parquet')
    for col in ['UP', 'MA', 'Tech']:
        if col in df.columns: df[col] = df[col].astype('category')
    return df

@st.cache_data
def load_hourly_data(mes):
    f1, f2 = f'allh_{mes}_part1.parquet', f'allh_{mes}_part2.parquet'
    if not (os.path.exists(f1) and os.path.exists(f2)):
        st.error(f"{t('Missing parts for month', 'Faltan archivos (part1 y part2) para el mes')} {mes}")
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(f1), pd.read_parquet(f2)], ignore_index=True)
    for col in ['UP', 'MA', 'Tech']:
        if col in df.columns: df[col] = df[col].astype('category')
    return df

@st.cache_data
def load_power_data():
    try:
        if os.path.exists('ups_dashboard.parquet'):
            df = pd.read_parquet('ups_dashboard.parquet', columns=['UP', 'Power MW'])
            df['Power MW'] = pd.to_numeric(df['Power MW'], errors='coerce')
            return df.dropna(subset=['Power MW', 'UP'])
        return pd.DataFrame(columns=['UP', 'Power MW'])
    except: return pd.DataFrame(columns=['UP', 'Power MW'])

# --- LÓGICA DE CARGA SEGÚN MODO ---
if is_hourly:
    archivos_disponibles = glob.glob('allh_*_part*.parquet')
    meses_brutos = set()
    for f in archivos_disponibles:
        partes = f.split('_')
        if len(partes) >= 2 and len(partes[1]) == 6: meses_brutos.add(partes[1])
    meses_disponibles = sorted(list(meses_brutos), key=lambda x: (x[2:], x[:2]))
    
    if not meses_disponibles:
        st.error(t("No hourly data found.", "No hay datos horarios en el repositorio."))
        st.stop()
        
    meses_formateados = {m: f"{m[:2]}/{m[2:]}" for m in meses_disponibles}
    selected_month = st.sidebar.selectbox(t("Select month:", "Selecciona el mes a cargar:"), options=meses_disponibles, format_func=lambda x: meses_formateados.get(x, x), index=len(meses_disponibles)-1)
    
    allh_full = load_hourly_data(selected_month)
else:
    allh_full = load_daily_data()

df_power = load_power_data()

if allh_full.empty:
    st.stop()

# Blindaje de columnas numéricas (Añadidas las nuevas para MRA)
allh_full['Day'] = pd.to_datetime(allh_full['Day'])
cols_to_ensure = ['Profit_rt', 'Profit_tr_s', 'Profit_tr', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i',
                  'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se', 'Energy_tr', 'Energy_i', 'Profit_p48', 'Energy_p48', 'PBF', 'Energy_RT1', 'Rev_tr', 'Rev_spot']
for col in cols_to_ensure:
    if col not in allh_full.columns: allh_full[col] = 0.0
    else: allh_full[col] = pd.to_numeric(allh_full[col], errors='coerce').fillna(0)

gc.collect()

# --- FILTRO DE FECHAS (GLOBAL) ---
st.sidebar.markdown("---")
st.sidebar.header(t("📅 Date Range", "📅 Rango de Fechas"))
min_date, max_date = allh_full['Day'].min().date(), allh_full['Day'].max().date()
selected_dates = st.sidebar.date_input(t("Select period:", "Selecciona periodo:"), value=(min_date, max_date), min_value=min_date, max_value=max_date)

start_date, end_date = selected_dates if len(selected_dates) == 2 else (min_date, max_date)
allh = allh_full.loc[(allh_full['Day'].dt.date >= start_date) & (allh_full['Day'].dt.date <= end_date)]
gc.collect()

# ==============================================================================
# MENÚ DE NAVEGACIÓN DINÁMICO Y A PRUEBA DE FALLOS
# ==============================================================================
st.sidebar.markdown("---")
st.sidebar.header(t("🧭 Navigation", "🧭 Menú de Navegación"))

name_main = t("📈 Main Overview", "📈 Resumen Principal")
name_mra = t("⚡ MRA Analysis", "⚡ Análisis MRA")
name_rt5 = t("📋 RT5 Detail", "📋 Detalle RT5")
name_gnera = t("📊 Gnera Analysis", "📊 Análisis Gnera")
name_verbund = t("💶 Verbund Profit", "💶 Beneficio Verbund")
name_evo = t("📈 Revenue Evolution", "📈 Evolución Ingresos")

menu_options = [name_main, name_mra, name_gnera, name_verbund, name_evo]

if is_hourly:
    menu_options.insert(2, name_rt5)

seleccion_menu = st.sidebar.radio("Menu", menu_options, label_visibility="collapsed")

# ==============================================================================
# SECCIÓN 1: RESUMEN PRINCIPAL
# ==============================================================================
if seleccion_menu == name_main:
    st.markdown(f'<div class="section-title">{t("Ancillary Services Revenue Dispersion by Technology", "Dispersión de ingresos en Servicios de ajuste por Tecnología")}</div>', unsafe_allow_html=True)
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        ups_interes = ['CLIFV30', 'CLIFV31', 'CLIFV32', 'UPBUS', 'UPLMP', 'UPSLN', 'GALPS59', 'GALPS57', 'GALPS56', 'FCTRAV2', 'EFGNRA', 'PEVER', 'PEVER2', 'EAYAMON', 'EGST146']
        installation = ['Pinos Puente 1', 'Pinos Puente 2', 'Pinos Puente 3', 'Buseco', 'Loma', 'La Solana', 'Buseco_Galp', 'Loma_Galp', 'La Solana_Galp', 'Calatrava', 'Bodenaya + Pico + Others', 'Sorolla 1', 'Mallen', 'Ayamonte', 'Barroso']
        ma_mapping = allh[['UP', 'MA']].dropna().drop_duplicates(subset=['UP']).set_index('UP')['MA'].to_dict()
        selected_ups = st.multiselect(t("🔴 Installations to Highlight:", "🔴 Instalaciones a Resaltar:"), options=ups_interes, default=[u for u in ['PEVER', 'EGST146'] if u in ups_interes], format_func=lambda x: f"{installation[ups_interes.index(x)]} ({ma_mapping.get(x, 'Desc')})")
    
    with col_f2:
        aass_sel = st.radio(t("⚙️ Market Selection:", "⚙️ Selección de Mercados:"), options=['no_sec', 'sec', 'all'], index=2, format_func=lambda x: t("No Secondary", "Sin Secundaria") if x == 'no_sec' else (t("Only Secondary", "Solo Secundaria") if x == 'sec' else t("All Markets", "Todos los mercados")), horizontal=True)

    mask_active = (allh['Profit_rt'] != 0) | (allh['Profit_b'] != 0)
    active_ups = allh[mask_active]['UP'].unique()
    excluded_MAs = ["ENDESA", "IBERDROLA", "EDP", "NATURGY", "HOLALUZ", "ALDROENERGIA Y SOLUCIONES SL"]
    allh_main = allh.loc[(allh['UP'].isin(active_ups)) & (~allh['MA'].isin(excluded_MAs))].copy()
    
    if aass_sel == 'no_sec': cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr']
    elif aass_sel == 'sec': cols_sel = ['Profit_b', 'Profit_se']
    else: cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']
    
    allh_main = allh_main.assign(Total_Profit=allh_main[cols_sel].sum(axis=1), Month=allh_main['Day'].dt.to_period('M'))
    monthly = allh_main.groupby(['UP', 'Tech', 'MA', 'Month'], observed=True).agg(Monthly_Profit=('Total_Profit', 'sum'), Monthly_Energy=('Energy_p48', 'sum')).reset_index()
    monthly = pd.merge(monthly, df_power, on='UP', how='left')
    monthly['Profit_per_MW'] = (monthly['Monthly_Profit'] / monthly['Power MW']).replace([np.inf, -np.inf], 0).fillna(0)
    grouped = monthly.groupby(['UP', 'Tech', 'MA'], observed=True).agg(Profit_per_MW=('Profit_per_MW', 'mean')).reset_index()
    grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)
    
    c1, c2 = st.columns(2)
    with c1:
        s_data = grouped[grouped['Tech'] == 'Solar PV']
        if not s_data.empty:
            order = s_data.groupby('MA', observed=True)['Profit_per_MW'].mean().sort_values(ascending=False).index
            fig, ax = plt.subplots(figsize=(8, 5))
            sns.boxplot(data=s_data, x='MA', y='Profit_per_MW', showfliers=False, color='orange', order=order, ax=ax)
            if not s_data[s_data['is_Highlighted']].empty:
                sns.stripplot(data=s_data[s_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=8, color='red', order=order, ax=ax)
            ax.set_title('SOLAR PV: Profit ordered by Agent Mean'); ax.tick_params(axis='x', rotation=45); ax.axhline(0, color='grey', linestyle='--')
            st.pyplot(fig); plt.close(fig) 
        else: st.info(t("No data for Solar PV.", "Sin datos de Solar PV."))
    with c2:
        w_data = grouped[grouped['Tech'] == 'Wind']
        if not w_data.empty:
            order = w_data.groupby('MA', observed=True)['Profit_per_MW'].mean().sort_values(ascending=False).index
            fig, ax = plt.subplots(figsize=(8, 5))
            sns.boxplot(data=w_data, x='MA', y='Profit_per_MW', showfliers=False, color='lightgreen', order=order, ax=ax)
            if not w_data[w_data['is_Highlighted']].empty:
                sns.stripplot(data=w_data[w_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=8, color='red', order=order, ax=ax)
            ax.set_title('WIND: Profit ordered by Agent Mean'); ax.tick_params(axis='x', rotation=45); ax.axhline(0, color='grey', linestyle='--')
            st.pyplot(fig); plt.close(fig)
    gc.collect()

# ==============================================================================
# SECCIÓN 2: ANÁLISIS MRA (Con el nuevo código y gráficos)
# ==============================================================================
elif seleccion_menu == name_mra:
    st.markdown(f'<div class="section-title">{t("MRA Analysis - Technology - Installation", "Análisis MRA - Tecnología - Instalación")}</div>', unsafe_allow_html=True)
    
    PROFIT_MAP = {
        'Profit_rt': 'RRTT F2', 'Profit_tr': 'RT5', 'Profit_tr_s': 'RT5_strategy',
        'Profit_t': 'Tertiary', 'Profit_rr': 'RR', 'Profit_b': 'Sec. Band',
        'Profit_se': 'Sec. Activation', 'Profit_i': 'Intraday'
    }

    f_ma, f_tech, f_up = st.columns(3)
    with f_ma:
        ma_mask = (allh['Profit_rt']!=0)|(allh['Profit_b']!=0)|(allh['Profit_t']!=0)|(allh['Profit_rr']!=0)
        qualified_MAs = sorted(allh[ma_mask]['MA'].unique()) if not allh[ma_mask].empty else [t('No data', 'Sin datos')]
        sel_ma = st.selectbox(t("1. Market Agent (MA)", "1. Representante (MA)"), qualified_MAs)
    with f_tech:
        tech_opts = sorted(allh[allh['MA'] == sel_ma]['Tech'].unique()) if sel_ma != t('No data', 'Sin datos') else [t('No data', 'Sin datos')]
        sel_tech = st.selectbox(t("2. Technology", "2. Tecnología"), tech_opts)
    with f_up:
        up_rt5 = allh.loc[(allh['MA']==sel_ma) & (allh['Tech']==sel_tech)]
        up_opts = [t('Any UP', 'Cualquier UP')] + sorted(up_rt5[(up_rt5['Profit_rt']!=0)|(up_rt5['Profit_b']!=0)]['UP'].unique().tolist())
        sel_up = st.selectbox(t("3. Production Unit (UP)", "3. Unidad (UP)"), up_opts)

    if sel_up == t('Any UP', 'Cualquier UP'): up_df = allh.loc[allh['UP'].isin(up_rt5['UP'].unique())].copy()
    else: up_df = allh.loc[allh['UP'] == sel_up].copy()
        
    if up_df.empty:
        st.warning(t("No data available.", "No hay datos disponibles para la combinación seleccionada."))
    else:
        # --- CÁLCULOS BASE ---
        cols_to_groupby = ['Tech','MA','Day','hour'] if is_hourly else ['Tech','MA','Day']
        numeric_cols_avail = ['PBF', 'Energy_p48', 'Energy_RT1', 'Profit_rt', 'Profit_t', 'Profit_rr', 
                              'Profit_se', 'Profit_b', 'Profit_i', 'Profit_tr', 'Profit_p48', 'Energy_tr', 
                              'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se', 'Energy_i', 'Rev_spot']
        
        # Asegurar columnas
        for c in numeric_cols_avail:
            if c not in up_df.columns: up_df[c] = 0.0
            
        up_hourly = up_df.groupby(cols_to_groupby, observed=True)[numeric_cols_avail].sum(numeric_only=True).reset_index()
        
        up_hourly['Year_Month'] = up_hourly['Day'].dt.to_period('M').astype(str)
        up_hourly['Profit_AASS'] = up_hourly[['Profit_rt', 'Profit_t', 'Profit_rr', 'Profit_se', 'Profit_b','Profit_tr']].sum(axis=1)
        
        aass_energy_cols = ['Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se','Energy_tr']
        up_hourly['Energy_AASS'] = up_hourly[aass_energy_cols].sum(axis=1)
        
        if up_hourly['Profit_p48'].sum() == 0 and 'Rev_spot' in up_hourly.columns:
            up_hourly['Profit_p48'] = up_hourly['Rev_spot']

        cols_mkts = ['Profit_rt', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i', 'Profit_tr']
        up_hourly['Profit_total'] = up_hourly[cols_mkts].sum(axis=1)

        # --- 1. TABLA RESUMEN NATIVA ---
        st.markdown(f"##### {t('Performance Summary', 'Resumen de Rendimiento (Performance Summary)')}")
        date_range_days = (up_hourly['Day'].max() - up_hourly['Day'].min()).days
        group_col = 'Day' if date_range_days <= 10 else 'Year_Month'
        group_col_name = 'Date' if group_col == 'Day' else 'Month'
        
        up_summary = up_hourly.groupby([group_col], observed=True)[['PBF', 'Energy_p48', 'Energy_RT1', 'Profit_AASS', 'Profit_tr', 'Profit_i']].sum(numeric_only=True).reset_index()
        
        up_summary['% P48 vs PBF'] = up_summary['Energy_p48'] / up_summary['PBF'].replace(0, np.nan)
        up_summary['% RT1 vs PBF'] = -up_summary['Energy_RT1'] / up_summary['PBF'].replace(0, np.nan)
        up_summary['Intras €/MWh'] = up_summary['Profit_i'] / up_summary['Energy_p48'].replace(0, np.nan)
        up_summary['AASS €/MWh'] = up_summary['Profit_AASS'] / up_summary['Energy_p48'].replace(0, np.nan)

        df_table = up_summary[[group_col, '% P48 vs PBF', '% RT1 vs PBF', 'Profit_tr', 'Profit_AASS', 'Profit_i', 'Intras €/MWh', 'AASS €/MWh']].copy()
        df_table.columns = [group_col_name, '% P48 vs PBF', '% RT1 vs PBF', 'Real Time (€)', 'AASS (€)', 'Intras (€)', 'Intras (€/MWh)', 'AASS (€/MWh)']
        
        # Convertir Fechas a string si es necesario para evitar fallos
        df_table[group_col_name] = df_table[group_col_name].astype(str)
        
        st.dataframe(df_table.set_index(group_col_name).style.format({
            '% P48 vs PBF': '{:.1%}', '% RT1 vs PBF': '{:.1%}', 'Real Time (€)': '{:,.0f} €', 'AASS (€)': '{:,.0f} €', 
            'Intras (€)': '{:,.0f} €', 'Intras (€/MWh)': '{:.2f} €', 'AASS (€/MWh)': '{:.2f} €'
        }), width='stretch')

        # --- 2. WATERFALL MEJORADO Y BARRAS (Economic Performance) ---
        st.markdown(f"##### {t('Economic Performance', 'Rendimiento Económico (Waterfall & Barras)')}")
        total_row = up_hourly[numeric_cols_avail + cols_mkts + ['Profit_p48', 'Profit_total']].sum(numeric_only=True)
        energy_base = total_row.get('Energy_p48', 0) - total_row.get('Energy_tr', 0)
        if energy_base == 0: energy_base = 1
        
        wf_data = {
            'Spot': total_row.get('Profit_p48', 0) / energy_base,
            'RRTT Ph2': total_row.get('Profit_rt', 0) / energy_base,
            'RT5': total_row.get('Profit_tr', 0) / energy_base,
            'Tertiary': total_row.get('Profit_t', 0) / energy_base,
            'RR': total_row.get('Profit_rr', 0) / energy_base,
            'Sec. Band': total_row.get('Profit_b', 0) / energy_base,
            'Sec. Energy': total_row.get('Profit_se', 0) / energy_base,
            'Intras': total_row.get('Profit_i', 0) / energy_base
        }
        wf_data = {k: v for k, v in wf_data.items() if abs(v) > 0.01}
        
        profit_total_data = total_row[cols_mkts].sort_values(ascending=False)
        profit_total_data.index = [PROFIT_MAP.get(i, i) for i in profit_total_data.index]
        
        c_pos = '#2E8B57'; c_neg = '#CD5C5C'; c_tot = '#4682B4'; c_bg = 'whitesmoke'
        
        fig2, (ax_wf, ax_bar) = plt.subplots(1, 2, figsize=(18, 7))
        def style_card(ax, title):
            ax.set_facecolor(c_bg)
            rect = patches.Rectangle((0, 0), 1, 1, transform=ax.transAxes, linewidth=0, facecolor=c_bg, zorder=0, alpha=0.5)
            ax.add_patch(rect)
            ax.text(0.5, 1.05, title, transform=ax.transAxes, ha='center', va='bottom', fontsize=14, fontweight='bold', color='#333333')
            for spine in ['top', 'right', 'left']: ax.spines[spine].set_visible(False)
            ax.spines['bottom'].set_color('#cccccc')

        if wf_data:
            labels = list(wf_data.keys()) + ['TOTAL']
            values = list(wf_data.values())
            
            ax_wf.bar(labels[0], values[0], color=c_tot, width=0.6, zorder=3)
            ax_wf.text(0, values[0] + (1 if values[0]>0 else -2), f"{values[0]:,.0f}", ha='center', va='bottom' if values[0]>0 else 'top', fontweight='bold', color='#333333')
            
            curr_h = values[0]
            for i in range(1, len(values)):
                change = values[i]
                color = c_pos if change >= 0 else c_neg
                prev_h = curr_h
                ax_wf.plot([i-1.3, i+0.3], [prev_h, prev_h], color='gray', linestyle='--', linewidth=0.8, alpha=0.7, zorder=2)
                ax_wf.bar(labels[i], change, bottom=curr_h, color=color, width=0.6, zorder=3)
                offset = 1 if change >= 0 else -1
                ax_wf.text(i, curr_h + change + offset, f"{change:+,.0f}", ha='center', va='bottom' if change>0 else 'top', fontsize=11, color='#333333')
                curr_h += change
                
            ax_wf.bar(labels[-1], curr_h, color=c_tot, width=0.6, zorder=3)
            ax_wf.plot([len(values)-1.3, len(values)-0.7], [curr_h, curr_h], color='gray', linestyle='--', linewidth=0.8, alpha=0.7)
            ax_wf.text(len(labels)-1, curr_h + (1 if curr_h>0 else -1), f"{curr_h:,.0f}", ha='center', va='bottom' if curr_h>0 else 'top', fontweight='bold', fontsize=12, color='#333333')
            
            style_card(ax_wf, "Unit Profit Breakdown (€/MWh)")
            ax_wf.set_yticks([]); ax_wf.grid(axis='y', linestyle=':', color='gray', alpha=0.3)
            plt.setp(ax_wf.get_xticklabels(), rotation=45, ha="right", fontsize=11, color='#555555')
        
        if not profit_total_data.empty:
            colors = [c_pos if x >= 0 else c_neg for x in profit_total_data]
            bars = ax_bar.barh(profit_total_data.index, profit_total_data, color=colors, zorder=3)
            style_card(ax_bar, "Total Accumulated Profit (€)")
            ax_bar.spines['bottom'].set_visible(False)
            ax_bar.spines['left'].set_color('#cccccc')
            ax_bar.set_xticks([])
            ax_bar.set_yticks(range(len(profit_total_data)))
            ax_bar.set_yticklabels(profit_total_data.index, fontsize=12, color='#444444', fontweight='medium')
            ax_bar.tick_params(axis='y', length=0)
            ax_bar.grid(axis='x', linestyle=':', color='gray', alpha=0.3)
            
            data_range = profit_total_data.max() - profit_total_data.min()
            if data_range == 0: data_range = abs(profit_total_data.max()) or 100
            pad = data_range * 0.02 
            ax_bar.set_xlim(min(profit_total_data.min(), 0), max(profit_total_data.max(), 0) + (pad * 6))
            
            for rect in bars:
                width = rect.get_width()
                ax_bar.text(width + pad, rect.get_y() + rect.get_height()/2, f'{int(width):,}', ha='left', va='center', fontweight='bold', fontsize=11, color='#333333')
                
        plt.subplots_adjust(wspace=0.4)
        st.pyplot(fig2); plt.close(fig2)

        # --- 3. DAILY PROFIT EVOLUTION (Stacked Bar) ---
        st.markdown(f"##### {t('Daily Profit Breakdown', 'Desglose Diario de Beneficio')}")
        daily_data = up_hourly.groupby('Day')[cols_mkts].sum()
        daily_data.columns = [PROFIT_MAP.get(c, c) for c in daily_data.columns]
        daily_data.index = daily_data.index.strftime('%d/%m/%Y')
        
        fig5, ax5 = plt.subplots(figsize=(16, 6))
        daily_data.plot(kind='bar', stacked=True, ax=ax5, colormap='tab20', width=0.8)
        ax5.set_ylabel('Profit (€)', fontsize=12); ax5.set_xlabel('Date', fontsize=12)
        ax5.grid(axis='y', linestyle='--', alpha=0.4)
        ax5.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, p: format(int(x), ',')))
        ax5.legend(title='Market Breakdown', bbox_to_anchor=(1.01, 1), loc='upper left')
        
        n_days = len(daily_data)
        if n_days > 20: 
            step = max(1, n_days // 20)
            ax5.set_xticks(range(0, n_days, step))
            ax5.set_xticklabels(daily_data.index[::step], rotation=45, ha='right')
        else:
            plt.setp(ax5.get_xticklabels(), rotation=45, ha="right")
        plt.tight_layout()
        st.pyplot(fig5); plt.close(fig5)

        # --- 4. SECCIÓN HORARIA (SÓLO SI IS_HOURLY) ---
        if is_hourly:
            st.markdown("---")
            st.markdown(f"##### {t('Hourly Profiles Analysis', 'Análisis de Perfiles Horarios')}")
            
            # Profiles (Average & Full)
            hourly_prof_avg = up_hourly.groupby('hour')[['PBF', 'Energy_p48', 'Energy_i', 'Energy_tr', 'Energy_AASS']].mean()
            up_hourly['datetime'] = pd.to_datetime(up_hourly['Day']) + pd.to_timedelta(up_hourly['hour'], unit='h')
            hourly_prof_ts = up_hourly.set_index('datetime')[['PBF', 'Energy_p48', 'Energy_i', 'Energy_tr', 'Energy_AASS']].sort_index()

            labels_prof = {'PBF': 'PBF', 'Energy_p48': 'Spot', 'Energy_i': 'Intra', 'Energy_tr': 'RT5', 'Energy_AASS': 'AASS'}
            fig3, (ax_avg, ax_ts) = plt.subplots(2, 1, figsize=(16, 12))
            
            for col in labels_prof:
                if col in hourly_prof_avg.columns:
                    style = '--' if 'PBF' in col else '-'
                    color = 'red' if col == 'Energy_AASS' else None
                    ax_avg.plot(hourly_prof_avg.index, hourly_prof_avg[col], label=labels_prof[col], ls=style, lw=1.5, color=color)
            ax_avg.set_title(t('Average Hourly Dispatch Profile (MW)', 'Perfil de Despacho Horario Medio (MW)'), fontsize=14); ax_avg.legend(); ax_avg.grid(True, alpha=0.3)

            for col in labels_prof:
                if col in hourly_prof_ts.columns:
                    style = '--' if 'PBF' in col else '-'
                    color = 'red' if col == 'Energy_AASS' else None
                    ax_ts.plot(hourly_prof_ts.index, hourly_prof_ts[col], label=labels_prof[col], ls=style, lw=1, alpha=0.8, color=color)
            ax_ts.set_title(t('Full Period Hourly Evolution (MW)', 'Evolución Horaria Periodo Completo (MW)'), fontsize=14); ax_ts.grid(True, alpha=0.3)
            plt.tight_layout()
            st.pyplot(fig3); plt.close(fig3)
            
            # Detalle Diario Opcional
            st.markdown(f"##### {t('Detailed Daily Inspection', 'Inspección Diaria Detallada')}")
            col_d1, _ = st.columns([1, 2])
            with col_d1:
                available_dates = up_hourly['Day'].dt.date.unique()
                input_detailed_date = st.date_input("Selecciona un día específico:", value=available_dates[0], min_value=min(available_dates), max_value=max(available_dates))
            
            if input_detailed_date:
                df_day = up_hourly[up_hourly['Day'].dt.date == input_detailed_date].copy()
                if not df_day.empty:
                    day_hourly = df_day.groupby('hour')[cols_mkts].sum()
                    day_hourly.columns = [PROFIT_MAP.get(c, c) for c in day_hourly.columns]
                    
                    fig4, ax4 = plt.subplots(figsize=(14, 6))
                    day_hourly.plot(kind='bar', stacked=True, ax=ax4, colormap='tab20')
                    ax4.set_title(f'Hourly Profit Breakdown: {input_detailed_date.strftime("%d/%m/%Y")}', fontsize=16, fontweight='bold', pad=15)
                    ax4.set_ylabel('Profit (€)'); ax4.set_xlabel('Hour')
                    ax4.grid(axis='y', alpha=0.3); ax4.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, p: format(int(x), ',')))
                    ax4.legend(bbox_to_anchor=(1.01, 1), loc='upper left')
                    plt.tight_layout()
                    st.pyplot(fig4); plt.close(fig4)
                else:
                    st.info(f"No hay datos horarios para {input_detailed_date}")
        else:
            st.info(t("Switch to Operational Mode (Hourly) to see Hourly Profiles and Detailed Day Inspection.", "Cambia al Modo Operativo (Horario) en la barra lateral para visualizar los Perfiles Horarios y el Detalle Diario."))

    except Exception as e:
        st.error(f"{t('Error processing MRA:', 'Error procesando MRA:')} {e}")
    gc.collect()

# ==============================================================================
# SECCIÓN 3: DETALLE RT5 (SOLO EN MODO HORARIO)
# ==============================================================================
elif is_hourly and seleccion_menu == name_rt5:
    st.markdown(f'<div class="section-title">{t("RT5 Detail: Prices & Offers", "Detalle RT5: Precios y Ofertas")}</div>', unsafe_allow_html=True)
    try:
        filtered_rt5 = allh.loc[(allh['Tech'].isin(['Solar PV', 'Wind'])) & (allh['Profit_tr_s'] != 0)].copy()
        filtered_rt5['Price_RT5'] = filtered_rt5['Rev_tr'] / filtered_rt5['Energy_tr'].replace(0, np.nan)
        filtered_rt5.dropna(subset=['Price_RT5'], inplace=True)
        
        if filtered_rt5.empty: st.info(t("No offers matched in RT5.", "No hay ofertas casadas en RT5."))
        else:
            col_rt_a1, col_rt_a2 = st.columns(2)
            with col_rt_a1:
                st.markdown(f"**{t('All Market (Min Bid < -50€)', 'Todo el Mercado (Min Bid < -50€)')}**")
                total_p_ma = filtered_rt5.groupby('MA', observed=True)['Profit_tr_s'].sum()
                e_p48_tr_diff_ma = filtered_rt5['Energy_p48'] - filtered_rt5['Energy_tr']
                eur_mwh_r_ma = filtered_rt5.groupby('MA', observed=True).apply(lambda x: x['Profit_tr_s'].sum() / e_p48_tr_diff_ma[x.index].sum()).replace([np.inf, -np.inf], 0).fillna(0)
                w_avg_bid_ma = filtered_rt5.groupby('MA', observed=True).apply(lambda x: (x['Price_RT5'] * x['Energy_tr']).sum() / x['Energy_tr'].sum()).replace([np.inf, -np.inf], 0).fillna(0)
                res_ma = pd.DataFrame({'Total Profit RT5': total_p_ma, '€/MWh_resource': eur_mwh_r_ma, 'Weighted Avg Bid': w_avg_bid_ma, 'Max Bid': filtered_rt5.groupby('MA', observed=True)['Price_RT5'].max(), 'Min Bid': filtered_rt5.groupby('MA', observed=True)['Price_RT5'].min()})
                filtered_res_ma = res_ma.dropna(subset=['Min Bid']); filtered_res_ma = filtered_res_ma[filtered_res_ma['Min Bid'] < -50]
                if filtered_res_ma.empty: st.info(t("No matches < -50€.", "Sin ofertas < -50€."))
                else: st.dataframe(filtered_res_ma.style.format({'Total Profit RT5': '{:,.2f} €', '€/MWh_resource': '{:.2f}', 'Weighted Avg Bid': '{:.2f}', 'Max Bid': '{:.2f}', 'Min Bid': '{:.2f}'}), width='stretch')

            with col_rt_a2:
                st.markdown(f"**{t('Specific Installations', 'Instalaciones Específicas (FCTRAV2, PEVER)')}**")
                up_rt5_v = filtered_rt5.loc[filtered_rt5['UP'].isin(['FCTRAV2', 'PEVER'])]
                if up_rt5_v.empty: st.info("Sin datos para FCTRAV2 o PEVER.")
                else:
                    e_p48_tr_diff_v = up_rt5_v['Energy_p48'] - up_rt5_v['Energy_tr']
                    eur_mwh_r_v = up_rt5_v.groupby('MA', observed=True).apply(lambda x: x['Profit_tr_s'].sum() / e_p48_tr_diff_v[x.index].sum()).replace([np.inf, -np.inf], 0).fillna(0)
                    w_avg_bid_v = up_rt5_v.groupby('MA', observed=True).apply(lambda x: (x['Price_RT5'] * x['Energy_tr']).sum() / x['Energy_tr'].sum()).replace([np.inf, -np.inf], 0).fillna(0)
                    res_v = pd.DataFrame({'Total Profit RT5': up_rt5_v.groupby('MA', observed=True)['Profit_tr_s'].sum(), '€/MWh_resource': eur_mwh_r_v, 'Weighted Avg Bid': w_avg_bid_v, 'Max Bid': up_rt5_v.groupby('MA', observed=True)['Price_RT5'].max(), 'Min Bid': up_rt5_v.groupby('MA', observed=True)['Price_RT5'].min()}).dropna(subset=['Min Bid'])
                    st.dataframe(res_v.style.format({'Total Profit RT5': '{:,.2f} €', '€/MWh_resource': '{:.2f}', 'Weighted Avg Bid': '{:.2f}', 'Max Bid': '{:.2f}', 'Min Bid': '{:.2f}'}), width='stretch')

            if not filtered_res_ma.empty:
                st.markdown("---")
                col_rt_b1, col_rt_b2 = st.columns(2)
                mas_to_plot_list = [m for m in filtered_res_ma.index if m != 'ESTABANELL Y PAHISA MERCATOR']
                df_graph = filtered_rt5.loc[filtered_rt5['MA'].isin(mas_to_plot_list)]
                with col_rt_b1:
                    fig_s, ax_s = plt.subplots(figsize=(8, 5))
                    sns.scatterplot(data=df_graph, x='MA', y='Price_RT5', alpha=0.3, s=30, color='#40466e', ax=ax_s)
                    ax_s.set_title("Scatter: Price_RT5 vs MA", fontsize=10); ax_s.tick_params(axis='x', rotation=90); st.pyplot(fig_s); plt.close(fig_s)
                with col_rt_b2:
                    fig_b, ax_b = plt.subplots(figsize=(8, 5))
                    sns.boxplot(data=df_graph, x='MA', y='Price_RT5', showfliers=False, palette='vlag', ax=ax_b)
                    ax_b.set_title("Boxplot: Price_RT5 matched by Market Agent", fontsize=10); ax_b.tick_params(axis='x', rotation=90); st.pyplot(fig_b); plt.close(fig_b)
    except Exception as e: st.error(f"Error Detalle RT5: {e}")

# ==============================================================================
# SECCIÓN 4: ANÁLISIS GNERA
# ==============================================================================
elif seleccion_menu == name_gnera:
    st.markdown(f'<div class="section-title">{t("Gnera Analysis", "Análisis Gnera")}</div>', unsafe_allow_html=True)
    try:
        POTENCIA_INSTALADA = {'EOTMR': 87.6, 'LECDE': 9.6, 'PEVER': 182.3, 'PEVER2': 29.8}
        UPS_INTERES = list(POTENCIA_INSTALADA.keys())
        PROFIT_MAP = {'Profit_rt': 'RRTT F2', 'Profit_tr': 'RT5', 'Profit_tr_s': 'RT5_strategy', 'Profit_t': 'Tertiary', 'Profit_rr': 'RR', 'Profit_b': 'Sec. Band', 'Profit_se': 'Sec. Activation'}
        
        gnwi = allh.loc[(allh['MA'] == 'GNERA') & (allh['Tech'] == 'Wind') & (allh['UP'].isin(UPS_INTERES))].copy()
        if gnwi.empty: st.info(t("No data for GNERA Wind.", "No hay datos de GNERA Wind para las instalaciones seleccionadas."))
        else:
            profit_cols_to_sum = list(PROFIT_MAP.keys())
            gnwi['Profit_Total_Extra'] = gnwi[[c for c in profit_cols_to_sum if c in gnwi.columns]].sum(axis=1)
            gnwi['Potencia_MW'] = gnwi['UP'].map(POTENCIA_INSTALADA)
            df_agg_gnera = gnwi.groupby('UP', observed=True)[[c for c in profit_cols_to_sum if c in gnwi.columns] + ['Profit_Total_Extra']].sum(numeric_only=True).reset_index()
            df_agg_gnera['Potencia_MW'] = df_agg_gnera['UP'].map(POTENCIA_INSTALADA)
            
            for col in [c for c in profit_cols_to_sum if c in df_agg_gnera.columns] + ['Profit_Total_Extra']: df_agg_gnera[f'{col}'] = df_agg_gnera[col] / df_agg_gnera['Potencia_MW']
            
            # HEATMAP
            st.markdown(f"##### {t('Summary (€/MW) as Heatmap', 'Resumen (€/MW) como Heatmap')}")
            df_heatmap = df_agg_gnera.set_index('UP').drop(columns=['Potencia_MW'])
            df_heatmap_components = df_heatmap.drop(columns=['Profit_Total_Extra'], errors='ignore')
            fig_hm, (ax_heat, ax_total) = plt.subplots(1, 2, figsize=(20, 8), gridspec_kw={'width_ratios': [7, 1]})
            sns.heatmap(df_heatmap_components, annot=True, fmt=',.2f', cmap='vlag', center=0, annot_kws={"size": 12}, ax=ax_heat)
            plt.setp(ax_heat.get_xticklabels(), rotation=45, ha="right", fontsize=10)
            if 'Profit_Total_Extra' in df_heatmap.columns:
                sns.heatmap(df_heatmap[['Profit_Total_Extra']], annot=True, fmt=',.2f', cmap='RdYlGn', center=df_heatmap[['Profit_Total_Extra']].mean().values[0], annot_kws={"size": 12, "weight": "bold"}, cbar=False, ax=ax_total)
            ax_total.set_yticks([])
            st.pyplot(fig_hm); plt.close(fig_hm)

            # GRÁFICOS HORARIOS (SÓLO SI ESTAMOS EN MODO OPERATIVO)
            if is_hourly:
                st.markdown("---")
                st.markdown(f"##### {t('Daily Profit Evolution (€/MW)', 'Evolución Diaria del Profit (€/MW)')}")
                gnwi['Profit_Total_eur_per_MW'] = gnwi['Profit_Total_Extra'] / gnwi['Potencia_MW']
                df_hourly_norm = gnwi.groupby(['UP', 'hour'], observed=True)['Profit_Total_eur_per_MW'].sum().reset_index()
                fig_evo, ax_evo = plt.subplots(figsize=(15, 6))
                sns.lineplot(data=df_hourly_norm, x='hour', y='Profit_Total_eur_per_MW', hue='UP', marker='o', ax=ax_evo)
                ax_evo.set_xticks(range(0, 24)); ax_evo.grid(True, alpha=0.3); st.pyplot(fig_evo); plt.close(fig_evo)

                st.markdown("---")
                st.markdown(f"##### {t('Stacked Profit Areas per UP (€/MW)', 'Áreas Apiladas de Profit por Instalación (€/MW)')}")
                for col in [c for c in profit_cols_to_sum if c in gnwi.columns]: gnwi[f"{col}_norm"] = gnwi[col] / gnwi['Potencia_MW'].replace(0, np.nan)
                df_hr_break = gnwi.groupby(['UP', 'hour'], observed=True)[[f"{c}_norm" for c in profit_cols_to_sum if c in gnwi.columns]].sum().reset_index()
                fig_st, axes_st = plt.subplots(2, 2, figsize=(20, 14), sharex=True, sharey=True); axes_st = axes_st.flatten()
                colors = plt.cm.get_cmap('tab20c', len(profit_cols_to_sum))
                for i, up in enumerate(UPS_INTERES):
                    ax = axes_st[i]
                    df_plot = df_hr_break[df_hr_break['UP'] == up]
                    if df_plot.empty: ax.set_title(f"{up} (No data)"); continue
                    labels_clean = [c.replace('_norm','') for c in df_plot.columns if '_norm' in c]
                    ax.stackplot(df_plot['hour'], [df_plot[c] for c in df_plot.columns if '_norm' in c], labels=labels_clean, colors=colors.colors, alpha=0.8)
                    ax.set_title(f"Desglose Profit: {up}", fontsize=14); ax.set_xticks(range(0, 24)); ax.grid(True, alpha=0.3)
                handles, labels = ax.get_legend_handles_labels()
                fig_st.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 0.98), ncol=min(4, len(labels)), fontsize=12)
                st.pyplot(fig_st); plt.close(fig_st)

                st.markdown("---")
                st.markdown(f"##### {t('PBF vs Energy_p48 (% Max PBF)', 'PBF vs Energy_p48 (% del Máximo PBF)')}")
                df_hourly_energy = gnwi.groupby(['UP', 'hour'], observed=True)[['PBF', 'Energy_p48']].sum(numeric_only=True).reset_index()
                max_pbf_values = df_hourly_energy.groupby('UP', observed=True)['PBF'].transform('max').replace(0, np.nan)
                df_norm = pd.DataFrame(index=df_hourly_energy.index)
                df_norm['PBF'] = df_hourly_energy['PBF'].div(max_pbf_values).fillna(0)
                df_norm['Energy_p48'] = df_hourly_energy['Energy_p48'].div(max_pbf_values).fillna(0)
                df_norm[['UP', 'hour']] = df_hourly_energy[['UP', 'hour']]
                df_melted = df_norm.melt(id_vars=['UP', 'hour'], value_vars=['PBF', 'Energy_p48'], var_name='Metrica', value_name='Valor (%)')
                fig_en, axes_en = plt.subplots(2, 2, figsize=(20, 14), sharex=True, sharey=True); axes_en = axes_en.flatten()
                for i, up in enumerate(UPS_INTERES):
                    ax = axes_en[i]
                    df_plot = df_melted[df_melted['UP'] == up]
                    if df_plot.empty: continue
                    sns.lineplot(data=df_plot, x='hour', y='Valor (%)', hue='Metrica', style='Metrica', markers=True, ax=ax)
                    ax.set_title(f"Evolución vs Max PBF: {up}", fontsize=14); ax.yaxis.set_major_formatter(FuncFormatter(lambda y, p: f'{y * 100:.0f}%')); ax.grid(True, alpha=0.3); ax.set_xticks(range(0, 24))
                st.pyplot(fig_en); plt.close(fig_en)
            else:
                st.info(t("Hourly charts (stack plots, lines) require Operational Mode to display.", "Los gráficos apilados y de líneas requieren el Modo Operativo (horario) para funcionar."))

    except Exception as e: st.error(f"Error Gnera: {e}")

# ==============================================================================
# SECCIÓN 5: BENEFICIO VERBUND
# ==============================================================================
elif seleccion_menu == name_verbund:
    st.markdown(f'<div class="section-title">{t("Verbund Profit (€)", "Beneficio Verbund Servicios de Ajuste (€)")}</div>', unsafe_allow_html=True)
    try:
        INPUT_DATA = {
            'FCTRAV2': ['Calatrava', 41.0, 0.5], 'EAYAMON': ['Ayamonte', 26.0, 0.5], 'EGST146': ['Barroso', 21.6, 0.5], 'PEVER': ['Sorolla 1', 182.3, 0.6], 'PEVER2': ['Sorolla Mallén', 29.8, 0.6],
            'CLIFV30': ['Pinos Puente 1', 0.0, 0.0], 'CLIFV31': ['Pinos Puente 2', 0.0, 0.0], 'CLIFV32': ['Pinos Puente 3', 0.0, 0.0], 'UPBUS': ['Buseco', 0.0, 0.0], 'UPLMP': ['Loma', 0.0, 0.0], 'UPSLN': ['La Solana', 0.0, 0.0],
            'GALPS59': ['Buseco_Galp', 0.0, 0.0], 'GALPS57': ['Loma_Galp', 0.0, 0.0], 'GALPS56': ['La Solana_Galp', 0.0, 0.0], 'CLIWI12': ['Buseco_Holaluz', 0.0, 0.0], 'CLIWI15': ['Loma_Holaluz', 0.0, 0.0], 'CLIFV20': ['La Solana_Holaluz', 0.0, 0.0],
            'EFGNRA': ['Bodenaya + Pico + Others', 0.0, 0.0]
        }
        profit_cols_v = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i']
        df_v = allh.loc[allh['UP'].isin(INPUT_DATA.keys())]
        
        df_agg_v = df_v.groupby('UP', observed=True)[[c for c in profit_cols_v if c in df_v.columns]].sum(numeric_only=True).reindex(list(INPUT_DATA.keys())).reset_index().fillna(0)
        df_agg_v['Total Profit'] = df_agg_v.iloc[:, 1:].sum(axis=1)
        df_agg_v['Verbund_Pct'] = [val[2] for val in INPUT_DATA.values()]
        df_agg_v['Profit Verbund'] = df_agg_v['Total Profit'] * df_agg_v['Verbund_Pct']
        df_agg_v['Potencia MW'] = [val[1] for val in INPUT_DATA.values()]
        df_agg_v['Profit Verbund / MW'] = np.where(df_agg_v['Potencia MW'] > 0, df_agg_v['Profit Verbund'] / df_agg_v['Potencia MW'], 0)
        
        totales = df_agg_v.select_dtypes(include=[np.number]).sum()
        totales['UP'] = 'Total'
        totales['Profit Verbund / MW'] = totales['Profit Verbund'] / totales['Potencia MW'] if totales['Potencia MW'] > 0 else 0
        df_final_v = pd.concat([df_agg_v, pd.DataFrame([totales])], ignore_index=True)
        df_final_v.insert(1, 'Installation', [val[0] for val in INPUT_DATA.values()] + ['Total'])
        
        cols_to_show = ['UP', 'Installation'] + [c for c in profit_cols_v if c in df_final_v.columns] + ['Total Profit', 'Profit Verbund', 'Profit Verbund / MW']
        st.dataframe(df_final_v[cols_to_show].style.format({c: "{:,.2f} €" for c in cols_to_show[2:]}), width='stretch')
    except Exception as e: st.warning(f"Error Verbund: {e}")

# ==============================================================================
# SECCIÓN 6: EVOLUCIÓN INGRESOS
# ==============================================================================
elif seleccion_menu == name_evo:
    st.markdown(f'<div class="section-title">{t("Revenue Evolution by Market Agent and Technology", "Evolución Ingresos por Representante y Tecnología")}</div>', unsafe_allow_html=True)
    try:
        col_e1, col_e2 = st.columns(2)
        with col_e1: ma_input = st.selectbox(t("Market Agent (MA):", "Representante (MA):"), sorted(allh['MA'].unique()), index=list(sorted(allh['MA'].unique())).index('GALP') if 'GALP' in allh['MA'].unique() else 0)
        with col_e2: tech_input = st.selectbox(t("Technology (Tech):", "Tecnología (Tech):"), sorted(allh['Tech'].unique()), index=list(sorted(allh['Tech'].unique())).index('Wind') if 'Wind' in allh['Tech'].unique() else 0)
        
        df_evo = allh.loc[(allh['MA'] == ma_input) & (allh['Tech'] == tech_input)].copy()
        
        if df_evo.empty: st.info(t("No data for this combination.", "No hay datos para esta combinación."))
        else:
            df_evo['YearMonth'] = df_evo['Day'].dt.to_period('M').astype(str)
            df_evo['Total_Profit'] = df_evo[['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']].sum(axis=1)
            df_evo_m = df_evo.groupby(['UP', 'YearMonth'], observed=True).agg(Total_Profit=('Total_Profit', 'sum'), Total_Energy=('Energy_p48', 'sum')).reset_index().sort_values('YearMonth')
            df_evo_m['Profit_per_MWh'] = df_evo_m['Total_Profit'] / df_evo_m['Total_Energy'].replace(0, np.nan)
            df_evo_m['Total_Profit_k'] = df_evo_m['Total_Profit'] / 1000

            c_evo1, c_evo2, c_evo3 = st.columns(3)
            with c_evo1:
                fig1, ax1 = plt.subplots(figsize=(6, 4))
                sns.lineplot(data=df_evo_m, x='YearMonth', y='Profit_per_MWh', hue='UP', marker='o', ax=ax1)
                ax1.set_title(t("Profit Evolution (€/MWh)", "Evolución Profit (€/MWh)"), fontsize=10); ax1.tick_params(axis='x', rotation=45); st.pyplot(fig1); plt.close(fig1)
            with c_evo2:
                fig2, ax2 = plt.subplots(figsize=(6, 4))
                sns.lineplot(data=df_evo_m, x='YearMonth', y='Total_Energy', hue='UP', marker='o', ax=ax2)
                ax2.set_title(t("Production (MWh)", "Producción (MWh)"), fontsize=10); ax2.tick_params(axis='x', rotation=45); st.pyplot(fig2); plt.close(fig2)
            with c_evo3:
                fig3, ax3 = plt.subplots(figsize=(6, 4))
                sns.lineplot(data=df_evo_m, x='YearMonth', y='Total_Profit_k', hue='UP', marker='o', ax=ax3)
                ax3.set_title(t("Total Profit (k€)", "Profit Total (k€)"), fontsize=10); ax3.tick_params(axis='x', rotation=45); st.pyplot(fig3); plt.close(fig3)
    except Exception as e: st.warning(f"Error Evolución: {e}")
