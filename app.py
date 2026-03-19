# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq
import gc

# --- 1. CONFIGURACIÓN PÁGINA STREAMLIT ---
st.set_page_config(page_title="Dashboard Ancillary Services", layout="wide")

# --- 2. SISTEMA DE CONTRASEÑA SEGURO ---
def check_password():
    try:
        app_pass = st.secrets["app_password"]
    except Exception:
        st.warning("⚠️ Modo Desarrollo: No se ha configurado 'app_password' en st.secrets. Acceso permitido.")
        return True

    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("<h1 style='text-align: center;'>🔒 Acceso Restringido</h1>", unsafe_allow_html=True)
        st.text_input("🔑 Introduce la contraseña:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("<h1 style='text-align: center;'>🔒 Acceso Restringido</h1>", unsafe_allow_html=True)
        st.text_input("🔑 Introduce la contraseña:", type="password", on_change=password_entered, key="password")
        st.error("😕 Contraseña incorrecta. Inténtalo de nuevo.")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ==========================================
# A PARTIR DE AQUÍ VA LA APLICACIÓN
# ==========================================
st.title("📊 Análisis de Desempeño: Mercados de Ajuste e Intradiarios")

# --- 3. CARGA DE DATOS OPTIMIZADA EN RAM (PRUEBA SOLO PARTE 1) ---
@st.cache_data
def load_allh_data():
    try:
        import pyarrow.parquet as pq
        
        # Analizamos qué columnas tiene el archivo realmente
        schema = pq.read_schema('allh_part1.parquet')
        
        # DEFINIMOS SOLO LAS COLUMNAS QUE USA EL DASHBOARD
        columnas_necesarias = ['UP', 'MA', 'Tech', 'Day', 'Energy_p48', 
                               'Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']
        
        cols_to_load = [c for c in columnas_necesarias if c in schema.names]
        
        # LEEMOS Y DEVOLVEMOS EXCLUSIVAMENTE LA PARTE 1
        df1 = pd.read_parquet('allh_part1.parquet', columns=cols_to_load)
        
        return df1
    except Exception as e:
        return str(e)

@st.cache_data
def load_power_data():
    try:
        df_power = pd.read_parquet('ups_dashboard.parquet', columns=['UP', 'Power MW'])
        df_power['Power MW'] = pd.to_numeric(df_power['Power MW'], errors='coerce').replace(0, np.nan)
        return df_power.dropna(subset=['Power MW', 'UP'])
    except Exception as e:
        return str(e)

# Cargar datos
allh = load_allh_data()
df_power = load_power_data()

if isinstance(allh, str):
    st.error(f"❌ Error al cargar los archivos 'allh'. Detalles: {allh}")
    st.stop()
if isinstance(df_power, str):
    st.error(f"❌ Error al cargar 'ups_dashboard.parquet'. Detalles: {df_power}")
    st.stop()
if allh.empty:
    st.error("❌ Los archivos de datos están vacíos.")
    st.stop()


# --- 4. BARRA LATERAL (FILTROS DE FECHAS) ---
allh['Day'] = pd.to_datetime(allh['Day'])
min_date = allh['Day'].min().date()
max_date = allh['Day'].max().date()

st.sidebar.header("📅 Rango de Fechas")
selected_dates = st.sidebar.date_input(
    "Selecciona el periodo a analizar:",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

if len(selected_dates) == 2:
    start_date, end_date = selected_dates
else:
    start_date, end_date = min_date, max_date

# Recortar el dataset al periodo seleccionado
allh = allh[(allh['Day'].dt.date >= start_date) & (allh['Day'].dt.date <= end_date)]

# Liberar memoria forzosamente tras el recorte
gc.collect()

if allh.empty:
    st.warning("⚠️ No hay datos para el periodo de fechas seleccionado.")
    st.stop()

# Título de fechas
st.markdown(f"<h3 style='text-align: center; color: #4c72b0; background-color: #f0f2f6; padding: 10px; border-radius: 10px;'>"
            f"📅 Periodo de Análisis: <b>{start_date.strftime('%d/%m/%Y')}</b> al <b>{end_date.strftime('%d/%m/%Y')}</b></h3>", 
            unsafe_allow_html=True)
st.markdown("---")


# --- 5. BARRA LATERAL (FILTRO DE INSTALACIONES PARA RESALTAR) ---
st.sidebar.header("🔴 Instalaciones a Resaltar")
st.sidebar.markdown("Selecciona las UPs que quieres ver marcadas en rojo sobre el resto:")

ups_interes = [
    'CLIFV30', 'CLIFV31', 'CLIFV32', 'UPBUS', 'UPLMP', 'UPSLN', 
    'GALPS59', 'GALPS57', 'GALPS56', 'FCTRAV2', 'EFGNRA', 'PEVER', 'PEVER2', 'EAYAMON', 'EGST146'
]
installation = [
    'Pinos Puente 1', 'Pinos Puente 2', 'Pinos Puente 3', 'Buseco', 'Loma', 'La Solana', 
    'Buseco_Galp', 'Loma_Galp', 'La Solana_Galp', 'Calatrava', 'Bodenaya + Pico + Others', 'Sorolla 1', 'Mallen', 'Ayamonte', 'Barroso'
]

# Mapa rápido para saber qué MA gestiona cada planta
ma_mapping = allh[['UP', 'MA']].dropna().drop_duplicates(subset=['UP']).set_index('UP')['MA'].to_dict()

selected_ups = []
for up, inst in zip(ups_interes, installation):
    ma_name = ma_mapping.get(up, "Desconocido")
    display_name = f"{inst} ({ma_name})"
    default_val = True if up in ['PEVER', 'EGST146'] else False
    if st.sidebar.checkbox(display_name, value=default_val):
        selected_ups.append(up)


# --- 6. BARRA LATERAL (AJUSTES) ---
st.sidebar.header("⚙️ Configuración de Mercados")
aass_sel = st.sidebar.radio(
    "Profit Base",
    options=['no_sec', 'sec', 'all'],
    format_func=lambda x: "Sin Secundaria" if x == 'no_sec' else ("Solo Secundaria" if x == 'sec' else "Todos")
)


# --- 7. PROCESAMIENTO MATEMÁTICO ---
excluded_MAs = ["ENDESA", "IBERDROLA", "EDP", "NATURGY", "HOLALUZ", "ALDROENERGIA Y SOLUCIONES SL"]
Energy_ref = 'Energy_p48'

if aass_sel == 'no_sec':
    available_profit_cols = [c for c in ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr'] if c in allh.columns]
elif aass_sel == 'sec':
    available_profit_cols = [c for c in ['Profit_b', 'Profit_se'] if c in allh.columns]
else:
    available_profit_cols = [c for c in ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se'] if c in allh.columns]

query_cols = [c for c in ['Profit_rt', 'Profit_b'] if c in allh.columns]
if query_cols:
    query_string = " or ".join([f"`{col}` != 0" for col in query_cols])
    rrtt_up = allh.query(query_string)
else:
    rrtt_up = allh.copy()

rrtt_up_l = rrtt_up[rrtt_up['MA'] != 'Desconocido']['UP'].unique().tolist()
db = allh[allh['UP'].isin(rrtt_up_l)].copy()

# Liberamos memoria de nuevo
del allh
gc.collect()

db['Total_Profit'] = db[available_profit_cols].sum(axis=1) if available_profit_cols else 0
db = db[~db['MA'].isin(excluded_MAs)]

db['Month'] = db['Day'].dt.to_period('M')

# Agrupación y Promedios
monthly_grouped = db.groupby(['UP', 'Tech', 'MA', 'Month']).agg(
    Monthly_Profit=pd.NamedAgg(column='Total_Profit', aggfunc='sum'),
    Monthly_Energy=pd.NamedAgg(column=Energy_ref, aggfunc='sum')
).reset_index()

monthly_grouped = pd.merge(monthly_grouped, df_power, on='UP', how='left')
monthly_grouped['Monthly_Profit_per_MW'] = monthly_grouped['Monthly_Profit'].div(monthly_grouped['Power MW']).fillna(0)

grouped = monthly_grouped.groupby(['UP', 'Tech', 'MA']).agg(
    Profit_per_MW = pd.NamedAgg(column='Monthly_Profit_per_MW', aggfunc='mean'),
    Total_Energy = pd.NamedAgg(column='Monthly_Energy', aggfunc='sum')
).reset_index()

grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)
period_text = f'since {start_date.strftime("%Y-%m-%d")} to {end_date.strftime("%Y-%m-%d")}'


# --- 8. RENDERIZADO DE GRÁFICOS ---
st.subheader("1. Dispersión General (Eólica y Solar)")
filtered_data = grouped[grouped['Tech'].isin(['Solar PV', 'Wind'])].copy()
filtered_data.sort_values('MA', inplace=True)

# Paleta roja limpia para evitar FutureWarnings de Seaborn
red_palette = sns.color_palette(['red', 'red', 'red'])

col1, col2 = st.columns(2)

with col1:
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=filtered_data, x='MA', y='Profit_per_MW', hue='Tech', size='Total_Energy', sizes=(40, 400), alpha=0.7, palette='muted', edgecolor='black', ax=ax1)
    
    highlight_data = filtered_data[filtered_data['is_Highlighted']]
    if not highlight_data.empty:
        sns.scatterplot(data=highlight_data, x='MA', y='Profit_per_MW', color='red', s=70, edgecolor='black', marker='o', zorder=10, legend=False, ax=ax1)
        
    ax1.set_title("Avg. Monthly Profit in €/MW")
    ax1.set_ylabel('€ / MW / Month')
    ax1.tick_params(axis='x', rotation=45)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.axhline(0, color='grey', linestyle='--')
    st.pyplot(fig1)

with col2:
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    sns.boxplot(data=filtered_data, x='MA', y='Profit_per_MW', hue='Tech', showfliers=False, palette='muted', ax=ax2)
    
    if not highlight_data.empty:
        sns.stripplot(data=highlight_data, x='MA', y='Profit_per_MW', hue='Tech', size=8, palette=red_palette, edgecolor='black', dodge=True, legend=False, ax=ax2)
        
    ax2.set_title("Boxplot: Avg. Monthly Profit (€/MW)")
    ax2.set_ylabel('€ / MW / Month')
    ax2.tick_params(axis='x', rotation=45)
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.axhline(0, color='grey', linestyle='--')
    st.pyplot(fig2)

st.write("---")
st.subheader("2. Detalle por Tecnología")
col3, col4 = st.columns(2)

with col3:
    solar_pv_data = grouped[grouped['Tech'] == 'Solar PV'].copy()
    ma_order_solar = solar_pv_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
    
    if len(ma_order_solar) > 0:
        fig3, ax3 = plt.subplots(figsize=(10, 6))
        sns.boxplot(data=solar_pv_data, x='MA', y='Profit_per_MW', showfliers=False, color='orange', order=ma_order_solar, ax=ax3)
        
        highlight_solar = solar_pv_data[solar_pv_data['is_Highlighted']]
        if not highlight_solar.empty:
            sns.stripplot(data=highlight_solar, x='MA', y='Profit_per_MW', size=8, color='red', edgecolor='black', order=ma_order_solar, ax=ax3)
            
        ax3.set_title('SOLAR PV: Boxplot ordered by Avg Profit')
        ax3.tick_params(axis='x', rotation=45)
        ax3.axhline(0, color='grey', linestyle='--')
        st.pyplot(fig3)
    else:
        st.info("Sin datos de Solar PV para el periodo seleccionado.")

with col4:
    wind_data = grouped[grouped['Tech'] == 'Wind'].copy()
    ma_order_wind = wind_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
    
    if len(ma_order_wind) > 0:
        fig4, ax4 = plt.subplots(figsize=(10, 6))
        sns.boxplot(data=wind_data, x='MA', y='Profit_per_MW', showfliers=False, color='lightgreen', order=ma_order_wind, ax=ax4)
        
        highlight_wind = wind_data[wind_data['is_Highlighted']]
        if not highlight_wind.empty:
            sns.stripplot(data=highlight_wind, x='MA', y='Profit_per_MW', size=8, color='red', edgecolor='black', order=ma_order_wind, ax=ax4)
            
        ax4.set_title('WIND: Boxplot ordered by Avg Profit')
        ax4.tick_params(axis='x', rotation=45)
        ax4.axhline(0, color='grey', linestyle='--')
        st.pyplot(fig4)
    else:
        st.info("Sin datos de Wind para el periodo seleccionado.")

st.write("---")
st.subheader("3. Mapa de Calor (Heatmap) Agregado")
ma_tech_summary = grouped.groupby(['MA', 'Tech']).agg(Avg_Monthly_Profit_per_MW=('Profit_per_MW', 'mean')).reset_index()

try:
    heatmap_data = ma_tech_summary.pivot(index='MA', columns='Tech', values='Avg_Monthly_Profit_per_MW').fillna(0).sort_index()
    if all(col in heatmap_data.columns for col in ['Wind', 'Solar PV']):
         heatmap_data = heatmap_data[['Wind', 'Solar PV']]
         
    fig5, ax5 = plt.subplots(figsize=(10, max(6, len(heatmap_data) * 0.4)))
    sns.heatmap(heatmap_data, annot=True, fmt=',.2f', cmap='vlag', center=0, linewidths=.5, ax=ax5)
    ax5.set_title(f'Average Monthly Profit per MW (€/MW/Month)')
    st.pyplot(fig5)
except Exception as e:
    st.error("No hay cruces suficientes de MA/Tech en este periodo para generar el Heatmap.")
