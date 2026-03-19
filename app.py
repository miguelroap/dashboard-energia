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
        st.error("😕 Contraseña incorrecta.")
        return False
    else:
        return True

if not check_password():
    st.stop()

st.title("📊 Análisis de Desempeño: Mercados de Ajuste e Intradiarios")

# --- CARGA DE DATOS ---
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
    st.error(f"Error cargando datos. Verifica el archivo parquet.")
    st.stop()

allh['Day'] = pd.to_datetime(allh['Day'])

# --- BARRA LATERAL ---
min_date, max_date = allh['Day'].min().date(), allh['Day'].max().date()
st.sidebar.header("📅 Rango de Fechas")
selected_dates = st.sidebar.date_input("Periodo:", value=(min_date, max_date), min_value=min_date, max_value=max_date)

start_date, end_date = selected_dates if len(selected_dates) == 2 else (min_date, max_date)
allh = allh[(allh['Day'].dt.date >= start_date) & (allh['Day'].dt.date <= end_date)]

st.sidebar.header("🔴 Instalaciones a Resaltar")
ups_interes = ['CLIFV30', 'CLIFV31', 'CLIFV32', 'UPBUS', 'UPLMP', 'UPSLN', 'GALPS59', 'GALPS57', 'GALPS56', 'FCTRAV2', 'EFGNRA', 'PEVER', 'PEVER2', 'EAYAMON', 'EGST146']
installation = ['Pinos Puente 1', 'Pinos Puente 2', 'Pinos Puente 3', 'Buseco', 'Loma', 'La Solana', 'Buseco_Galp', 'Loma_Galp', 'La Solana_Galp', 'Calatrava', 'Bodenaya + Pico + Others', 'Sorolla 1', 'Mallen', 'Ayamonte', 'Barroso']

ma_mapping = allh[['UP', 'MA']].dropna().drop_duplicates(subset=['UP']).set_index('UP')['MA'].to_dict()
selected_ups = [up for up, inst in zip(ups_interes, installation) 
                if st.sidebar.checkbox(f"{inst} ({ma_mapping.get(up, 'Desc')})", value=(up in ['PEVER', 'EGST146']))]

st.sidebar.header("⚙️ Configuración")
# --- CAMBIO APLICADO: 'Todos' por defecto y cambio de nombre ---
aass_sel = st.sidebar.radio(
    "Profit Base", 
    options=['no_sec', 'sec', 'all'], 
    index=2, # Índice 2 es 'all'
    format_func=lambda x: "Sin Secundaria" if x == 'no_sec' else ("Solo Secundaria" if x == 'sec' else "Todos los mercados")
)

# --- CREACIÓN DE PESTAÑAS ---
tab_principal, tab_rt5, tab_gnera, tab_verbund, tab_evo = st.tabs([
    "📈 Dispersión Principal", 
    "⚡ RT5", 
    "📊 Análisis Gnera", 
    "💶 Beneficio Verbund", 
    "📈 Evolución Ingresos"
])

# Procesamiento Base para la pestaña principal
if aass_sel == 'no_sec': cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr']
elif aass_sel == 'sec': cols_sel = ['Profit_b', 'Profit_se']
else: cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']
available_cols = [c for c in cols_sel if c in allh.columns]

allh_main = allh[~allh['MA'].isin(["ENDESA", "IBERDROLA", "EDP", "NATURGY", "HOLALUZ", "ALDROENERGIA Y SOLUCIONES SL"])].copy()
allh_main['Total_Profit'] = allh_main[available_cols].sum(axis=1) if available_cols else 0
allh_main['Month'] = allh_main['Day'].dt.to_period('M')

monthly = allh_main.groupby(['UP', 'Tech', 'MA', 'Month']).agg(
    Monthly_Profit=('Total_Profit', 'sum'),
    Monthly_Energy=('Energy_p48', 'sum') if 'Energy_p48' in allh_main.columns else ('Total_Profit', 'count')
).reset_index()

monthly = pd.merge(monthly, df_power, on='UP', how='left')
monthly['Profit_per_MW'] = (monthly['Monthly_Profit'] / monthly['Power MW']).fillna(0)

grouped = monthly.groupby(['UP', 'Tech', 'MA']).agg(Profit_per_MW=('Profit_per_MW', 'mean'), Total_Energy=('Monthly_Energy', 'sum')).reset_index()
grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)
red_palette = sns.color_palette(['red', 'red', 'red'])

# ==============================================================================
# PESTAÑA 1: PRINCIPAL (SOLO GRÁFICOS DEL MEDIO)
# ==============================================================================
with tab_principal:
    st.subheader("Dispersión de ingresos en Servicios de ajuste por Tecnología")
    c1, c2 = st.columns(2)
    
    with c1:
        s_data = grouped[grouped['Tech'] == 'Solar PV']
        if not s_data.empty:
            order = s_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.boxplot(data=s_data, x='MA', y='Profit_per_MW', showfliers=False, color='orange', order=order, ax=ax)
            if not s_data[s_data['is_Highlighted']].empty:
                sns.stripplot(data=s_data[s_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=8, color='red', edgecolor='black', order=order, ax=ax)
            ax.set_title('SOLAR PV'); ax.tick_params(axis='x', rotation=45); ax.axhline(0, color='grey', linestyle='--')
            st.pyplot(fig)
        else:
            st.info("Sin datos de Solar PV.")
            
    with c2:
        w_data = grouped[grouped['Tech'] == 'Wind']
        if not w_data.empty:
            order = w_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.boxplot(data=w_data, x='MA', y='Profit_per_MW', showfliers=False, color='lightgreen', order=order, ax=ax)
            if not w_data[w_data['is_Highlighted']].empty:
                sns.stripplot(data=w_data[w_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=8, color='red', edgecolor='black', order=order, ax=ax)
            ax.set_title('WIND'); ax.tick_params(axis='x', rotation=45); ax.axhline(0, color='grey', linestyle='--')
            st.pyplot(fig)

# ==============================================================================
# PESTAÑA 2: RT5
# ==============================================================================
with tab_rt5:
    st.subheader("Restricciones técnicas en tiempo real (RT5)")
    try:
        col_rt1, col_rt2 = st.columns(2)
        with col_rt1: ma_rt5 = st.selectbox("Selecciona MA:", allh['MA'].unique(), index=list(allh['MA'].unique()).index('GNERA') if 'GNERA' in allh['MA'].unique() else 0)
        with col_rt2: tech_rt5 = st.selectbox("Selecciona Tech:", allh['Tech'].unique(), index=list(allh['Tech'].unique()).index('Wind') if 'Wind' in allh['Tech'].unique() else 0)
        
        up_rt5 = allh[(allh['MA']==ma_rt5) & (allh['Tech']==tech_rt5)].copy()
        
        if up_rt5.empty:
            st.warning("No hay datos para esta combinación de MA y Tech.")
        else:
            up_rt5['Year_Month'] = up_rt5['Day'].dt.to_period('M')
            
            # Tabla de métricas
            up_m = up_rt5.groupby(['Year_Month'])[['PBF','Energy_p48','Energy_RT1','Profit_tr','Profit_i', 'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se']].sum().reset_index()
            up_m['Profit_AASS'] = up_rt5.groupby(['Year_Month'])[['Profit_rt', 'Profit_t', 'Profit_rr', 'Profit_se', 'Profit_b']].sum().sum(axis=1).values
            
            up_m['% p48/PBF'] = (up_m['Energy_p48']/up_m['PBF'].replace(0, np.nan)) * 100
            up_m['% RT1/PBF'] = (-up_m['Energy_RT1']/up_m['PBF'].replace(0, np.nan)) * 100
            up_m['Intras €/MWh'] = up_m['Profit_i']/up_m['Energy_p48'].replace(0, np.nan)
            up_m['AASS €/MWh'] = up_m['Profit_AASS']/up_m['Energy_p48'].replace(0, np.nan)
            
            df_table_rt5 = up_m[['Year_Month', '% p48/PBF', '% RT1/PBF', 'Profit_tr', 'Profit_AASS', 'Profit_i', 'Intras €/MWh', 'AASS €/MWh']].copy()
            df_table_rt5.columns = ['Period', '% p48/PBF', '% RT1/PBF', 'Real Time €', 'AASS €', 'Intras €', 'Intras €/MWh', 'AASS €/MWh']
            df_table_rt5['Period'] = df_table_rt5['Period'].astype(str)
            
            st.markdown("##### Resumen de Métricas")
            st.dataframe(df_table_rt5.style.format({
                '% p48/PBF': "{:.1f}%", '% RT1/PBF': "{:.1f}%", 
                'Real Time €': "{:,.1f}", 'AASS €': "{:,.1f}", 'Intras €': "{:,.1f}", 
                'Intras €/MWh': "{:.2f}", 'AASS €/MWh': "{:.2f}"
            }), use_container_width=True)

            # Waterfall (Adaptado a gráfico de barras normalizado por día/mes)
            st.markdown("##### Distribución del Profit (€/MWh)")
            df_wf = up_rt5[['MA','Profit_p48','Profit_rt','Profit_tr','Profit_t','Profit_rr','Profit_b','Profit_se','Profit_i','Energy_p48', 'Energy_tr']].sum()
            div_energy = df_wf['Energy_p48'] - df_wf['Energy_tr']
            
            if div_energy > 0:
                wf_data = pd.DataFrame({
                    'Mercado': ['Spot', 'RRTT Ph2', 'Tertiary', 'RR', 'Sec. Band', 'Sec. Energy', 'Intras'],
                    '€/MWh': [df_wf['Profit_p48']/div_energy, df_wf['Profit_rt']/div_energy, df_wf['Profit_t']/div_energy, 
                              df_wf['Profit_rr']/div_energy, df_wf['Profit_b']/div_energy, df_wf['Profit_se']/div_energy, df_wf['Profit_i']/div_energy]
                })
                fig_wf, ax_wf = plt.subplots(figsize=(10, 4))
                sns.barplot(data=wf_data, x='Mercado', y='€/MWh', palette='viridis', ax=ax_wf)
                ax_wf.set_title(f"{ma_rt5} - {tech_rt5} Profit breakdown")
                st.pyplot(fig_wf)
    except Exception as e:
        st.warning(f"Faltan columnas necesarias para el análisis RT5: {e}")

# ==============================================================================
# PESTAÑA 3: ANÁLISIS GNERA
# ==============================================================================
with tab_gnera:
    st.subheader("Análisis Gnera")
    try:
        POTENCIA_INSTALADA = {'EOTMR': 87.6, 'LECDE': 9.6, 'PEVER': 182.3, 'PEVER2': 29.8}
        gnwi = allh[(allh['MA'] == 'GNERA') & (allh['Tech'] == 'Wind') & (allh['UP'].isin(POTENCIA_INSTALADA.keys()))].copy()
        
        if gnwi.empty:
            st.info("No hay datos de GNERA Wind para las instalaciones seleccionadas en este mes.")
        else:
            profit_cols_to_sum = ['Profit_rt', 'Profit_tr', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']
            gnwi['Profit_Total_Extra'] = gnwi[[c for c in profit_cols_to_sum if c in gnwi.columns]].sum(axis=1)
            gnwi['Potencia_MW'] = gnwi['UP'].map(POTENCIA_INSTALADA)
            
            # Reporte Numérico
            df_agg_gnera = gnwi.groupby('UP')[profit_cols_to_sum + ['Profit_Total_Extra']].sum().reset_index()
            df_agg_gnera['Potencia_MW'] = df_agg_gnera['UP'].map(POTENCIA_INSTALADA)
            
            for col in profit_cols_to_sum + ['Profit_Total_Extra']:
                if col in df_agg_gnera.columns:
                    df_agg_gnera[f'{col}_eur_per_MW'] = df_agg_gnera[col] / df_agg_gnera['Potencia_MW']
            
            display_cols = ['UP'] + [c for c in df_agg_gnera.columns if 'eur_per_MW' in c]
            st.markdown("##### Resumen Numérico Agregado (€/MW)")
            st.dataframe(df_agg_gnera[display_cols].style.format({c: "{:,.2f}" for c in display_cols[1:]}), use_container_width=True)

            # Evolución Diaria (adaptada de la horaria)
            st.markdown("##### Evolución Diaria del Profit Total (€/MW)")
            gnwi['Profit_Total_eur_per_MW'] = gnwi['Profit_Total_Extra'] / gnwi['Potencia_MW']
            df_daily_gnera = gnwi.groupby(['UP', 'Day'])['Profit_Total_eur_per_MW'].sum().reset_index()
            
            fig_g, ax_g = plt.subplots(figsize=(12, 5))
            sns.lineplot(data=df_daily_gnera, x='Day', y='Profit_Total_eur_per_MW', hue='UP', marker='o', ax=ax_g)
            ax_g.axhline(0, color='black', linewidth=0.8)
            st.pyplot(fig_g)
            
    except Exception as e:
        st.warning(f"Faltan datos para procesar el Análisis Gnera: {e}")

# ==============================================================================
# PESTAÑA 4: BENEFICIO VERBUND
# ==============================================================================
with tab_verbund:
    st.subheader("Beneficio Verbund Servicios de Ajuste (€)")
    try:
        INPUT_DATA = {
            'FCTRAV2':  ['Calatrava',       41.0,  0.5],
            'EAYAMON':  ['Ayamonte',        26.0,  0.5],
            'EGST146':  ['Barroso',         21.6,  0.5],
            'PEVER':    ['Sorolla 1',       182.3,  0.6],
            'PEVER2':   ['Sorolla Mallén',  29.8,  0.6]
        }
        
        profit_cols_v = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i']
        df_v = allh[allh['UP'].isin(INPUT_DATA.keys())].copy()
        
        df_agg_v = df_v.groupby('UP')[[c for c in profit_cols_v if c in df_v.columns]].sum().reindex(INPUT_DATA.keys()).reset_index().fillna(0)
        
        df_agg_v['Total Profit'] = df_agg_v.iloc[:, 1:].sum(axis=1)
        df_agg_v['Verbund_Pct'] = [val[2] for val in INPUT_DATA.values()]
        df_agg_v['Profit Verbund'] = df_agg_v['Total Profit'] * df_agg_v['Verbund_Pct']
        df_agg_v['Potencia MW'] = [val[1] for val in INPUT_DATA.values()]
        df_agg_v['Profit Verbund / MW'] = df_agg_v['Profit Verbund'] / df_agg_v['Potencia MW']
        
        df_agg_v.insert(1, 'Installation', [val[0] for val in INPUT_DATA.values()])
        
        # Añadir fila de totales
        totales = df_agg_v.select_dtypes(include=[np.number]).sum()
        totales['UP'] = 'Total'
        totales['Installation'] = 'Total'
        totales['Profit Verbund / MW'] = totales['Profit Verbund'] / totales['Potencia MW'] if totales['Potencia MW'] > 0 else 0
        
        df_final_v = pd.concat([df_agg_v, pd.DataFrame([totales])], ignore_index=True)
        
        # Formatear y mostrar en tabla nativa (más bonito en web que plt.table)
        cols_to_show = ['UP', 'Installation'] + [c for c in profit_cols_v if c in df_final_v.columns] + ['Total Profit', 'Profit Verbund', 'Profit Verbund / MW']
        st.dataframe(df_final_v[cols_to_show].style.format({c: "{:,.2f} €" for c in cols_to_show[2:]}), use_container_width=True)
        
    except Exception as e:
        st.warning(f"Asegúrate de haber incluido todas las columnas de Profit en tu exportación. Detalle: {e}")

# ==============================================================================
# PESTAÑA 5: EVOLUCIÓN INGRESOS
# ==============================================================================
with tab_evo:
    st.subheader("Evolución Ingresos por Representante y Tecnología")
    try:
        col_e1, col_e2 = st.columns(2)
        with col_e1: ma_input = st.selectbox("Market Agent (MA):", allh['MA'].unique())
        with col_e2: tech_input = st.selectbox("Tecnología (Tech):", allh['Tech'].unique())
        
        df_evo = allh[(allh['MA'] == ma_input) & (allh['Tech'] == tech_input)].copy()
        
        if df_evo.empty:
            st.info("No hay datos para esta combinación.")
        else:
            df_evo['YearMonth'] = df_evo['Day'].dt.to_period('M').astype(str)
            df_evo_m = df_evo.groupby(['UP', 'YearMonth']).agg(
                Total_Profit=('Total_Profit', 'sum') if 'Total_Profit' in df_evo.columns else ('Profit_rt', 'sum'),
                Total_Energy=('Energy_p48', 'sum') if 'Energy_p48' in df_evo.columns else ('PBF', 'sum')
            ).reset_index()
            
            df_evo_m['Profit_per_MWh'] = df_evo_m['Total_Profit'] / df_evo_m['Total_Energy'].replace(0, np.nan)
            df_evo_m['Total_Profit_k'] = df_evo_m['Total_Profit'] / 1000
            
            st.markdown("##### 1. Evolución Profit en €/MWh")
            fig1, ax1 = plt.subplots(figsize=(10, 4))
            sns.lineplot(data=df_evo_m, x='YearMonth', y='Profit_per_MWh', hue='UP', marker='o', ax=ax1)
            ax1.grid(True); st.pyplot(fig1)
            
            st.markdown("##### 2. Evolución Producción (MWh)")
            fig2, ax2 = plt.subplots(figsize=(10, 4))
            sns.lineplot(data=df_evo_m, x='YearMonth', y='Total_Energy', hue='UP', marker='o', ax=ax2)
            ax2.grid(True); st.pyplot(fig2)
            
            st.markdown("##### 3. Evolución Profit Total (k€)")
            fig3, ax3 = plt.subplots(figsize=(10, 4))
            sns.lineplot(data=df_evo_m, x='YearMonth', y='Total_Profit_k', hue='UP', marker='o', ax=ax3)
            ax3.grid(True); st.pyplot(fig3)
            
    except Exception as e:
        st.warning(f"Error procesando los gráficos de evolución: {e}")
