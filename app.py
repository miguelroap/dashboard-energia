# -*- coding: utf-8 -*-
"""
Created on Thu Mar 19 17:14:27 2026

@author: ROAPRIEM
"""

# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
from google.cloud import bigquery
from google.oauth2 import service_account
import json

# --- 1. CONFIGURACIÓN PÁGINA STREAMLIT ---
st.set_page_config(page_title="Dashboard Ancillary Services", layout="wide")
st.title("📊 Análisis de Desempeño: Mercados de Ajuste e Intradiarios")

# --- 2. CARGA DE DATOS (CON CACHÉ PARA MAYOR VELOCIDAD) ---
@st.cache_data
def load_allh_data():
    # Carga los datos procesados localmente y subidos al repo
    return pd.read_parquet('allh_dashboard.parquet')

@st.cache_data
def load_power_data():
    # Lógica para leer desde Google Cloud BigQuery
    PROJECT_ID = 'veb-dev-renewables-spain-ijb'
    DATASET_ID = 'red_electrica_data'
    
    # Autenticación: Streamlit Cloud usará st.secrets, en local usará tus credenciales por defecto
    try:
        if "gcp_service_account" in st.secrets:
            credentials = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
            client = bigquery.Client(credentials=credentials, project=PROJECT_ID)
        else:
            client = bigquery.Client(project=PROJECT_ID)
            
        sql = f"SELECT UP, Power_MW as `Power MW` FROM `{PROJECT_ID}.{DATASET_ID}.programming_units_external_table_latest`"
        df_power = client.query(sql).to_dataframe()
        
        df_power['Power MW'] = pd.to_numeric(df_power['Power MW'], errors='coerce').replace(0, np.nan)
        df_power = df_power.dropna(subset=['Power MW', 'UP'])
        return df_power
    except Exception as e:
        st.error(f"Error cargando datos de BigQuery: {e}")
        return pd.DataFrame(columns=['UP', 'Power MW'])

# Cargar los datos
allh = load_allh_data()
df_power = load_power_data()

# --- 3. BARRA LATERAL (FILTROS INTERACTIVOS) ---
st.sidebar.header("Filtros de Análisis")

# Selección de mercado
aass_sel = st.sidebar.radio(
    "Selección de Mercados (Profit Base)",
    options=['no_sec', 'sec', 'all'],
    format_func=lambda x: "Sin Secundaria" if x == 'no_sec' else ("Solo Secundaria" if x == 'sec' else "Todos")
)

# Selección de UPs a resaltar
todas_las_ups = sorted(allh['UP'].unique().tolist())
ups_to_highlight = st.sidebar.multiselect(
    "UPs a Resaltar (Color Rojo)",
    options=todas_las_ups,
    default=['PEVER', 'EGST146'] if 'PEVER' in todas_las_ups else []
)

# MAs excluidos
excluded_MAs = ["ENDESA", "IBERDROLA", "EDP", "NATURGY", "HOLALUZ", "ALDROENERGIA Y SOLUCIONES SL"]
Energy_ref = 'Energy_p48'

# --- 4. PROCESAMIENTO DE DATOS ---
if aass_sel == 'no_sec':
    available_profit_cols = [c for c in ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr'] if c in allh.columns]
elif aass_sel == 'sec':
    available_profit_cols = [c for c in ['Profit_b', 'Profit_se'] if c in allh.columns]
else:
    available_profit_cols = [c for c in ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se'] if c in allh.columns]

# Filtrar y preparar DB
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

db['Day'] = pd.to_datetime(db['Day'])
db['Month'] = db['Day'].dt.to_period('M')

if Energy_ref in db.columns and db[Energy_ref].dtype == 'object':
     db[Energy_ref] = pd.to_numeric(db[Energy_ref].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

# Agrupación Mensual
monthly_grouped = db.groupby(['UP', 'Tech', 'MA', 'Month']).agg(
    Monthly_Profit=pd.NamedAgg(column='Total_Profit', aggfunc='sum'),
    Monthly_Energy=pd.NamedAgg(column=Energy_ref, aggfunc='sum')
).reset_index()

# Cruce con Potencia de BQ
monthly_grouped = pd.merge(monthly_grouped, df_power, on='UP', how='left')
monthly_grouped['Monthly_Profit_per_MW'] = monthly_grouped['Monthly_Profit'].div(monthly_grouped['Power MW']).fillna(0)

# Promedios
grouped = monthly_grouped.groupby(['UP', 'Tech', 'MA']).agg(
    Profit_per_MW = pd.NamedAgg(column='Monthly_Profit_per_MW', aggfunc='mean'),
    Total_Energy = pd.NamedAgg(column='Monthly_Energy', aggfunc='sum')
).reset_index()

# Textos para gráficos
start_date = db['Day'].min().strftime('%Y-%m-%d')
end_date = db['Day'].max().strftime('%Y-%m-%d')
period_text = f'since {start_date} to {end_date}'

# --- 5. RENDERIZADO DE GRÁFICOS ---
st.write("---")
st.subheader("1. Dispersión General (Eólica y Solar)")
filtered_data = grouped[grouped['Tech'].isin(['Solar PV', 'Wind'])].copy()
filtered_data['is_Highlighted'] = filtered_data['UP'].isin(ups_to_highlight)
filtered_data.sort_values('MA', inplace=True)

col1, col2 = st.columns(2)

with col1:
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=filtered_data, x='MA', y='Profit_per_MW', hue='Tech', size='Total_Energy', sizes=(40, 400), alpha=0.7, palette='muted', edgecolor='black', ax=ax1)
    sns.scatterplot(data=filtered_data[filtered_data['is_Highlighted']], x='MA', y='Profit_per_MW', color='red', s=70, edgecolor='black', marker='o', zorder=10, legend=False, ax=ax1)
    ax1.set_title(f'Avg. Monthly Profit in €/MW\n{period_text}')
    ax1.set_ylabel('€ / MW / Month')
    ax1.tick_params(axis='x', rotation=45)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.axhline(0, color='grey', linestyle='--')
    st.pyplot(fig1)

with col2:
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    sns.boxplot(data=filtered_data, x='MA', y='Profit_per_MW', hue='Tech', showfliers=False, palette='muted', ax=ax2)
    sns.stripplot(data=filtered_data[filtered_data['is_Highlighted']], x='MA', y='Profit_per_MW', hue='Tech', size=8, color='red', edgecolor='black', dodge=True, legend=False, ax=ax2)
    ax2.set_title(f'Boxplot: Avg. Monthly Profit (€/MW)\n{period_text}')
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
        st.info("Sin datos de Solar PV")

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
        st.info("Sin datos de Wind")

st.write("---")
st.subheader("3. Mapa de Calor (Heatmap) Agregado")
ma_tech_summary = grouped.groupby(['MA', 'Tech']).agg(Avg_Monthly_Profit_per_MW=('Profit_per_MW', 'mean')).reset_index()
try:
    heatmap_data = ma_tech_summary.pivot(index='MA', columns='Tech', values='Avg_Monthly_Profit_per_MW').fillna(0).sort_index()
    if all(col in heatmap_data.columns for col in ['Wind', 'Solar PV']):
         heatmap_data = heatmap_data[['Wind', 'Solar PV']]
         
    fig5, ax5 = plt.subplots(figsize=(10, max(6, len(heatmap_data) * 0.4)))
    sns.heatmap(heatmap_data, annot=True, fmt=',.2f', cmap='vlag', center=0, linewidths=.5, ax=ax5)
    ax5.set_title(f'Average Monthly Profit per MW (€/MW/Month)\n{period_text}')
    st.pyplot(fig5)
except Exception as e:
    st.error("No se pudo generar el Heatmap por falta de cruces MA/Tech.")