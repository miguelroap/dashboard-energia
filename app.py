# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

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

# --- CARGA DE DATOS OPTIMIZADA ---
@st.cache_data
def load_allh_data():
    try:
        cols_needed = ['UP', 'MA', 'Tech', 'Day', 'hour', 'PBF', 'Energy_p48', 'Energy_RT1',
                       'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se', 'Energy_tr', 'Energy_i',
                       'Profit_rt', 'Profit_tr_s', 'Profit_tr', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i', 'Rev_tr']
        
        import pyarrow.parquet as pq
        schema = pq.read_schema('allh_part1.parquet')
        cols_to_load = [c for c in cols_needed if c in schema.names]
        
        df1 = pd.read_parquet('allh_part1.parquet', columns=cols_to_load)
        df2 = pd.read_parquet('allh_part2.parquet', columns=cols_to_load)
        return pd.concat([df1, df2], ignore_index=True)
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

st.sidebar.header("🔴 Instalaciones a Resaltar")
ups_interes = ['CLIFV30', 'CLIFV31', 'CLIFV32', 'UPBUS', 'UPLMP', 'UPSLN', 'GALPS59', 'GALPS57', 'GALPS56', 'FCTRAV2', 'EFGNRA', 'PEVER', 'PEVER2', 'EAYAMON', 'EGST146']
installation = ['Pinos Puente 1', 'Pinos Puente 2', 'Pinos Puente 3', 'Buseco', 'Loma', 'La Solana', 'Buseco_Galp', 'Loma_Galp', 'La Solana_Galp', 'Calatrava', 'Bodenaya + Pico + Others', 'Sorolla 1', 'Mallen', 'Ayamonte', 'Barroso']

ma_mapping = allh[['UP', 'MA']].dropna().drop_duplicates(subset=['UP']).set_index('UP')['MA'].to_dict()
selected_ups = [up for up, inst in zip(ups_interes, installation) 
                if st.sidebar.checkbox(f"{inst} ({ma_mapping.get(up, 'Desc')})", value=(up in ['PEVER', 'EGST146']))]

st.sidebar.header("⚙️ Configuración")
aass_sel = st.sidebar.radio(
    "Profit Base", 
    options=['no_sec', 'sec', 'all'], 
    index=2, 
    format_func=lambda x: "Sin Secundaria" if x == 'no_sec' else ("Solo Secundaria" if x == 'sec' else "Todos los mercados")
)

# Convertimos a numérico de forma global
num_cols = ['Profit_rt', 'Profit_tr_s', 'Profit_tr', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i',
            'PBF', 'Energy_p48', 'Energy_RT1', 'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se', 'Energy_tr', 'Energy_i']
for c in num_cols:
    if c in allh.columns:
        allh[c] = pd.to_numeric(allh[c], errors='coerce').fillna(0)

# --- CREACIÓN DE PESTAÑAS ---
tab_principal, tab_rt5, tab_gnera, tab_verbund, tab_evo = st.tabs([
    "📈 Dispersión Principal", 
    "⚡ RT5", 
    "📊 Análisis Gnera", 
    "💶 Beneficio Verbund", 
    "📈 Evolución Ingresos"
])

# ==============================================================================
# PESTAÑA 1: PRINCIPAL (Dispersión de ingresos en Servicios de ajuste por Tecnología)
# ==============================================================================
with tab_principal:
    st.subheader("Dispersión de ingresos en Servicios de ajuste por Tecnología")
    
    # 1. Filtro de UPs activas (como lo tenías originalmente)
    active_mask = pd.Series(False, index=allh.index)
    for c in ['Profit_rt', 'Profit_b']:
        if c in allh.columns:
            active_mask = active_mask | (allh[c] != 0)
    active_ups = allh[active_mask]['UP'].unique()
    
    # 2. Exclusión de MAs no deseados
    excluded_MAs = ["ENDESA", "IBERDROLA", "EDP", "NATURGY", "HOLALUZ", "ALDROENERGIA Y SOLUCIONES SL", "Desconocido"]
    
    allh_main = allh[(allh['UP'].isin(active_ups)) & (~allh['MA'].isin(excluded_MAs))].copy()
    
    # 3. Selección de mercados
    if aass_sel == 'no_sec': cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr']
    elif aass_sel == 'sec': cols_sel = ['Profit_b', 'Profit_se']
    else: cols_sel = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']
    available_cols = [c for c in cols_sel if c in allh_main.columns]

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
        with col_rt1: ma_rt5 = st.selectbox("MA (RT5):", sorted(allh['MA'].unique()), index=sorted(allh['MA'].unique()).index('GNERA') if 'GNERA' in allh['MA'].unique() else 0)
        with col_rt2: tech_rt5 = st.selectbox("Tech (RT5):", sorted(allh['Tech'].unique()), index=sorted(allh['Tech'].unique()).index('Wind') if 'Wind' in allh['Tech'].unique() else 0)
        
        mask_rt5 = (allh['Profit_rt']!=0)|(allh['Profit_b']!=0)|(allh['Profit_t']!=0)|(allh['Profit_rr']!=0)
        rrtt_up = allh[allh['MA'] == ma_rt5][mask_rt5]
        rrtt_up = rrtt_up[rrtt_up['Tech'] == tech_rt5]
        rrtt_up_l = rrtt_up['UP'].unique().tolist()
        
        up = allh[allh['UP'].isin(rrtt_up_l)].copy()
        
        if up.empty:
            st.warning("No hay datos suficientes para esta combinación.")
        else:
            # Solución al error datetime64: Extraer Year_Month ANTES de sumar y agrupar solo numéricos
            up['Year_Month'] = up['Day'].dt.to_period('M')
            
            # Tabla de métricas
            cols_to_sum_m = ['PBF','Energy_p48','Energy_RT1','Profit_tr','Profit_i', 'Energy_rt', 'Energy_t', 'Energy_rr', 'Energy_se']
            up_m = up.groupby(['Year_Month'])[cols_to_sum_m].sum(numeric_only=True).reset_index()
            
            # Suma segura de Profits
            profit_cols_rt5 = [c for c in ['Profit_rt', 'Profit_t', 'Profit_rr', 'Profit_se', 'Profit_b'] if c in up.columns]
            up_m['Profit_AASS'] = up.groupby(['Year_Month'])[profit_cols_rt5].sum(numeric_only=True).sum(axis=1).values
            
            up_m['% p48/PBF'] = (up_m['Energy_p48']/up_m['PBF'].replace(0, np.nan)) * 100
            up_m['% RT1/PBF'] = (-up_m['Energy_RT1']/up_m['PBF'].replace(0, np.nan)) * 100
            up_m['Intras €/MWh'] = up_m['Profit_i']/up_m['Energy_p48'].replace(0, np.nan)
            up_m['AASS €/MWh'] = up_m['Profit_AASS']/up_m['Energy_p48'].replace(0, np.nan)
            
            df_table_rt5 = up_m[['Year_Month', '% p48/PBF', '% RT1/PBF', 'Profit_tr', 'Profit_AASS', 'Profit_i', 'Intras €/MWh', 'AASS €/MWh']].copy()
            df_table_rt5.columns = ['Period', '% p48/PBF', '% RT1/PBF', 'Real Time €', 'AASS €', 'Intras €', 'Intras €/MWh', 'AASS €/MWh']
            df_table_rt5['Period'] = df_table_rt5['Period'].astype(str)
            
            def format_number(num):
                if pd.isna(num): return "0.0"
                return f"{num:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")

            formatted_cells = []
            for i, row in df_table_rt5.set_index('Period').iterrows():
                formatted_row = [str(i)] 
                formatted_row.append(f'{row["% p48/PBF"]:.1f}%'.replace(".", ",")) 
                formatted_row.append(f'{row["% RT1/PBF"]:.1f}%'.replace(".", ",")) 
                for col in df_table_rt5.columns[3:]:
                    formatted_row.append(format_number(row[col])) 
                formatted_cells.append(formatted_row)

            st.markdown("##### Resumen de Métricas")
            fig_t, ax_t = plt.subplots(figsize=(12, 4))
            ax_t.axis('tight'); ax_t.axis('off')
            columns = df_table_rt5.columns.tolist()
            table = ax_t.table(cellText=formatted_cells, colLabels=columns, cellLoc='center', loc='center')
            table.auto_set_font_size(False); table.set_fontsize(12); table.scale(1.2, 1.2)
            
            for key, cell in table.get_celld().items():
                row_idx, col_idx = key
                if row_idx == 0:
                    cell.set_fontsize(14); cell.set_text_props(color='#262f3a', fontweight='bold')
                    cell.set_facecolor('#40466e'); cell.set_height(0.15)
                else:
                    cell.set_fontsize(12); cell.set_text_props(color='#2d3a4b')
                    cell.set_facecolor('#f9f9f9' if row_idx % 2 == 0 else '#f1f1f2'); cell.set_height(0.1)
            st.pyplot(fig_t)

            # WATERFALL CHART
            st.markdown("##### Distribución del Profit (€/MWh)")
            cols_to_wf = ['Profit_p48','Profit_rt','Profit_tr','Profit_t','Profit_rr','Profit_b','Profit_se','Profit_i','Energy_p48', 'Energy_tr']
            df_wf = up[[c for c in cols_to_wf if c in up.columns]].sum(numeric_only=True)
            
            div_energy = df_wf.get('Energy_p48', 0) - df_wf.get('Energy_tr', 0)
            
            if div_energy > 0:
                wf_data = pd.DataFrame({
                    'Market': ['Spot', 'RRTT Ph2', 'Tertiary', 'RR', 'Sec. Band', 'Sec. Energy', 'Intras'],
                    'Values': [df_wf.get('Profit_p48',0)/div_energy, df_wf.get('Profit_rt',0)/div_energy, df_wf.get('Profit_t',0)/div_energy, 
                               df_wf.get('Profit_rr',0)/div_energy, df_wf.get('Profit_b',0)/div_energy, df_wf.get('Profit_se',0)/div_energy, df_wf.get('Profit_i',0)/div_energy]
                })
                # Sumamos el total
                wf_data.loc[len(wf_data)] = ['TOTAL', wf_data['Values'].sum()]
                
                fig_w, ax_w = plt.subplots(figsize=(10,5))
                altura_actual = wf_data['Values'][0]
                ax_w.bar(wf_data['Market'][0], wf_data['Values'][0], color='#add8e6', label='Inicio')
                ax_w.text(wf_data['Market'][0], wf_data['Values'][0], f"{wf_data['Values'][0]:.1f}", ha='center', va='center')
                
                for i in range(1, len(wf_data) - 1):
                    val = wf_data['Values'][i]
                    color = '#32cd32' if val > 0 else '#ff0000'
                    altura_anterior = altura_actual
                    altura_actual += val
                    ax_w.bar(wf_data['Market'][i], val, bottom=altura_anterior, color=color)
                    ax_w.text(wf_data['Market'][i], altura_actual, f"{val:.1f}", ha='center', va='center')
                    
                ax_w.bar(wf_data['Market'].iloc[-1], wf_data['Values'].iloc[-1], color='#5f9ea0', label='Final')
                ax_w.text(wf_data['Market'].iloc[-1], wf_data['Values'].iloc[-1], f"{wf_data['Values'].iloc[-1]:.1f}", ha='center', va='center')
                
                plt.xticks(rotation=45); ax_w.set_ylabel('€/MWh')
                ax_w.set_title(f"{ma_rt5} - {tech_rt5} Profit")
                st.pyplot(fig_w)

            # GRÁFICO EVOLUCIÓN POR HORA
            st.markdown("##### Evolución por Hora")
            up_h = up.groupby('hour').sum(numeric_only=True).reset_index()
            column_labels = {'PBF': 'PBF', 'Energy_p48': 'P48', 'Energy_i': 'Intras', 'Energy_AASS': 'AASS', 'Energy_tr': 'RT5'}
            fig_h, ax_h = plt.subplots(figsize=(10, 6))
            for col_id, col_name in column_labels.items():
                if col_id in up_h.columns:
                    ax_h.plot(up_h['hour'].astype(str), up_h[col_id], label=col_name)
            ax_h.set_ylabel('MW')
            ax_h.legend(loc='upper center', bbox_to_anchor=(0.5, 1.085), ncol=5)
            st.pyplot(fig_h)

    except Exception as e:
        st.warning(f"Error procesando pestaña RT5: {e}")


# ==============================================================================
# PESTAÑA 3: ANÁLISIS GNERA
# ==============================================================================
with tab_gnera:
    st.subheader("Análisis Gnera")
    try:
        POTENCIA_INSTALADA = {'EOTMR': 87.6, 'LECDE': 9.6, 'PEVER': 182.3, 'PEVER2': 29.8}
        UPS_INTERES = list(POTENCIA_INSTALADA.keys())
        PROFIT_MAP = {'Profit_rt': 'RRTT F2', 'Profit_tr': 'RT5', 'Profit_tr_s': 'RT5_strategy', 
                      'Profit_t': 'Tertiary', 'Profit_rr': 'RR', 'Profit_b': 'Sec. Band', 'Profit_se': 'Sec. Activation'}
        
        gnwi = allh[(allh['MA'] == 'GNERA') & (allh['Tech'] == 'Wind') & (allh['UP'].isin(UPS_INTERES))].copy()
        
        if gnwi.empty:
            st.info("No hay datos de GNERA Wind para las instalaciones seleccionadas en este mes.")
        else:
            profit_cols_to_sum = list(PROFIT_MAP.keys())
            gnwi['Profit_Total_Extra'] = gnwi[[c for c in profit_cols_to_sum if c in gnwi.columns]].sum(axis=1)
            gnwi['Potencia_MW'] = gnwi['UP'].map(POTENCIA_INSTALADA)
            
            # Tabla numérica agregada (Se usa internamente para el Heatmap, no se imprime como tabla aburrida)
            df_agg_gnera = gnwi.groupby('UP')[[c for c in profit_cols_to_sum if c in gnwi.columns] + ['Profit_Total_Extra']].sum(numeric_only=True).reset_index()
            df_agg_gnera['Potencia_MW'] = df_agg_gnera['UP'].map(POTENCIA_INSTALADA)
            
            cols_to_normalize = [c for c in profit_cols_to_sum if c in df_agg_gnera.columns] + ['Profit_Total_Extra']
            for col in cols_to_normalize:
                df_agg_gnera[f'{col}_eur_per_MW'] = df_agg_gnera[col] / df_agg_gnera['Potencia_MW']
            
            rename_map_num = {f'{col}_eur_per_MW': f"{PROFIT_MAP.get(col, 'Profit_Total_Extra')} (€/MW)" for col in cols_to_normalize}
            df_report_num = df_agg_gnera[['UP'] + [f'{col}_eur_per_MW' for col in cols_to_normalize]].rename(columns=rename_map_num)

            # =========================================================
            # 1. MOVER HEATMAP AL PRINCIPIO
            # =========================================================
            st.markdown("##### Resumen (€/MW) como Heatmap")
            df_heatmap = df_report_num.set_index('UP')
            df_heatmap.columns = [col.replace(' (€/MW)', '') for col in df_heatmap.columns]
            
            if 'Profit_Total_Extra' in df_heatmap.columns:
                df_heatmap_components = df_heatmap.drop(columns='Profit_Total_Extra')
                df_heatmap_total = df_heatmap[['Profit_Total_Extra']]
            else:
                df_heatmap_components = df_heatmap
                df_heatmap_total = pd.DataFrame()

            fig_hm, (ax_heat, ax_total) = plt.subplots(1, 2, figsize=(22, 10), gridspec_kw={'width_ratios': [max(1, df_heatmap_components.shape[1]), 1]})
            sns.heatmap(df_heatmap_components, annot=True, fmt=',.2f', cmap='vlag', center=0, linewidths=.5, annot_kws={"size": 16}, ax=ax_heat)
            ax_heat.set_title(''); ax_heat.set_ylabel(''); ax_heat.set_xlabel('')
            plt.setp(ax_heat.get_xticklabels(), rotation=45, ha="right", fontsize=16)
            
            if not df_heatmap_total.empty:
                sns.heatmap(df_heatmap_total, annot=True, fmt=',.2f', cmap='RdYlGn', center=df_heatmap_total.mean().values[0], linewidths=.5, annot_kws={"size": 16, "weight": "bold"}, cbar=False, ax=ax_total)
                ax_total.set_title('Total', fontsize=16); ax_total.set_yticks([]); ax_total.set_xlabel('')
            st.pyplot(fig_hm)

            # =========================================================
            # 2. GRÁFICOS DE EVOLUCIÓN DEBAJO
            # =========================================================
            st.markdown("##### Evolución Diaria del Profit Total Normalizado (€/MW)")
            gnwi['Profit_Total_eur_per_MW'] = gnwi['Profit_Total_Extra'].div(gnwi['Potencia_MW']).fillna(0)
            df_hourly_norm_total = gnwi.groupby(['UP', 'hour'])['Profit_Total_eur_per_MW'].sum().reset_index()
            
            fig_evo, ax_evo = plt.subplots(figsize=(15, 8))
            sns.lineplot(data=df_hourly_norm_total, x='hour', y='Profit_Total_eur_per_MW', hue='UP', style='UP', markers=True, dashes=False, ax=ax_evo)
            ax_evo.set_ylabel('Profit Total Acumulado por hora (€/MW)', fontsize=12)
            ax_evo.set_xlabel('Hora del Día', fontsize=12)
            ax_evo.grid(True, linestyle='--', alpha=0.6); ax_evo.axhline(0, color='black', linewidth=0.8)
            ax_evo.set_xticks(range(0, 24))
            st.pyplot(fig_evo)

            # Áreas Apiladas (Subplots)
            st.markdown("##### Áreas Apiladas de Profit por Hora (€/MW)")
            norm_profit_cols = []
            for col in [c for c in profit_cols_to_sum if c in gnwi.columns]:
                norm_col_name = f"{col}_norm_mw"
                gnwi[norm_col_name] = gnwi[col].div(gnwi['Potencia_MW'].replace(0, np.nan)).fillna(0)
                norm_profit_cols.append(norm_col_name)

            df_hourly_breakdown = gnwi.groupby(['UP', 'hour'])[norm_profit_cols].sum().reset_index()
            fig_stack, axes_stack = plt.subplots(2, 2, figsize=(20, 14), sharex=True, sharey=True)
            axes_stack = axes_stack.flatten()
            market_labels = [PROFIT_MAP.get(c.replace('_norm_mw',''), c) for c in norm_profit_cols]
            colors = plt.cm.get_cmap('tab20c', len(market_labels))
            
            for i, up in enumerate(UPS_INTERES):
                ax = axes_stack[i]
                df_plot = df_hourly_breakdown[df_hourly_breakdown['UP'] == up]
                if df_plot.empty:
                    ax.set_title(f'{up}\n(No data)', fontsize=14)
                    continue
                x = df_plot['hour']
                y_values = [df_plot[col] for col in norm_profit_cols]
                ax.stackplot(x, y_values, labels=market_labels, colors=colors.colors, alpha=0.8)
                ax.set_title(f'Desglose Profit por Hora: {up} (€/MW)', fontsize=16)
                ax.set_ylabel('Profit Acumulado por hora (€/MW)', fontsize=12)
                ax.grid(True, linestyle='--', alpha=0.6); ax.axhline(0, color='black', linewidth=0.8, linestyle='--')
                ax.set_xticks(range(0, 24))
            
            handles, labels = ax.get_legend_handles_labels()
            fig_stack.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 0.98), ncol=min(4, len(market_labels)), fontsize=13, title="Mercados")
            st.pyplot(fig_stack)

            # Evolución PBF vs Energy_p48
            st.markdown("##### Evolución Horaria PBF vs Energy_p48 (% del Máximo PBF)")
            df_hourly_energy = gnwi.groupby(['UP', 'hour'])[['PBF', 'Energy_p48']].sum(numeric_only=True).reset_index()
            max_pbf_values = df_hourly_energy.groupby('UP')['PBF'].transform('max').replace(0, np.nan)
            
            df_norm = pd.DataFrame(index=df_hourly_energy.index)
            df_norm['PBF'] = df_hourly_energy['PBF'].div(max_pbf_values).fillna(0)
            df_norm['Energy_p48'] = df_hourly_energy['Energy_p48'].div(max_pbf_values).fillna(0)
            df_norm[['UP', 'hour']] = df_hourly_energy[['UP', 'hour']]
            
            df_melted = df_norm.melt(id_vars=['UP', 'hour'], value_vars=['PBF', 'Energy_p48'], var_name='Metrica', value_name='Valor (% del Máximo PBF)')
            
            fig_en, axes_en = plt.subplots(2, 2, figsize=(18, 12), sharex=True, sharey=True)
            axes_en = axes_en.flatten()
            for i, up in enumerate(UPS_INTERES):
                ax = axes_en[i]
                df_plot = df_melted[df_melted['UP'] == up]
                if df_plot.empty:
                    ax.set_title(f'{up}\n(No data)', fontsize=14); continue
                sns.lineplot(data=df_plot, x='hour', y='Valor (% del Máximo PBF)', hue='Metrica', style='Metrica', markers=True, dashes=False, ax=ax)
                ax.set_title(f'Evolución Horaria Normalizada (vs Max PBF): {up}', fontsize=16)
                ax.yaxis.set_major_formatter(FuncFormatter(lambda y, p: f'{y * 100:.0f}%'))
                ax.grid(True, linestyle='--', alpha=0.6); ax.set_xticks(range(0, 24))
            st.pyplot(fig_en)

    except Exception as e:
        st.warning(f"Error procesando Análisis Gnera: {e}")

# ==============================================================================
# PESTAÑA 4: BENEFICIO VERBUND (TABLA GIGANTE MATPLOTLIB)
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
        selected_ups_v = list(INPUT_DATA.keys())
        installation_names = [val[0] for val in INPUT_DATA.values()]
        potencias_vector = [val[1] for val in INPUT_DATA.values()]
        verbund_percentages = [val[2] for val in INPUT_DATA.values()]
        
        profit_cols = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se', 'Profit_i']
        col_mapping = {'Profit_rt': 'RRTT F2', 'Profit_tr_s': 'RT5\nStrategy', 'Profit_t': 'Tertiary', 'Profit_rr': 'RR', 'Profit_b': 'Sec.\nBand', 'Profit_se': 'Sec.\nActivation', 'Profit_i': 'Intraday'}
        
        df_v = allh[allh['UP'].isin(selected_ups_v)].copy()
        for col in profit_cols:
            if col not in df_v.columns: df_v[col] = 0
            
        df_agg_v = df_v.groupby('UP')[profit_cols].sum(numeric_only=True).reindex(selected_ups_v).reset_index().fillna(0)
        df_agg_v['Total Profit'] = df_agg_v[profit_cols].sum(axis=1)
        df_agg_v['Verbund_Pct'] = verbund_percentages
        df_agg_v['Profit Verbund'] = df_agg_v['Total Profit'] * df_agg_v['Verbund_Pct']
        df_agg_v['Potencia MW'] = potencias_vector
        df_agg_v['Profit Verbund / MW'] = df_agg_v['Profit Verbund'] / df_agg_v['Potencia MW']
        
        total_profits = df_agg_v[profit_cols].sum(numeric_only=True)
        sum_total_profit = df_agg_v['Total Profit'].sum()
        sum_profit_verbund = df_agg_v['Profit Verbund'].sum()
        sum_potencia_mw = df_agg_v['Potencia MW'].sum()
        total_verbund_per_mw_weighted = sum_profit_verbund / sum_potencia_mw if sum_potencia_mw > 0 else 0
        
        total_row = pd.Series(index=df_agg_v.columns, dtype=object)
        total_row['UP'] = 'Total'
        for col in profit_cols: total_row[col] = total_profits[col]
        total_row['Total Profit'] = sum_total_profit
        total_row['Profit Verbund'] = sum_profit_verbund
        total_row['Profit Verbund / MW'] = total_verbund_per_mw_weighted
        
        df_agg_v = pd.concat([df_agg_v, total_row.to_frame().T], ignore_index=True)
        
        mask_not_total = df_agg_v['UP'] != 'Total'
        df_agg_v.loc[mask_not_total, 'Installation'] = installation_names
        df_agg_v.loc[~mask_not_total, 'Installation'] = 'Total'
        
        df_agg_v = df_agg_v.rename(columns=col_mapping).rename(columns={'Total Profit': 'Total\nProfit', 'Profit Verbund': 'Profit\nVerbund', 'Profit Verbund / MW': 'Profit\nVerbund\n€/MW'})
        cols_finales = ['Installation'] + list(col_mapping.values()) + ['Total\nProfit', 'Profit\nVerbund', 'Profit\nVerbund\n€/MW']
        df_table = df_agg_v[cols_finales]
        
        # TABLA MATPLOTLIB
        fig_verb, ax_verb = plt.subplots(figsize=(22, (len(selected_ups_v) + 1) * 1.5 + 5)) 
        ax_verb.axis('tight'); ax_verb.axis('off')
        
        cell_text = []
        for row in df_table.values:
            formatted_row = [row[0]]
            for val in row[1:]: formatted_row.append(f"{float(val):,.2f}")
            cell_text.append(formatted_row)
            
        the_table = ax_verb.table(cellText=cell_text, colLabels=df_table.columns, loc='center', cellLoc='center')
        the_table.auto_set_font_size(False); the_table.set_fontsize(18); the_table.scale(1.0, 3.5)
        
        for (row, col), cell in the_table.get_celld().items():
            if row == 0:
                cell.set_text_props(weight='bold', color='white', fontsize=18); cell.set_facecolor('#40466e'); cell.set_height(0.3)
            else:
                cell.set_height(0.22) 
                if row == len(df_table): cell.set_text_props(weight='bold'); cell.set_facecolor('#d9d9d9')
                elif row % 2 == 0: cell.set_facecolor('#f2f2f2')
                else: cell.set_facecolor('white')
                if col == 0 or col >= len(cols_finales) - 3: cell.set_text_props(weight='bold')

        title_text = f"Ancillary Services Profits by Installation (€)\n{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
        plt.subplots_adjust(left=0.05, right=0.95, top=0.60, bottom=0.05)
        plt.suptitle(title_text, fontsize=24, weight='bold', y=0.82)
        st.pyplot(fig_verb)
        
    except Exception as e:
        st.warning(f"Error procesando tabla Verbund: {e}")

# ==============================================================================
# PESTAÑA 5: EVOLUCIÓN INGRESOS
# ==============================================================================
with tab_evo:
    st.subheader("Evolución Ingresos por Representante y Tecnología")
    try:
        col_e1, col_e2 = st.columns(2)
        with col_e1: ma_input = st.selectbox("Market Agent (MA):", sorted(allh['MA'].unique()), index=list(sorted(allh['MA'].unique())).index('GALP') if 'GALP' in allh['MA'].unique() else 0)
        with col_e2: tech_input = st.selectbox("Tecnología (Tech):", sorted(allh['Tech'].unique()), index=list(sorted(allh['Tech'].unique())).index('Wind') if 'Wind' in allh['Tech'].unique() else 0)
        
        df_evo = allh[(allh['MA'] == ma_input) & (allh['Tech'] == tech_input)].copy()
        
        if df_evo.empty:
            st.info("No hay datos para esta combinación de MA y Tech.")
        else:
            df_evo['YearMonth'] = df_evo['Day'].dt.to_period('M').astype(str)
            if aass_sel == 'no_sec': aass_sel0 = ['Profit_rt', 'Profit_tr_s','Profit_t', 'Profit_rr']
            elif aass_sel == 'sec': aass_sel0 = ['Profit_b', 'Profit_se']
            else: aass_sel0 = ['Profit_rt', 'Profit_tr_s', 'Profit_t', 'Profit_rr', 'Profit_b', 'Profit_se']
            
            df_evo['Total_Profit'] = df_evo[[c for c in aass_sel0 if c in df_evo.columns]].sum(axis=1)
            
            grouped_evo = df_evo.groupby(['UP', 'YearMonth']).agg(
                Total_Profit=('Total_Profit', 'sum'),
                Total_Energy=('Energy_p48', 'sum') if 'Energy_p48' in df_evo.columns else ('Total_Profit', 'count')
            ).reset_index().sort_values('YearMonth')
            
            grouped_evo['Profit_per_MWh'] = grouped_evo['Total_Profit'] / grouped_evo['Total_Energy'].replace(0, np.nan)
            grouped_evo['Total_Profit_k'] = grouped_evo['Total_Profit'] / 1000

            st.markdown("##### 1. Evolution of Profit in €/MWh")
            fig_e1, ax_e1 = plt.subplots(figsize=(12, 8))
            sns.lineplot(data=grouped_evo, x='YearMonth', y='Profit_per_MWh', hue='UP', marker='o', ax=ax_e1)
            ax_e1.set_title(f'Evolution of Profit in €/MWh per Month and Year\nMA: {ma_input}, Tech: {tech_input}')
            ax_e1.set_xlabel('Month and Year'); ax_e1.set_ylabel('Profit in €/MWh')
            ax_e1.tick_params(axis='x', rotation=45); ax_e1.grid(True)
            st.pyplot(fig_e1)

            st.markdown("##### 2. Evolution of Production in MWh")
            fig_e2, ax_e2 = plt.subplots(figsize=(12, 8))
            sns.lineplot(data=grouped_evo, x='YearMonth', y='Total_Energy', hue='UP', marker='o', ax=ax_e2)
            ax_e2.set_title(f'Evolution of Production in MWh per Month and Year\nMA: {ma_input}, Tech: {tech_input}')
            ax_e2.set_xlabel('Month and Year'); ax_e2.set_ylabel('Production MWh')
            ax_e2.tick_params(axis='x', rotation=45); ax_e2.grid(True)
            st.pyplot(fig_e2)

            st.markdown("##### 3. Evolution of Profit in k€")
            fig_e3, ax_e3 = plt.subplots(figsize=(12, 8))
            sns.lineplot(data=grouped_evo, x='YearMonth', y='Total_Profit_k', hue='UP', marker='o', ax=ax_e3)
            ax_e3.set_title(f'Evolution of Profit in k€ per Month and Year\nMA: {ma_input}, Tech: {tech_input}')
            ax_e3.set_xlabel('Month and Year'); ax_e3.set_ylabel('Profit k€')
            ax_e3.tick_params(axis='x', rotation=45); ax_e3.grid(True)
            st.pyplot(fig_e3)

    except Exception as e:
        st.warning(f"Error procesando la pestaña Evolución Ingresos: {e}")
