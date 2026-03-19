# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

# --- 1. CONFIGURACIÓN PÁGINA STREAMLIT ---
st.set_page_config(page_title="Dashboard Ancillary Services", layout="wide")
st.title("📊 Análisis de Desempeño: Mercados de Ajuste e Intradiarios")

# --- 2. CARGA DE DATOS (CON CACHÉ PARA MAYOR VELOCIDAD) ---
@st.cache_data
def load_allh_data():
    try:
        df1 = pd.read_parquet('allh_part1.parquet')
        df2 = pd.read_parquet('allh_part2.parquet')
        return pd.concat([df1, df2], ignore_index=True)
    except Exception as e:
        st.error(f"Error cargando las partes del archivo allh: {e}")
        return pd.DataFrame()

@st.cache_data
def load_power_data():
    try:
        df_power = pd.read_parquet('ups_dashboard.parquet', columns=['UP', 'Power MW'])
        df_power['Power MW'] = pd.to_numeric(df_power['Power MW'], errors='coerce').replace(0, np.nan)
        df_power = df_power.dropna(subset=['Power MW', 'UP'])
        return df_power
    except Exception as e:
        st.error(f"Error cargando datos de potencia (ups_dashboard.parquet): {e}")
        return pd.DataFrame(columns=['UP', 'Power MW'])

# Cargar los datos a la memoria RAM de la web
allh = load_allh_data()
df_power = load_power_data()

# Asegurarnos de que 'Day' es formato fecha
allh['Day'] = pd.to_datetime(allh['Day'])

# --- 3. BARRA LATERAL (FILTROS INTERACTIVOS) ---

# --- A. Filtro de Fechas ---
st.sidebar.header("📅 Rango de Fechas")
min_date = allh['Day'].min().date()
max_date = allh['Day'].max().date()

selected_dates = st.sidebar.date_input(
    "Selecciona el periodo a analizar:",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Controlar que se hayan seleccionado fecha de inicio y fin
if len(selected_dates) == 2:
    start_date, end_date = selected_dates
else:
    start_date, end_date = min_date, max_date

# Aplicar el filtro de fechas al dataset
allh = allh[(allh['Day'].dt.date >= start_date) & (allh['Day'].dt.date <= end_date)]

# Mostrar el periodo seleccionado claramente arriba
st.markdown(f"<h3 style='text-align: center; color: #4c72b0; background-color: #f0f2f6; padding: 10px; border-radius: 10px;'>"
            f"📅 Periodo de Análisis: <b>{start_date.strftime('%d/%m/%Y')}</b> al <b>{end_date.strftime('%d/%m/%Y')}</b></h3>", 
            unsafe_allow_html=True)
st.markdown("---")

# --- B. Filtro de Instalaciones (UPs personalizadas) ---
st.sidebar.header("🏭 Instalaciones de Interés")

ups_interes = [
    'CLIFV30', 'CLIFV31', 'CLIFV32', 'UPBUS', 'UPLMP', 'UPSLN', 
    'GALPS59', 'GALPS57', 'GALPS56', 'FCTRAV2', 'EFGNRA', 'PEVER', 'PEVER2', 'EAYAMON', 'EGST146'
]

installation = [
    'Pinos Puente 1', 'Pinos Puente 2', 'Pinos Puente 3', 'Buseco', 'Loma', 'La Solana', 
    'Buseco_Galp', 'Loma_Galp', 'La Solana_Galp', 'Calatrava', 'Bodenaya + Pico + Others', 'Sorolla 1', 'Mallen', 'Ayamonte', 'Barroso'
]

# Diccionario rápido para saber qué MA tiene cada UP (evitando fallos si alguna UP no actuó ese mes)
ma_mapping = allh[['UP', 'MA']].dropna().drop_duplicates(subset=['UP']).set_index('UP')['MA'].to_dict()

selected_ups = []

# Crear las casillas de verificación en la barra lateral
for up, inst in zip(ups_interes, installation):
    ma_name = ma_mapping.get(up, "MA Desconocido")
    display_name = f"{inst} ({ma_name})"
    
    # Creamos un checkbox por cada planta. Value=True significa que nacen marcados por defecto.
    if st.sidebar.checkbox(display_name, value=True):
        selected_ups.append(up)

# Comprobar si no hay nada seleccionado
if not selected_ups:
    st.warning("⚠️ Selecciona al menos una instalación en el menú izquierdo para visualizar los gráficos.")
    st.stop()

# ¡APLICAMOS EL FILTRO! Nos quedamos solo con las UPs que estén marcadas
allh = allh[allh['UP'].isin(selected_ups)]


# --- C. Filtros Adicionales ---
st.sidebar.header("⚙️ Configuración Adicional")
aass_sel = st.sidebar.radio(
    "Selección de Mercados (Profit Base)",
    options=['no_sec', 'sec', 'all'],
    format_func=lambda x: "Sin Secundaria" if x == 'no_sec' else ("Solo Secundaria" if x == 'sec' else "Todos")
)

# Selección de UPs a resaltar en rojo (solo permite elegir de entre las que están marcadas arriba)
ups_to_highlight = st.sidebar.multiselect(
    "🔴 UPs a Resaltar (Puntos Rojos)",
    options=selected_ups,
    default=[up for up in ['PEVER', 'EGST146'] if up in selected_ups]
)


# --- 4. PROCESAMIENTO DE DATOS ---
excluded_MAs = ["ENDESA", "IBERDROLA", "EDP", "NATURGY", "HOLALUZ", "ALDROENERGIA Y SOLUCIONES SL"]
Energy_ref = 'Energy_p48'

if aass_sel == 'no_sec':
    available_profit_cols = [c for c in ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr'] if c in allh.columns]
elif aass_sel == 'sec':
    available_profit_cols = [c for c in ['Profit_b', 'Profit_se'] if c in allh.columns]
else:
    available_profit_cols = [c for c in ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se'] if c in allh.columns]

# Variables de rentabilidad
query_cols = [c for c in ['Profit_rt', 'Profit_b'] if c in allh.columns]
if query_cols:
    for col in query_cols:
        if allh[col].dtype == 'object':
             allh[col] = pd.to_numeric(allh[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    query_string = " or ".join([f"`{col}` != 0" for col in query_cols])
    rrtt_up = allh.query(query_string)
else:
    rrtt_up = allh.copy()

rrtt_up_l = rrtt_up[rrtt_up['MA'] != 0]['UP'].unique().tolist()
db = allh[allh['UP'].isin(rrtt_up_l)].copy()

for col in available_profit_cols:
     if col in db.columns and db[col].dtype == 'object':
       db[col] = pd.to_numeric(db[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

db['Total_Profit'] = db[available_profit_cols].sum(axis=1) if available_profit_cols else 0
db = db[~db['MA'].isin(excluded_MAs)]

db['Month'] = db['Day'].dt.to_period('M')

if Energy_ref in db.columns and db[Energy_ref].dtype == 'object':
     db[Energy_ref] = pd.to_numeric(db[Energy_ref].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

# Agrupación Mensual
monthly_grouped = db.groupby(['UP', 'Tech', 'MA', 'Month']).agg(
    Monthly_Profit=pd.NamedAgg(column='Total_Profit', aggfunc='sum'),
    Monthly_Energy=pd.NamedAgg(column=Energy_ref, aggfunc='sum')
).reset_index()

# Cruce con Potencia del Parquet
monthly_grouped = pd.merge(monthly_grouped, df_power, on='UP', how='left')
monthly_grouped['Monthly_Profit_per_MW'] = monthly_grouped['Monthly_Profit'].div(monthly_grouped['Power MW']).fillna(0)

# Promedios de la métrica por UP, Tech y MA
grouped = monthly_grouped.groupby(['UP', 'Tech', 'MA']).agg(
    Profit_per_MW = pd.NamedAgg(column='Monthly_Profit_per_MW', aggfunc='mean'),
    Total_Energy = pd.NamedAgg(column='Monthly_Energy', aggfunc='sum')
).reset_index()


# --- 5. RENDERIZADO DE GRÁFICOS ---
st.subheader("1. Dispersión General (Eólica y Solar)")
filtered_data = grouped[grouped['Tech'].isin(['Solar PV', 'Wind'])].copy()
filtered_data['is_Highlighted'] = filtered_data['UP'].isin(ups_to_highlight)
filtered_data.sort_values('MA', inplace=True)

col1, col2 = st.columns(2)

with col1:
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=filtered_data, x='MA', y='Profit_per_MW', hue='Tech', size='Total_Energy', sizes=(40, 400), alpha=0.7, palette='muted', edgecolor='black', ax=ax1)
    sns.scatterplot(data=filtered_data[filtered_data['is_Highlighted']], x='MA', y='Profit_per_MW', color='red', s=70, edgecolor='black', marker='o', zorder=10, legend=False, ax=ax1)
    ax1.set_title(f'Avg. Monthly Profit in €/MW')
    ax1.set_ylabel('€ / MW / Month')
    ax1.tick_params(axis='x', rotation=45)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.axhline(0, color='grey', linestyle='--')
    st.pyplot(fig1)

with col2:
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    sns.boxplot(data=filtered_data, x='MA', y='Profit_per_MW', hue='Tech', showfliers=False, palette='muted', ax=ax2)
    sns.stripplot(data=filtered_data[filtered_data['is_Highlighted']], x='MA', y='Profit_per_MW', hue='Tech', size=8, color='red', edgecolor='black', dodge=True, legend=False, ax=ax2)
    ax2.set_title(f'Boxplot: Avg. Monthly Profit (€/MW)')
    ax2.set_ylabel('€ / MW / Month')
    ax2.tick_params(axis='x', rotation=45)
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.axhline(0, color='grey', linestyle='--')
    st.pyplot(fig2)

st.write("---")
st.subheader("2. Detalle por Tecnología")
col3, col4 = st.columns(2)

with col3:
    # Solar PV
    solar_pv_data = grouped[grouped['Tech'] == 'Solar PV'].copy()
    solar_pv_data['is_Highlighted'] = solar_pv_data['UP'].isin(ups_to_highlight)
    ma_order_solar = solar_pv_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
    
    if len(ma_order_solar) > 0:
        fig3, ax3 = plt.subplots(figsize=(10, 6))
        sns.boxplot(data=solar_pv_data, x='MA', y='Profit_per_MW', showfliers=False, color='orange', order=ma_order_solar, ax=ax3)
        sns.stripplot(data=solar_pv_data[solar_pv_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=8, color='red', edgecolor='black', order=ma_order_solar, ax=ax3)
        ax3.set_title('SOLAR PV: Boxplot ordered by Avg Profit')
        ax3.tick_params(axis='x', rotation=45)
        ax3.axhline(0, color='grey', linestyle='--')
        st.pyplot(fig3)
    else:
        st.info("Sin datos de Solar PV para las instalaciones seleccionadas")

with col4:
    # Wind
    wind_data = grouped[grouped['Tech'] == 'Wind'].copy()
    wind_data['is_Highlighted'] = wind_data['UP'].isin(ups_to_highlight)
    ma_order_wind = wind_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
    
    if len(ma_order_wind) > 0:
        fig4, ax4 = plt.subplots(figsize=(10, 6))
        sns.boxplot(data=wind_data, x='MA', y='Profit_per_MW', showfliers=False, color='lightgreen', order=ma_order_wind, ax=ax4)
        sns.stripplot(data=wind_data[wind_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=8, color='red', edgecolor='black', order=ma_order_wind, ax=ax4)
        ax4.set_title('WIND: Boxplot ordered by Avg Profit')
        ax4.tick_params(axis='x', rotation=45)
        ax4.axhline(0, color='grey', linestyle='--')
        st.pyplot(fig4)
    else:
        st.info("Sin datos de Wind para las instalaciones seleccionadas")

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
    st.error("Selecciona al menos dos combinaciones MA/Tech diferentes para poder generar el Heatmap.")