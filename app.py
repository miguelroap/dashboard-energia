# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
import altair as alt # Usado para tablas estilizadas dinámicas

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard Ancillary Services", layout="wide", page_icon="📊")

# --- ESTILOS CSS PERSONALIZADOS (Para tablas y layout) ---
st.markdown("""
<style>
    /* Estilo para reducir padding en tablas nativas */
    [data-testid="stDataFrame"] > div { margin-bottom: 20px; }
    /* Titulos de sección más pequeños y estéticos */
    .section-title { color: #40466e; font-size: 20px; font-weight: bold; margin-bottom: 15px; margin-top: 10px; border-bottom: 2px solid #f0f2f6; padding-bottom: 5px; }
    /* Mejorar el aspecto general de los contenedores */
    div.block-container { padding-top: 2rem; }
    /* Centrar imágenes de matplotlib */
    [data-testid="stFigure"] { text-align: center; }
</style>
""", unsafe_allow_html=True)

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
        st.text_input("🔑 Introduce la contraseña:", type="password", on_change=password_entered, key="password")
        st.error("😕 Contraseña incorrecta.")
        return False
    else:
        return True

if not check_password():
    st.stop()

st.title("📊 Análisis de Desempeño: Mercados de Ajuste e Intradiarios")

# --- CARGA DE DATOS OPTIMIZADA (CACHE) ---
@st.cache_data
def load_allh_data():
    try:
        # Cargamos explícitamente las columnas necesarias para no saturar la memoria
        cols_needed = ['UP', 'MA', 'Tech', 'Day', 'hour', 'PBF', 'Energy_p48', 'Energy_RT1',
                       'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se', 'Energy_tr', 'Energy_i',
                       'Profit_rt', 'Profit_tr_s', 'Profit_tr', 'Profit_t', 'Profit_rr', 'Profit_b', 
                       'Profit_se', 'Profit_i', 'Rev_tr']
        
        # Necesitamos hour para RT5
        import pyarrow.parquet as pq
        schema = pq.read_schema('allh_part1.parquet')
        cols_to_load = [c for c in cols_needed if c in schema.names]
        
        df1 = pd.read_parquet('allh_part1.parquet', columns=cols_to_load)
        df2 = pd.read_parquet('allh_part2.parquet', columns=cols_to_load)
        return pd.concat([df1, df2], ignore_index=True)
    except Exception as e:
        st.error(f"Error crítico cargando archivos parquet: {e}")
        return pd.DataFrame()

@st.cache_data
def load_power_data():
    try:
        df = pd.read_parquet('ups_dashboard.parquet', columns=['UP', 'Power MW'])
        df['Power MW'] = pd.to_numeric(df['Power MW'], errors='coerce')
        return df.dropna(subset=['Power MW', 'UP'])
    except Exception:
        return pd.DataFrame(columns=['UP', 'Power MW'])

# Cargar bases
allh_full = load_allh_data()
df_power = load_power_data()

if allh_full.empty:
    st.error("No se han podido cargar los datos de base.")
    st.stop()

# Preparación base
allh_full['Day'] = pd.to_datetime(allh_full['Day'])

# Asegurar numéricos para cálculos de RT5 (solución a errores de sumas)
num_cols = ['Profit_rt', 'Profit_tr_s', 'Profit_tr', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i',
            'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se', 'Energy_tr', 'Energy_i']
for col in num_cols:
    if col in allh_full.columns:
        allh_full[col] = pd.to_numeric(allh_full[col], errors='coerce').fillna(0)

# --- SISTEMA DE PESTAÑAS Y CONTROL DE SIDEBAR ---
# Declaramos las pestañas
tab_names = ["📈 Resumen Principal", "⚡ Análisis MRA", "📋 Detalle RT5"]
tabs = st.tabs(tab_names)

# --- 1. FILTRO DE FECHAS (GLOBAL, siempre arriba en sidebar) ---
st.sidebar.header("📅 Rango de Fechas (Global)")
min_date, max_date = allh_full['Day'].min().date(), allh_full['Day'].max().date()
selected_dates = st.sidebar.date_input("Selecciona periodo:", value=(min_date, max_date), min_value=min_date, max_value=max_date)

# Filtrar allh base por fechas
start_date, end_date = selected_dates if len(selected_dates) == 2 else (min_date, max_date)
allh = allh_full[(allh_full['Day'].dt.date >= start_date) & (allh_full['Day'].dt.date <= end_date)].copy()

# ==============================================================================
# PESTAÑA 1: RESUMEN PRINCIPAL (Manejo condicional del Sidebar)
# ==============================================================================
with tabs[0]:
    # --- FILTROS EXCLUSIVOS DE LA PRIMERA PESTAÑA (Conditional Sidebar) ---
    st.sidebar.markdown("---")
    st.sidebar.header("🔴 Instalaciones a Resaltar")
    # (Tu lista de UPs original)
    ups_interes = ['CLIFV30', 'CLIFV31', 'CLIFV32', 'UPBUS', 'UPLMP', 'UPSLN', 'GALPS59', 'GALPS57', 'GALPS56', 'FCTRAV2', 'EFGNRA', 'PEVER', 'PEVER2', 'EAYAMON', 'EGST146']
    installation = ['Pinos Puente 1', 'Pinos Puente 2', 'Pinos Puente 3', 'Buseco', 'Loma', 'La Solana', 'Buseco_Galp', 'Loma_Galp', 'La Solana_Galp', 'Calatrava', 'Bodenaya + Pico + Others', 'Sorolla 1', 'Mallen', 'Ayamonte', 'Barroso']
    
    ma_mapping = allh[['UP', 'MA']].dropna().drop_duplicates(subset=['UP']).set_index('UP')['MA'].to_dict()
    selected_ups = [up for up, inst in zip(ups_interes, installation) 
                    if st.sidebar.checkbox(f"{inst} ({ma_mapping.get(up, 'Desc')})", value=(up in ['PEVER', 'EGST146']))]

    st.sidebar.header("⚙️ Configuración")
    aass_sel = st.sidebar.radio("Profit Base", options=['no_sec', 'sec', 'all'], index=2, format_func=lambda x: "Sin Secundaria" if x == 'no_sec' else ("Solo Secundaria" if x == 'sec' else "Todos"))

    # --- LÓGICA GRÁFICOS PRINCIPALES ---
    # 1. Filtro estricto MAs (como al principio)
    excluded_MAs = ["ENDESA", "IBERDROLA", "EDP", "NATURGY", "HOLALUZ", "ALDROENERGIA Y SOLUCIONES SL"]
    
    # 2. Configurar profit base
    if aass_sel == 'no_sec': cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr']
    elif aass_sel == 'sec': cols_sel = ['Profit_b', 'Profit_se']
    else: cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']
    available_cols = [c for c in cols_sel if c in allh.columns]

    # Procesamiento Main
    allh_main = allh[~allh['MA'].isin(excluded_MAs)].copy()
    allh_main['Total_Profit'] = allh_main[available_cols].sum(axis=1) if available_cols else 0
    allh_main['Month'] = allh_main['Day'].dt.to_period('M')

    monthly = allh_main.groupby(['UP', 'Tech', 'MA', 'Month']).agg(
        Monthly_Profit=('Total_Profit', 'sum'),
        Monthly_Energy=('Energy_p48', 'sum') if 'Energy_p48' in allh_main.columns else ('Total_Profit', 'count')
    ).reset_index()

    monthly = pd.merge(monthly, df_power, on='UP', how='left')
    monthly['Profit_per_MW'] = (monthly['Monthly_Profit'] / monthly['Power MW']).fillna(0)

    # Agregación final
    grouped = monthly.groupby(['UP', 'Tech', 'MA']).agg(Profit_per_MW=('Profit_per_MW', 'mean'), Total_Energy=('Monthly_Energy', 'sum')).reset_index()
    grouped['is_Highlighted'] = grouped['UP'].isin(selected_ups)
    
    st.markdown('<div class="section-title">Dispersión de ingresos en Servicios de ajuste por Tecnología</div>', unsafe_allow_html=True)
    
    # DISTRIBUCIÓN Side-by-Side (gráficos reducidos)
    col1, col2 = st.columns(2)
    with col1:
        s_data = grouped[grouped['Tech'] == 'Solar PV']
        if not s_data.empty:
            order = s_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
            fig, ax = plt.subplots(figsize=(8, 5)) # Tamaño reducido
            sns.boxplot(data=s_data, x='MA', y='Profit_per_MW', showfliers=False, color='orange', order=order, ax=ax)
            if not s_data[s_data['is_Highlighted']].empty:
                sns.stripplot(data=s_data[s_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=6, color='red', edgecolor='black', order=order, ax=ax)
            ax.set_title('SOLAR PV: Profit ordered by Agent Mean'); ax.tick_params(axis='x', rotation=45); ax.axhline(0, color='grey', linestyle='--')
            st.pyplot(fig)
        else:
            st.info("Sin datos de Solar PV en este periodo.")
            
    with col2:
        w_data = grouped[grouped['Tech'] == 'Wind']
        if not w_data.empty:
            order = w_data.groupby('MA')['Profit_per_MW'].mean().sort_values(ascending=False).index
            fig, ax = plt.subplots(figsize=(8, 5)) # Tamaño reducido
            sns.boxplot(data=w_data, x='MA', y='Profit_per_MW', showfliers=False, color='lightgreen', order=order, ax=ax)
            if not w_data[w_data['is_Highlighted']].empty:
                sns.stripplot(data=w_data[w_data['is_Highlighted']], x='MA', y='Profit_per_MW', size=6, color='red', edgecolor='black', order=order, ax=ax)
            ax.set_title('WIND: Profit ordered by Agent Mean'); ax.tick_params(axis='x', rotation=45); ax.axhline(0, color='grey', linestyle='--')
            st.pyplot(fig)

# ==============================================================================
# PESTAÑA 2: ANÁLISIS MRA (Antigua RT5 - Solución errores y filtros profundos)
# ==============================================================================
with tabs[1]:
    st.markdown('<div class="section-title">Análisis MRA - Tecnología - Instalación</div>', unsafe_allow_html=True)
    
    # 1. FILTROS PROFUNDOS INTEGRADOS EN LA PESTAÑA (Top columns)
    f_ma, f_tech, f_up = st.columns(3)
    with f_ma:
        # Solo mostrar representantes que tengan UPs habilitadas en SSAA
        ma_mask = (allh_full['Profit_rt']!=0)|(allh_full['Profit_b']!=0)|(allh_full['Profit_t']!=0)|(allh_full['Profit_rr']!=0)
        qualified_MAs = sorted(allh_full[ma_mask]['MA'].unique())
        sel_ma = st.selectbox("1. Representante de Mercado (MA)", qualified_MAs, index=qualified_MAs.index('GNERA') if 'GNERA' in qualified_MAs else 0)
    
    with f_tech:
        tech_opts = sorted(allh_full[allh_full['MA'] == sel_ma]['Tech'].unique())
        sel_tech = st.selectbox("2. Tecnología", tech_opts, index=tech_opts.index('Wind') if 'Wind' in tech_opts else 0)
        
    with f_up:
        # Lógica de filtrado de UP original del script
        up_rt5 = allh_full[(allh_full['MA']==sel_ma) & (allh_full['Tech']==sel_tech)].copy()
        mask_rt5 = (up_rt5['Profit_rt']!=0)|(up_rt5['Profit_b']!=0)|(up_rt5['Profit_t']!=0)|(up_rt5['Profit_rr']!=0)
        up_rt5_qualified = up_rt5[mask_rt5]
        up_opts = ['Cualquier UP'] + sorted(up_rt5_qualified['UP'].unique().tolist())
        sel_up = st.selectbox("3. Unidad Producción (UP) - Opcional", up_opts)

    # 2. PROCESAMIENTO MRA (Aplicando filtros contextuales y globales de fecha)
    try:
        if sel_up == 'Cualquier UP':
            # Usar la lista de UPs cualificadas de ese MA/Tech
            up_ids = up_rt5_qualified['UP'].unique().tolist()
            up_df = allh[allh['UP'].isin(up_ids)].copy()
        else:
            up_df = allh[allh['UP'] == sel_up].copy()
            
        if up_df.empty:
            st.warning("No hay datos disponibles para la combinación de fechas y filtros seleccionados en MRA.")
        else:
            # CORRECCIÓN DEL ERROR: numeric_only=True y agrupar quitando columnas de fecha del sumatorio
            cols_to_groupby = ['Tech','MA','Day','hour']
            # Dejar fuera del sumatorio columnas temporales no numéricas
            cols_sum = ['PBF','Energy_p48','Energy_RT1','Profit_rt', 'Profit_t', 'Profit_rr', 'Profit_se', 'Profit_b','Profit_tr','Profit_i','Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se', 'Energy_tr','Profit_p48','Rev_tr']
            
            # Agrupar asegurando que solo se suman numéricos
            up_grouped = up_df.groupby(cols_to_groupby)[cols_sum].sum(numeric_only=True).reset_index()
            
            # Cálculos adicionales
            up_grouped['Profit_AASS'] = up_grouped[['Profit_rt', 'Profit_t', 'Profit_rr', 'Profit_se', 'Profit_b']].sum(axis=1)
            up_grouped['Energy_AASS'] = up_grouped[['Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se']].sum(axis=1)

            # --- TABLA RESUMEN MENSUAL ESTILIZADA ---
            # CORRECCIÓN ERROR DATETIME AQUÍ TAMBIÉN
            up_grouped['Year_Month'] = up_grouped['Day'].dt.to_period('M')
            
            up_m = up_grouped.groupby(['Year_Month'])[['PBF','Energy_p48','Energy_RT1','Profit_AASS','Profit_tr','Profit_i']].sum(numeric_only=True).reset_index()
            
            # Evitar divisiones por cero con .replace(0, np.nan)
            up_m['% p48/PBF'] = up_m['Energy_p48'] / up_m['PBF'].replace(0, np.nan)
            up_m['% RT1/PBF'] = -up_m['Energy_RT1'] / up_m['PBF'].replace(0, np.nan)
            up_m['Intras €/MWh'] = up_m['Profit_i'] / up_m['Energy_p48'].replace(0, np.nan)
            up_m['AASS €/MWh'] = up_m['Profit_AASS'] / up_m['Energy_p48'].replace(0, np.nan)
            
            # Formatear tabla para visualización (Nativa de Streamlit estilizada)
            up_m_def = up_m.set_index('Year_Month')
            # Seleccionar y renombrar columnas
            cols_show = ['% p48/PBF', '% RT1/PBF', 'Profit_tr', 'Profit_AASS', 'Profit_i', 'Intras €/MWh', 'AASS €/MWh']
            df_table_mra = up_m_def[cols_show].copy()
            df_table_mra.columns = ['% p48/PBF', '% RT1/PBF', 'Real Time €', 'AASS €', 'Intras €', 'Intras €/MWh', 'AASS €/MWh']
            
            st.markdown('<div class="section-title">Resumen Métricas Mensuales (MRA)</div>', unsafe_allow_html=True)
            # Mostrar como dataframe formateado dinámico (norudimentario, interactivo)
            st.dataframe(df_table_mra.style.format({
                '% p48/PBF': '{:.1%}', '% RT1/PBF': '{:.1%}',
                'Real Time €': '{:,.2f}', 'AASS €': '{:,.2f}', 'Intras €': '{:,.2f}',
                'Intras €/MWh': '{:.2f}', 'AASS €/MWh': '{:.2f}'
            }), use_container_width=True)

            st.markdown('<div class="section-title">Distribución y Evolución</div>', unsafe_allow_html=True)
            col_m1, col_m2 = st.columns(2)
            
            # --- BARRA CASCADA (Mapeado de profit por mercado) ---
            with col_m1:
                st.markdown("**Desglose de Beneficio (€/MWh)**")
                # Agrupación global de la selección
                g_df = up_grouped.drop(columns=['hour','Year_Month'], errors='ignore').groupby(['Tech','MA']).sum(numeric_only=True).reset_index()
                
                # Suponiendo que hay un MA o sumando todos los del MA seleccionado
                if not g_df.empty:
                    w_data = g_df[g_df['MA'] == sel_ma].iloc[0] # Tomamos el primero si hay múltiples días
                    
                    energy_diff = w_data['Energy_p48'] - w_data['Energy_tr']
                    
                    if energy_diff != 0:
                        # Preparar datos waterfall
                        # Nota: He quitado Rev_tr del cálculo del waterfall del script porque no cuadraba con la suma total.
                        # He mantenido los componentes de profit sumados.
                        cols_p = ['Profit_p48','Profit_rt','Profit_tr','Profit_t','Profit_rr','Profit_b','Profit_se','Profit_i']
                        # Profit_Total de SSAA
                        p_total_ssaa = w_data[['Profit_rt','Profit_tr','Profit_t','Profit_rr','Profit_b','Profit_se','Profit_i']].sum()
                        
                        wf_df = pd.DataFrame({
                            'Concepto': ['Spot', 'RRTT Ph2', 'RT5', 'Tertiary', 'RR', 'Sec. Band', 'Sec. Energy', 'Intras'],
                            'Valor': [w_data['Profit_p48'], w_data['Profit_rt'], w_data['Profit_tr'], w_data['Profit_t'], 
                                       w_data['Profit_rr'], w_data['Profit_b'], w_data['Profit_se'], w_data['Profit_i']]
                        })
                        # Normalizar por energía neta
                        wf_df['€/MWh'] = wf_df['Valor'] / energy_diff
                        
                        # Generar gráfico dinámico estilocascada con Altair (más atractivo que matplotlib)
                        source = wf_df.copy()
                        source['label'] = source['Concepto']
                        
                        # Añadir fila TOTAL
                        p_p48 = source.iloc[0]['Valor']
                        total_profit = (p_p48 + p_total_ssaa) / energy_diff
                        source.loc[len(source)] = ['TOTAL', p_p48 + p_total_ssaa, total_profit, 'TOTAL']
                        
                        fig_wf, ax_wf = plt.subplots(figsize=(7, 4))
                        
                        # Lógica de colores y acumulado para waterfall
                        base = 0
                        labels = []
                        positions = np.arange(len(source))
                        
                        for i, row in source.iterrows():
                            val = row['€/MWh']
                            if i == 0: # Inicio (Spot)
                                ax_wf.bar(i, val, color='#add8e6', edgecolor='black', alpha=0.8)
                                base = val
                                color = '#add8e6'
                            elif i == len(source) - 1: # Final (TOTAL)
                                ax_wf.bar(i, val, color='#5f9ea0', edgecolor='black')
                                color = '#5f9ea0'
                            else: # SSAA
                                color = '#32cd32' if val >= 0 else '#ff0000'
                                ax_wf.bar(i, val, bottom=base if val >= 0 else base + val, color=color, alpha=0.7, edgecolor='black')
                                base += val
                            
                            labels.append(row['label'])
                            # Texto etiqueta
                            ax_wf.text(i, base if val >= 0 else base + val, f"{val:.1f}", ha='center', va='bottom', fontsize=8, weight='bold')

                        ax_wf.set_xticks(positions); ax_wf.set_xticklabels(labels, rotation=45, ha='right')
                        ax_wf.set_ylabel('€/MWh'); ax_wf.set_title(f"MRA Breakdown: {sel_ma} ({sel_up})", fontsize=10)
                        ax_wf.grid(axis='y', linestyle='--', alpha=0.5)
                        st.pyplot(fig_wf)
                    else:
                        st.info("Energía neta (p48 - tr) es cero. No se puede calcular €/MWh.")

            # --- GRÁFICO EVOLUCIÓN HORARIA (Line plot) ---
            with col_m2:
                st.markdown("**Evolución Despacho Horario Medio (MW)**")
                # Agrupar por hora media del periodo
                up_hourly = up_grouped.groupby('hour')[['PBF','Energy_p48','Energy_i','Energy_AASS','Energy_tr']].mean().reset_index()
                
                # Formateo dinámico con Seaborn
                fig_l, ax_l = plt.subplots(figsize=(7, 4))
                
                label_map = {'PBF': 'PBF', 'Energy_p48': 'P48', 'Energy_i': 'Intras', 'Energy_AASS': 'SSAA', 'Energy_tr': 'RT5'}
                # Normalizar a lista larga para Seaborn
                up_hourly_long = up_hourly.melt(id_vars='hour', var_name='Variable', value_name='MW')
                up_hourly_long['label'] = up_hourly_long['Variable'].map(label_map)
                
                # Graficar con Seaborn (atractivo)
                sns.lineplot(data=up_hourly_long, x='hour', y='MW', hue='label', marker='o', ax=ax_l, palette='Set2')
                
                # Personalización (Reducida)
                ax_l.set_xticks(range(0, 24)); ax_l.set_xlabel("Hora"); ax_l.set_ylabel("MW"); ax_l.grid(True, alpha=0.3)
                ax_l.legend(title='', fontsize=8, loc='upper right')
                ax_l.set_title(f"Average Hourly Dispatch: {sel_ma} ({sel_up})", fontsize=10)
                st.pyplot(fig_l)

    except Exception as e:
        st.error(f"Error procesando la pestaña Análisis MRA: {e}")

# ==============================================================================
# PESTAÑA 3: NUEVA PESTAÑA "⚡ DETALLE RT5" (Integración scripts 29/10 - 31/10)
# ==============================================================================
with tabs[2]:
    st.markdown('<div class="section-title">Análisis RT5 (Fase 3 y 4): Precios y Ofertas</div>', unsafe_allow_html=True)
    
    # --- PROCESAMIENTO INICIAL (Script RT5_Offers.py) ---
    try:
        # Nota: La columna se llama Profit_tr_s para RT5_strategy según mapeo SSAA
        rt5_col = 'Profit_tr_s'
        if rt5_col not in allh.columns:
            st.error("No se encuentra la columna 'Profit_tr_s' necesaria para Detalle RT5.")
        else:
            # Paso 1: Filtrar Tech y Profit_RT5 != 0
            filtered_rt5 = allh[ (allh['Tech'].isin(['Solar PV', 'Wind'])) & (allh[rt5_col] != 0) ].copy()
            
            # Paso 2 y 3: Price_RT5 (Prevenir división por cero)
            # Manejar 'Energy_tr' = 0 con .replace(0, np.nan)
            filtered_rt5['Price_RT5'] = filtered_rt5['Rev_tr'] / filtered_rt5['Energy_tr'].replace(0, np.nan)
            filtered_rt5.dropna(subset=['Price_RT5'], inplace=True) # Eliminar infinitos/NaNs
            
            if filtered_rt5.empty:
                st.warning("No hay ofertas casadas en RT5 (Profit_tr_s != 0) para el periodo y tecnologías seleccionadas.")
            else:
                # --- A. TABLAS DE RESUMEN (No rudimentarias, dinámicas) ---
                st.markdown('<div class="section-title">A. Resumen por Representante de Mercado (MA)</div>', unsafe_allow_html=True)
                
                col_rt_a1, col_rt_a2 = st.columns(2)
                
                with col_rt_a1:
                    st.markdown("**Todo el Mercado (Criterio: Min Bid < -50€)**")
                    
                    # Cálculos agrupados por MA
                    total_p_ma = filtered_rt5.groupby('MA')[rt5_col].sum()
                    e_tr_sum_ma = filtered_rt5.groupby('MA')['Energy_tr'].sum()
                    
                    # €/MWh_resource (usando Energy_p48 - Energy_tr)
                    e_p48_tr_diff_ma = filtered_rt5['Energy_p48'] - filtered_rt5['Energy_tr']
                    # Agrupar y aplicar formula por MA (Evitar división por cero globalmente)
                    eur_mwh_r_ma = filtered_rt5.groupby('MA').apply(
                        lambda x: x[rt5_col].sum() / e_p48_tr_diff_ma[x.index].sum()
                    ).replace([np.inf, -np.inf], 0).fillna(0)
                    
                    # Weighted Avg Bid: sum(Price * E_tr) / sum(E_tr)
                    w_avg_bid_ma = filtered_rt5.groupby('MA').apply(
                        lambda x: (x['Price_RT5'] * x['Energy_tr']).sum() / x['Energy_tr'].sum()
                    ).replace([np.inf, -np.inf], 0).fillna(0)
                    
                    max_bid_ma = filtered_rt5.groupby('MA')['Price_RT5'].max()
                    min_bid_ma = filtered_rt5.groupby('MA')['Price_RT5'].min()
                    
                    # Combinar en DF
                    res_ma = pd.DataFrame({
                        'Total Profit RT5': total_p_ma,
                        '€/MWh_resource': eur_mwh_r_ma,
                        'Weighted Avg Bid': w_avg_bid_ma,
                        'Max Bid': max_bid_ma,
                        'Min Bid': min_bid_ma
                    })
                    
                    # Aplicar filtro estricto del script
                    filtered_res_ma = res_ma[res_ma['Min Bid'] < -50]
                    
                    if filtered_res_ma.empty:
                        st.info("Ningún MA tiene ofertas casadas con precio < -50€.")
                    else:
                        st.dataframe(filtered_res_ma.style.format({
                            'Total Profit RT5': '{:,.2f} €', '€/MWh_resource': '{:.2f}',
                            'Weighted Avg Bid': '{:.2f}', 'Max Bid': '{:.2f}', 'Min Bid': '{:.2f}'
                        }), use_container_width=True)

                with col_rt_a2:
                    st.markdown("**Instalaciones Específicas (FCTRAV2, PEVER)**")
                    up_list_rt = ['FCTRAV2', 'PEVER']
                    up_rt5_v = filtered_rt5[filtered_rt5['UP'].isin(up_list_rt)].copy()
                    
                    if up_rt5_v.empty:
                        st.info("Sin datos para FCTRAV2 o PEVER.")
                    else:
                        total_p_v = up_rt5_v.groupby('MA')[rt5_col].sum()
                        
                        e_p48_tr_diff_v = up_rt5_v['Energy_p48'] - up_rt5_v['Energy_tr']
                        eur_mwh_r_v = up_rt5_v.groupby('MA').apply(
                            lambda x: x[rt5_col].sum() / e_p48_tr_diff_v[x.index].sum()
                        ).replace([np.inf, -np.inf], 0).fillna(0)
                        
                        w_avg_bid_v = up_rt5_v.groupby('MA').apply(
                            lambda x: (x['Price_RT5'] * x['Energy_tr']).sum() / x['Energy_tr'].sum()
                        ).replace([np.inf, -np.inf], 0).fillna(0)
                        
                        max_bid_v = up_rt5_v.groupby('MA')['Price_RT5'].max()
                        min_bid_v = up_rt5_v.groupby('MA')['Price_RT5'].min()
                        
                        res_v = pd.DataFrame({
                            'Total Profit RT5': total_p_v,
                            '€/MWh_resource': eur_mwh_r_v,
                            'Weighted Avg Bid': w_avg_bid_v,
                            'Max Bid': max_bid_v,
                            'Min Bid': min_bid_v
                        })
                        
                        st.dataframe(res_v.style.format({
                            'Total Profit RT5': '{:,.2f} €', '€/MWh_resource': '{:.2f}',
                            'Weighted Avg Bid': '{:.2f}', 'Max Bid': '{:.2f}', 'Min Bid': '{:.2f}'
                        }), use_container_width=True)

                # --- B. GRÁFICOS DINÁMICOS (Scatter y Boxplot reducidos) ---
                st.markdown('<div class="section-title">B. Dispersión de Precios (Offers Matched)</div>', unsafe_allow_html=True)
                
                # Preparar base de MAs filtrados del script (Min < -50)
                if not filtered_res_ma.empty:
                    # MAs a graficar (excluyendo específicos como 'ESTABANELL...')
                    mas_to_plot_list = filtered_res_ma.index.tolist()
                    if 'ESTABANELL Y PAHISA MERCATOR' in mas_to_plot_list:
                        mas_to_plot_list.remove('ESTABANELL Y PAHISA MERCATOR')
                    
                    df_graph = filtered_rt5[filtered_rt5['MA'].isin(mas_to_plot_list)].copy()
                    
                    col_rt_b1, col_rt_b2 = st.columns(2)
                    
                    with col_rt_b1:
                        # Gráfico de dispersión MA vs Price_RT5
                        fig_s, ax_s = plt.subplots(figsize=(8, 6))
                        # Reducir alpha para mejorar estética rudimentaria
                        sns.scatterplot(data=df_graph, x='MA', y='Price_RT5', alpha=0.3, ax=ax_s, s=30, color='#40466e')
                        ax_s.set_title("Scatter: Price_RT5 vs MA", fontsize=10)
                        ax_s.set_ylabel("Price_RT5 €/MWh"); ax_s.set_xlabel(""); ax_s.grid(True, alpha=0.3)
                        ax_s.tick_params(axis='x', rotation=90, labelsize=8)
                        st.pyplot(fig_s)
                        
                    with col_rt_b2:
                        # Boxplot Price_RT5 por MA
                        fig_b, ax_b = plt.subplots(figsize=(8, 6))
                        sns.boxplot(data=df_graph, x='MA', y='Price_RT5', showfliers=False, ax=ax_b, palette='vlag', edgecolor='black')
                        ax_b.set_title("Boxplot: Price_RT5 matched by Market Agent", fontsize=10)
                        ax_b.set_ylabel("Price_RT5 €/MWh"); ax_b.set_xlabel(""); ax_b.grid(False, axis='x')
                        ax_b.grid(True, axis='y', alpha=0.3)
                        ax_b.tick_params(axis='x', rotation=90, labelsize=8)
                        st.pyplot(fig_b)

                    # --- C. DISPERSIÓN INDIVIDUAL POR MA (Dinámica, no rudimentaria) ---
                    st.markdown('<div class="section-title">C. Detalle de Ofertas por UP (Gráficos Dinámicos)</div>', unsafe_allow_html=True)
                    ma_opts_rt = ['Selecciona un MA...'] + sorted(mas_to_plot_list)
                    sel_ma_rt_graph = st.selectbox("Elige un Representante de Mercado (MA) para ver detalle por UP", ma_opts_rt)
                    
                    if sel_ma_rt_graph != 'Selecciona un MA...':
                        ma_rt_data = df_graph[df_graph['MA'] == sel_ma_rt_graph]
                        
                        fig_i, ax_i = plt.subplots(figsize=(10, 5))
                        sns.scatterplot(data=ma_rt_data, x='UP', y='Price_RT5', alpha=0.4, s=40, color='#5f9ea0', ax=ax_i)
                        ax_i.set_title(f'Price_RT5 Offers Matched: "{sel_ma_rt_graph}"', fontsize=12)
                        ax_i.set_ylabel("Price_RT5 €/MWh"); ax_i.set_xlabel(""); ax_i.grid(True, alpha=0.3)
                        ax_i.tick_params(axis='x', rotation=90, labelsize=9)
                        st.pyplot(fig_i)

                # --- D. TABLA BENEFICIO VERBUND (Stylized Streamlit DataFrame, no Imagen Rudimentaria) ---
                # Integración del script `AncillaryServicesProfits.py` para la tabla Verbund
                st.markdown('<div class="section-title">D. Tabla Beneficio Verbund RT RT (€) - Estilizada DDBB</div>', unsafe_allow_html=True)
                
                ups_inte_v = ['CLIFV30', 'CLIFV31', 'CLIFV32', 'UPBUS', 'UPLMP', 'UPSLN', 
                             'GALPS59', 'GALPS57', 'GALPS56', 'FCTRAV2', 'CLIWI12', 'CLIWI15', 
                             'CLIFV20', 'EFGNRA', 'PEVER', 'PEVER2', 'EAYAMON', 'EGST146']
                
                installation_v = ['Pinos Puente 1', 'Pinos Puente 2', 'Pinos Puente 3', 'Buseco', 'Loma', 'La Solana', 
                                 'Buseco_Galp', 'Loma_Galp', 'La Solana_Galp', 'Calatrava', 'Buseco_Holaluz', 'Loma_Holaluz', 
                                 'La Solana_Holaluz', 'Bodenaya + Pico + Others', 'Sorolla 1', 'Mallen', 'Ayamonte', 'Barroso']
                
                mapping_up_inst_v = dict(zip(ups_inte_v, installation_v))
                
                # Filtrar base global allh
                verbund_base = allh[allh['UP'].isin(ups_inte_v)].copy()
                
                if verbund_base.empty:
                    st.info("Sin datos para las instalaciones Verbund en este periodo.")
                else:
                    verbund_base['Day'] = pd.to_datetime(verbund_base['Day'])
                    # Forzar formato Year_Month compatible con st.dataframe
                    verbund_base['Year_Month'] = verbund_base['Day'].dt.to_period('M').astype(str)
                    
                    # Agrupación asegurando numeric_only (como RT5)
                    verbund_add = verbund_base.groupby(['Year_Month', 'UP'])[['Rev_tr','Profit_tr','Profit_tr_s','Profit_i']].sum(numeric_only=True).reset_index()
                    
                    # Añadir columna Installation
                    verbund_add['Installation'] = verbund_add['UP'].map(mapping_up_inst_v)
                    
                    # Preparar tabla para visualización estilizada dinámicamente
                    res_cols = ['Year_Month', 'UP', 'Installation', 'Rev_tr', 'Profit_tr', 'Profit_tr_s']
                    df_table_verb = verbund_add[res_cols].copy()
                    
                    # Renombrar columnas para estetica
                    df_table_verb.columns = ['Period', 'UP', 'Installation', 'Revenue TR RT (€)', 'To be received (€)', 'To be shared (€)']
                    
                    # MOSTRAR TABLA ESTILIZADA DINÁMICA (Nativa, no imagen rudimentaria)
                    # He quitado los colores condicionales por defecto para no saturar, pero he reducido el padding
                    st.dataframe(df_table_verb.style.format({
                        'Revenue TR RT (€)': '{:,.2f}', 'To be received (€)': '{:,.2f}', 'To be shared (€)': '{:,.2f}'
                    }).hide_index(), use_container_width=True)

    except Exception as e:
        st.error(f"Error procesando pestaña Detalle RT5: {e}")
