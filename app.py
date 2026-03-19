# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

st.set_page_config(page_title="Dashboard Ancillary Services", layout="wide")

# --- SISTEMA DE CONTRASEÑA ---
def check_password():
    try:
        app_pass = st.secrets["app_password"]
    except Exception:
        return True # Si no hay contraseña configurada, deja pasar
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
        st.error("😕 Contraseña incorrecta.")
        return False
    else:
        return True

if not check_password():
    st.stop()

st.title("📊 Análisis de Desempeño: Mercados de Ajuste e Intradiarios")

# --- CARGA DE DATOS ULTRALIGERA ---
@st.cache_data
def load_allh_data():
    try:
        return pd.read_parquet('allh_dashboard_daily.parquet')
    except Exception as e:
        return str(e)

@st.cache_data
def load_power_data():
    try:
        df = pd.read_parquet('ups_dashboard.parquet', columns=['UP', 'Power MW'])
        df['Power MW'] = pd.to_numeric(df['Power MW'], errors='coerce')
        return df.dropna(subset=['Power MW', 'UP'])
    except Exception as e:
        return str(e)

allh = load_allh_data()
df_power = load_power_data()

if isinstance(allh, str) or allh.empty:
    st.error(f"Error cargando datos: {allh}")
    st.stop()

allh['Day'] = pd.to_datetime(allh['Day'])

# --- BARRA LATERAL ---
min_date, max_date = allh['Day'].min().date(), allh['Day'].max().date()
st.sidebar.header("📅 Rango de Fechas")
selected_dates = st.sidebar.date_input("Periodo:", value=(min_date, max_date), min_value=min_date, max_value=max_date)

start_date, end_date = selected_dates if len(selected_dates) == 2 else (min_date, max_date)
allh = allh[(allh['Day'].dt.date >= start_date) & (allh['Day'].dt.date <= end_date)]

st.markdown(f"<h3 style='text-align: center; color: #4c72b0; background-color: #f0f2f6; padding: 10px; border-radius: 10px;'>"
            f"📅 Periodo de Análisis: <b>{start_date.strftime('%d/%m/%Y')}</b> al <b>{end_date.strftime('%d/%m/%Y')}</b></h3>", 
            unsafe_allow_html=True)
st.markdown("---")

st.sidebar.header("🔴 Instalaciones a Resaltar")
ups_interes = ['CLIFV30', 'CLIFV31', 'CLIFV32', 'UPBUS', 'UPLMP', 'UPSLN', 'GALPS59', 'GALPS57', 'GALPS56', 'FCTRAV2', 'EFGNRA', 'PEVER', 'PEVER2', 'EAYAMON', 'EGST146']
installation = ['Pinos Puente 1', 'Pinos Puente 2', 'Pinos Puente 3', 'Buseco', 'Loma', 'La Solana', 'Buseco_Galp', 'Loma_Galp', 'La Solana_Galp', 'Calatrava', 'Bodenaya + Pico + Others', 'Sorolla 1', 'Mallen', 'Ayamonte', 'Barroso']

ma_mapping = allh[['UP', 'MA']].dropna().drop_duplicates(subset=['UP']).set_index('UP')['MA'].to_dict()
selected_ups = [up for up, inst in zip(ups_interes, installation) 
                if st.sidebar.checkbox(f"{inst} ({ma_mapping.get(up, 'Desc')})", value=(up in ['PEVER', 'EGST146']))]

st.sidebar.header("⚙️ Configuración")
aass_sel = st.sidebar.radio("Profit Base", options=['no_sec', 'sec', 'all'], format_func=lambda x: "Sin Secundaria" if x == 'no_sec' else ("Solo Secundaria" if x == 'sec' else "Todos"))

# --- PROCESAMIENTO ---
if aass_sel == 'no_sec': cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr']
elif aass_sel == 'sec': cols_sel = ['Profit_b', 'Profit_se']
else: cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']
available_cols = [c for c in cols_sel if c in allh.columns]

# Filtro UP activas
q_cols = [c for c in ['Profit_rt', 'Profit_b'] if c in allh.columns]
if q_cols:
    query = " or ".join([f"`{c}` != 0" for c in q_cols])
    active_ups = allh.query(query)['UP'].unique()
    allh = allh[allh['UP'].isin(active_ups)]

allh = allh[~allh['MA'].isin(["ENDESA", "IBERDROLA", "EDP", "NATURGY", "HOLALUZ", "ALDROENERGIA Y SOLUCIONES SL"])]
allh['Total_Profit'] = allh[available_cols].sum(axis=1) if available_cols else 0
allh['Month'] = allh['Day'].dt.to_period('M')

# Agrupar a Nivel Mensual y Cruzar Potencia
monthly = allh.groupby(['UP', 'Tech', 'MA', 'Month']).agg(
    Monthly_Profit=('Total_Profit', 'sum'),
    Monthly_Energy=('Energy_p48', 'sum') if 'Energy_p48' in allh.columns else ('Total_Profit', 'count')
).reset_index()

monthly = pd.merge(monthly, df_power, on='UP', how='left')
monthly['Profit_per_MW'] = (monthly['Monthly_Profit'] / monthly['Power MW']).fillna(0)

# Promedio Final
grouped = monthly.groupby(['UP', 'Tech', 'MA']).agg(Profit_per_MW=('Profit_per_MW', 'mean'), Total_Energy=('Monthly_Energy', 'sum')).reset_index()
grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)

# --- GRÁFICOS ---
red_palette = sns.color_palette(['red', 'red', 'red'])

st.subheader("1. Dispersión General (Eólica y Solar)")
f_data = grouped[grouped['Tech'].isin(['Solar PV', 'Wind'])].sort_values('MA')
c1, c2 = st.columns(2)
with c1:
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=f_data, x='MA', y='Profit_per_MW', hue='Tech', size='Total_Energy', sizes=(40, 400), alpha=0.7, ax=ax)
    if not f_data[f_data['is_Highlighted']].empty:
        sns.scatterplot(data=f_data[f_data['is_Highlighted']], x='MA', y='Profit_per_MW', color='red', s=70, edgecolor='black', zorder=10, legend=False, ax=ax)
    ax.tick_params(axis='x', rotation=45); ax.grid(True, linestyle='--'); ax.axhline(0, color='grey', linestyle='--')
    st.pyplot(fig)
with c2:
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.boxplot(data=f_data, x='MA', y='Profit_per_MW', hue='Tech', showfliers=False, ax=ax)
    if not f_data[f_data['is_Highlighted']].empty:
        sns.stripplot(data=f_data[f_data['is_Highlighted']], x='MA', y='Profit_per_MW', hue='Tech', size=8, palette=red_palette, edgecolor='black', dodge=True, legend=False, ax=ax)
    ax.tick_params(axis='x', rotation=45); ax.grid(True, linestyle='--'); ax.axhline(0, color='grey', linestyle='--')
    st.pyplot(fig)

st.write("---")
st.subheader("2. Detalle por Tecnología")
c3, c4 = st.columns(2)
with c3:
    s_data = grouped[grouped['Tech'] == 'Solar PV']
    if not s_data.empty:
        order = s_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.boxplot(data=s_data, x='MA', y='Profit_per_MW', showfliers=False, color='orange', order=order, ax=ax)
        if not s_data[s_data['is_Highlighted']].empty:
            sns.stripplot(data=s_data[s_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=8, color='red', edgecolor='black', order=order, ax=ax)
        ax.set_title('SOLAR PV'); ax.tick_params(axis='x', rotation=45); ax.axhline(0, color='grey', linestyle='--')
        st.pyplot(fig)
with c4:
    w_data = grouped[grouped['Tech'] == 'Wind']
    if not w_data.empty:
        order = w_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.boxplot(data=w_data, x='MA', y='Profit_per_MW', showfliers=False, color='lightgreen', order=order, ax=ax)
        if not w_data[w_data['is_Highlighted']].empty:
            sns.stripplot(data=w_data[w_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=8, color='red', edgecolor='black', order=order, ax=ax)
        ax.set_title('WIND'); ax.tick_params(axis='x', rotation=45); ax.axhline(0, color='grey', linestyle='--')
        st.pyplot(fig)

st.write("---")
st.subheader("3. Mapa de Calor (Heatmap) Agregado")
try:
    heatmap_data = grouped.groupby(['MA', 'Tech'])['Profit_per_MW'].mean().reset_index().pivot(index='MA', columns='Tech', values='Profit_per_MW').fillna(0).sort_index()
    if 'Wind' in heatmap_data and 'Solar PV' in heatmap_data: heatmap_data = heatmap_data[['Wind', 'Solar PV']]
    fig, ax = plt.subplots(figsize=(10, max(6, len(heatmap_data) * 0.4)))
    sns.heatmap(heatmap_data, annot=True, fmt=',.2f', cmap='vlag', center=0, ax=ax)
    st.pyplot(fig)
except Exception:
    st.warning("Datos insuficientes para el Heatmap.")
