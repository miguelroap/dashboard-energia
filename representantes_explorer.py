"""
═══════════════════════════════════════════════════════════════════════════════
  representantes_explorer.py
  Módulo de comparación de OFERTAS de representantes (curvas pay-as-bid) para app.py

  Lee directamente de las 11 tablas BigQuery `i90_diaXX_*offer*_raw`
  (pieza `ofertas-fetch-data`). NO usa los parquets allh ni los i90rrtt.

  Patrón de integración: inyección de dependencias, igual que unit_explorer.py.
  En app.py:

      import representantes_explorer as rep
      rep.render(
          bq_client = get_bq_client(),          # google.cloud.bigquery.Client ya autenticado
          project   = "miguel-energia",
          dataset   = "red_electrica_data",
          up_master = load_up_master_df(),       # DataFrame del maestro de UPs (opcional)
          fmt       = fmt_num,                    # helper de formato (opcional)
      )

  Si no tienes un cliente BQ a mano, el módulo lo crea desde
  st.secrets["gcp_service_account"] (mismo secreto que gcs_loader.py).

  ── QUÉ COMPARA ──────────────────────────────────────────────────────────────
  Para cada representante (Sujeto del Mercado) y mercado seleccionado, agrega
  su curva de oferta en el período y deriva métricas COMPARABLES entre reps:

    · MW ofertado total / medio        (capacidad que pone en el mercado)
    · €/MWh ofertado ponderado por MW  (lo caro/barato que es — precio real)
    · €/MWh mínimo y máximo            (rango de su curva: agresividad del B1)
    · Nº de bloques medio              (granularidad de la curva)
    · Nº de UPs activas                (amplitud de cartera)
    · % horas con oferta               (constancia / disponibilidad)
    · Spread Subir-Bajar               (sesgo direccional, donde aplique)

  El precio ponderado por MW es la métrica clave: comparar el €/MWh "a pelo"
  engaña porque un bloque de 1 MW a 500 €/MWh pesa lo mismo que 200 MW a 20.

  ── INTÉRPRETE IA (patrón B, con A preparado) ────────────────────────────────
  build_ai_payload() arma un resumen estructurado (markdown + JSON) compacto:
  NO manda las 96·N·bloques series crudas, manda las métricas agregadas + el
  contexto de mercado/período. Eso es lo que pegas en un chat con Claude.
  Para activar el botón-API (patrón A) hay un hueco marcado `# === API HOOK ===`.
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import datetime as dt
from textwrap import dedent

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px


# ══════════════════════════════════════════════════════════════════════════════
#  CATÁLOGO DE MERCADOS  (qué tablas, qué entidad, qué lado)
# ══════════════════════════════════════════════════════════════════════════════
# Cada mercado declara las tablas BQ de MW y de precio. Para hojas interleaved
# (13/15/38) MW y precio viven en la MISMA tabla (VALUE_MW + VALUE_EUR).
# Para hojas simples (17/22/41/23/32/31/42/24) MW y precio están en tablas
# distintas que hay que cruzar por las dimensiones comunes.
#
# entity:  'UP' → filtra por ENTITY ∈ UPs del SM ;  'PM' → filtra por ENTITY = código PM I90
# price_unit: etiqueta para la UI (€/MWh salvo banda secundaria = €/MW)

MARKETS = {
    "rrtt_pdbf_sub": {
        "label": "RRTT PDBF · Subir",
        "entity": "UP",
        "interleaved": False,
        "mw_table": "i90_dia17_rrtt_pdbf_offer_up_mw_raw",
        "pr_table": "i90_dia22_rrtt_pdbf_offer_up_price_raw",
        "side": "Subir",
        "price_unit": "€/MWh",
    },
    "rrtt_pdbf_baj": {
        "label": "RRTT PDBF · Bajar",
        "entity": "UP",
        "interleaved": False,
        "mw_table": "i90_dia41_rrtt_pdbf_offer_dn_mw_raw",
        "pr_table": "i90_dia23_rrtt_pdbf_offer_dn_price_raw",
        "side": "Bajar",
        "price_unit": "€/MWh",
    },
    "rrtt_tr_sub": {
        "label": "RRTT TR (RT5) · Subir",
        "entity": "UP",
        "interleaved": False,
        "mw_table": "i90_dia32_rrtt_tr_offer_up_mw_raw",
        "pr_table": "i90_dia31_rrtt_tr_offer_up_price_raw",
        "side": "Subir",
        "price_unit": "€/MWh",
    },
    "rrtt_tr_baj": {
        "label": "RRTT TR (RT5) · Bajar",
        "entity": "UP",
        "interleaved": False,
        "mw_table": "i90_dia42_rrtt_tr_offer_dn_mw_raw",
        "pr_table": "i90_dia24_rrtt_tr_offer_dn_price_raw",
        "side": "Bajar",
        "price_unit": "€/MWh",
    },
    "terciaria": {
        "label": "Terciaria / mFRR (por bloque)",
        "entity": "UP",
        "interleaved": True,
        "mw_table": "i90_dia15_tertiary_offer_raw",
        "pr_table": "i90_dia15_tertiary_offer_raw",
        "side": None,                       # trae ambos sentidos en OFFER_SIDE
        "price_unit": "€/MWh",
    },
    "banda_sec": {
        "label": "Banda secundaria (por bloque)",
        "entity": "PM",
        "interleaved": True,
        "mw_table": "i90_dia13_secondary_band_offer_raw",
        "pr_table": "i90_dia13_secondary_band_offer_raw",
        "side": None,
        "price_unit": "€/MW",               # OJO: banda es €/MW, no €/MWh
    },
    "energia_sec": {
        "label": "Energía secundaria (por bloque)",
        "entity": "PM",
        "interleaved": True,
        "mw_table": "i90_dia38_secondary_energy_offer_raw",
        "pr_table": "i90_dia38_secondary_energy_offer_raw",
        "side": None,
        "price_unit": "€/MWh",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
#  CLIENTE BQ  (si app.py no inyecta uno)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _default_bq_client(project: str):
    """Crea un cliente BQ desde st.secrets, mismo secreto que gcs_loader.py."""
    from google.cloud import bigquery
    from google.oauth2 import service_account
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(project=project, credentials=creds)


# ══════════════════════════════════════════════════════════════════════════════
#  RESOLUCIÓN DE ENTIDADES POR REPRESENTANTE
# ══════════════════════════════════════════════════════════════════════════════
# Para mercados UP: necesito las UPs de cada SM.
# Para mercados PM: necesito el código Participante I90 (GNE), NO el SM2 (GNRA).
#
# Fuente preferida: el maestro de UPs (programming_units_external_table_latest),
# que app.py ya carga. Si no se inyecta, lo leo de BQ.

@st.cache_data(ttl=3600)
def _load_up_master_bq(project: str, dataset: str):
    client = _default_bq_client(project)
    sql = f"""
        SELECT UP, Descrip_Long, Power_MW, Tech, Buy_Sell,
               Regulation_Zone, Sujeto_del_Mercado AS SM,
               Sujeto_del_Mercado_2 AS SM2, RZ
        FROM `{project}.{dataset}.programming_units_external_table_latest`
    """
    return client.query(sql).to_dataframe()


def _normalize_master(df: pd.DataFrame) -> pd.DataFrame:
    """Acepta el maestro venga de app.py o de BQ; homogeneiza nombres."""
    if df is None:
        return None
    ren = {
        "Sujeto del Mercado": "SM", "Sujeto_del_Mercado": "SM",
        "Sujeto del Mercado 2": "SM2", "Sujeto_del_Mercado_2": "SM2",
        "Power MW": "Power_MW", "Buy-Sell": "Buy_Sell",
        "Regulation Zone": "Regulation_Zone",
    }
    df = df.rename(columns={k: v for k, v in ren.items() if k in df.columns})
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  QUERIES BQ  (agregación en el servidor — barato y rápido)
# ══════════════════════════════════════════════════════════════════════════════
# Estrategia: agregar en BQ a nivel (ENTITY, BLOCK, OFFER_SIDE) sumando MW y
# promediando precio sobre el período, y traer ya agregado. Las métricas finas
# por QH no se bajan (no las necesitamos para COMPARAR reps).
#
# Higiene de coste (contexto §3-ter): siempre WHERE de fecha, filtro de ENTITY,
# nunca SELECT *.

def _q_simple_market(client, project, dataset, mkt, entities, d_ini, d_fin):
    """
    Mercado de hojas simples (MW y precio en tablas distintas).
    Cruza MW↔precio por (ENTITY, BLOCK, OFFER_SIDE) y devuelve, por bloque,
    MW total ofertado (Σ sobre QH·días) y precio medio ponderado por MW.
    """
    mw_t, pr_t = mkt["mw_table"], mkt["pr_table"]
    side = mkt["side"]
    ent_list = ",".join(f"'{e}'" for e in entities)
    # Las hojas simples de RRTT (17/22/41/23/32/31/42/24) ya son de un único
    # sentido por tabla (Subir o Bajar), así que el filtro OFFER_SIDE es
    # redundante; lo dejamos solo si la tabla trajera ambos sentidos.
    side_filter = f"AND OFFER_SIDE = '{side}'" if side else ""

    sql = f"""
    WITH mw AS (
      SELECT ENTITY, BLOCK,
             SUM(VALUE_MW)              AS mw_sum,
             COUNT(VALUE_MW)            AS qh_count,
             COUNT(DISTINCT DELIVERY_DATE_DAY_CET) AS days
      FROM `{project}.{dataset}.{mw_t}`
      WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
        AND ENTITY IN ({ent_list})
        {side_filter}
        AND VALUE_MW IS NOT NULL
      GROUP BY ENTITY, BLOCK
    ),
    pr AS (
      SELECT ENTITY, BLOCK,
             AVG(VALUE_EUR)             AS pr_avg,
             MIN(VALUE_EUR)             AS pr_min,
             MAX(VALUE_EUR)             AS pr_max
      FROM `{project}.{dataset}.{pr_t}`
      WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
        AND ENTITY IN ({ent_list})
        {side_filter}
        AND VALUE_EUR IS NOT NULL
      GROUP BY ENTITY, BLOCK
    )
    SELECT mw.ENTITY, mw.BLOCK,
           mw.mw_sum, mw.qh_count, mw.days,
           pr.pr_avg, pr.pr_min, pr.pr_max
    FROM mw LEFT JOIN pr USING (ENTITY, BLOCK)
    """
    from google.cloud import bigquery
    job_cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
        bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin),
    ])
    return client.query(sql, job_config=job_cfg).to_dataframe()


def _q_interleaved_market(client, project, dataset, mkt, entities, d_ini, d_fin):
    """
    Mercado interleaved (MW y precio en la MISMA tabla, misma fila).
    Aquí el precio ponderado por MW se puede calcular en SQL directamente.
    """
    t = mkt["mw_table"]
    ent_list = ",".join(f"'{e}'" for e in entities)
    sql = f"""
    SELECT ENTITY, BLOCK,
           COALESCE(OFFER_SIDE,'NA')   AS side,
           SUM(VALUE_MW)               AS mw_sum,
           SAFE_DIVIDE(SUM(VALUE_MW * VALUE_EUR), SUM(VALUE_MW)) AS pr_wavg,
           MIN(VALUE_EUR)              AS pr_min,
           MAX(VALUE_EUR)              AS pr_max,
           COUNT(VALUE_MW)             AS qh_count,
           COUNT(DISTINCT DELIVERY_DATE_DAY_CET) AS days
    FROM `{project}.{dataset}.{t}`
    WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
      AND ENTITY IN ({ent_list})
      AND VALUE_MW IS NOT NULL
    GROUP BY ENTITY, BLOCK, side
    """
    from google.cloud import bigquery
    job_cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
        bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin),
    ])
    return client.query(sql, job_config=job_cfg).to_dataframe()


def dry_run_bytes(client, project, dataset, mkt, entities, d_ini, d_fin):
    """Estima bytes a escanear sin ejecutar (para el aviso de coste)."""
    from google.cloud import bigquery
    t = mkt["mw_table"]
    ent_list = ",".join(f"'{e}'" for e in entities) or "''"
    sql = f"""SELECT ENTITY FROM `{project}.{dataset}.{t}`
              WHERE DELIVERY_DATE_DAY_CET BETWEEN @d_ini AND @d_fin
                AND ENTITY IN ({ent_list})"""
    cfg = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False,
        query_parameters=[
            bigquery.ScalarQueryParameter("d_ini", "DATE", d_ini),
            bigquery.ScalarQueryParameter("d_fin", "DATE", d_fin),
        ],
    )
    job = client.query(sql, job_config=cfg)
    return job.total_bytes_processed


# ══════════════════════════════════════════════════════════════════════════════
#  CÁLCULO DE MÉTRICAS COMPARABLES POR REPRESENTANTE
# ══════════════════════════════════════════════════════════════════════════════

def _metrics_from_blocks(df_blocks: pd.DataFrame, mkt, entity_to_rep: dict) -> pd.DataFrame:
    """
    df_blocks: salida de las queries, una fila por (ENTITY, BLOCK[, side]).
    entity_to_rep: mapea cada ENTITY (UP o PM) a su representante (SM).
    Devuelve una fila por representante con las métricas comparables.
    """
    if df_blocks is None or df_blocks.empty:
        return pd.DataFrame()

    df = df_blocks.copy()
    df["rep"] = df["ENTITY"].map(entity_to_rep).fillna(df["ENTITY"])

    # Precio ponderado por MW a nivel bloque:
    if "pr_wavg" in df.columns:                     # interleaved: ya viene
        df["pr_w"] = df["pr_wavg"]
    else:                                           # simple: pondero con pr_avg
        df["pr_w"] = df["pr_avg"]

    rows = []
    for rep, g in df.groupby("rep"):
        mw_total = g["mw_sum"].sum(skipna=True)
        # precio ponderado por MW a nivel representante
        valid = g.dropna(subset=["pr_w"])
        if valid["mw_sum"].sum() > 0:
            pr_wavg = (valid["pr_w"] * valid["mw_sum"]).sum() / valid["mw_sum"].sum()
        else:
            pr_wavg = valid["pr_w"].mean()
        rows.append({
            "Representante": rep,
            "MW ofertado (Σ)": round(float(mw_total), 1) if pd.notna(mw_total) else 0.0,
            f"Precio pond. ({mkt['price_unit']})": round(float(pr_wavg), 2) if pd.notna(pr_wavg) else None,
            f"Precio mín": round(float(g["pr_min"].min()), 2) if g["pr_min"].notna().any() else None,
            f"Precio máx": round(float(g["pr_max"].max()), 2) if g["pr_max"].notna().any() else None,
            "Nº bloques (medio)": round(float(g.groupby("ENTITY")["BLOCK"].nunique().mean()), 1),
            "Nº entidades": int(g["ENTITY"].nunique()),
            "QH con oferta (Σ)": int(g["qh_count"].sum()),
            "Días con datos": int(g["days"].max()) if "days" in g else None,
        })
    out = pd.DataFrame(rows).sort_values("MW ofertado (Σ)", ascending=False).reset_index(drop=True)
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  PAYLOAD PARA IA  (patrón B; reusable por patrón A)
# ══════════════════════════════════════════════════════════════════════════════

def build_ai_payload(metrics: pd.DataFrame, mkt, d_ini, d_fin, reps_sel) -> dict:
    """
    Resumen estructurado y COMPACTO para mandar a un LLM.
    No incluye series por QH: solo el agregado por representante + contexto.
    """
    context = {
        "mercado": mkt["label"],
        "unidad_precio": mkt["price_unit"],
        "periodo": {"inicio": str(d_ini), "fin": str(d_fin)},
        "representantes_comparados": list(reps_sel),
        "nota_metrica": (
            "El 'Precio pond.' es el €/(MW·h o MW) ponderado por MW ofertado, "
            "no la media simple de la curva. Comparar precios sin ponderar engaña."
        ),
        "tabla": metrics.to_dict(orient="records"),
    }
    return context


def payload_to_markdown(payload: dict) -> str:
    """Versión legible para copiar-pegar en un chat."""
    md = [f"# Comparación de ofertas de representantes",
          f"**Mercado:** {payload['mercado']}  ·  **Período:** "
          f"{payload['periodo']['inicio']} → {payload['periodo']['fin']}",
          f"**Unidad de precio:** {payload['unidad_precio']}", ""]
    md.append(f"_{payload['nota_metrica']}_\n")
    if payload["tabla"]:
        cols = list(payload["tabla"][0].keys())
        md.append("| " + " | ".join(cols) + " |")
        md.append("| " + " | ".join("---" for _ in cols) + " |")
        for r in payload["tabla"]:
            md.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    md.append("")
    md.append(dedent("""\
        ---
        **Pregunta para la IA:** Interpreta esta comparación de ofertas en el mercado
        de balancing español. En concreto:
        1. ¿Qué representante oferta más agresivo en precio y cuál más conservador?
        2. ¿Alguno pone mucha capacidad (MW) pero a precio alto, o poca a precio bajo?
        3. ¿El número de bloques/entidades sugiere estrategias de curva distintas?
        4. Señales de poder de mercado o de ubicación en zona de regulación poco
           competida (precio alto que aun así casaría).
        5. Qué mirarías después para confirmar cada hipótesis."""))
    return "\n".join(md)


# === API HOOK ===  (patrón A: descomentar y poner ANTHROPIC_API_KEY como secreto)
def call_claude_api(payload: dict) -> str:
    """
    Patrón A. Requiere `anthropic` instalado y st.secrets['ANTHROPIC_API_KEY'].
    Verifica que el egress a api.anthropic.com esté permitido tras el VPN corporativo.
    """
    import anthropic
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    prompt = payload_to_markdown(payload)
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


# ══════════════════════════════════════════════════════════════════════════════
#  GRÁFICOS
# ══════════════════════════════════════════════════════════════════════════════

def _fig_scatter(metrics: pd.DataFrame, mkt):
    """MW ofertado (x) vs precio ponderado (y): mapa competitivo de un vistazo."""
    pr_col = f"Precio pond. ({mkt['price_unit']})"
    if metrics.empty or pr_col not in metrics:
        return None
    fig = px.scatter(
        metrics, x="MW ofertado (Σ)", y=pr_col,
        text="Representante", size="Nº entidades",
        color="Representante",
        labels={"MW ofertado (Σ)": "MW ofertado (Σ período)",
                pr_col: f"Precio ponderado ({mkt['price_unit']})"},
    )
    fig.update_traces(textposition="top center")
    fig.update_layout(
        template="plotly_dark", height=420, showlegend=False,
        title=f"Mapa competitivo — {mkt['label']}",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def _fig_bars(metrics: pd.DataFrame, mkt):
    """Barras de MW y precio lado a lado."""
    pr_col = f"Precio pond. ({mkt['price_unit']})"
    if metrics.empty:
        return None
    fig = go.Figure()
    fig.add_bar(x=metrics["Representante"], y=metrics["MW ofertado (Σ)"],
                name="MW ofertado (Σ)", yaxis="y1")
    if pr_col in metrics:
        fig.add_scatter(x=metrics["Representante"], y=metrics[pr_col],
                        name=f"Precio pond. ({mkt['price_unit']})",
                        mode="markers+lines", yaxis="y2",
                        marker=dict(size=11))
    fig.update_layout(
        template="plotly_dark", height=400,
        title=f"MW vs precio por representante — {mkt['label']}",
        yaxis=dict(title="MW ofertado (Σ)"),
        yaxis2=dict(title=f"Precio ({mkt['price_unit']})", overlaying="y",
                    side="right", showgrid=False),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", y=1.12),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  RENDER  (lo que llamas desde app.py)
# ══════════════════════════════════════════════════════════════════════════════

def render(bq_client=None, project="miguel-energia",
           dataset="red_electrica_data", up_master=None, fmt=None,
           pm_map=None):
    """
    pm_map: dict {SM2_o_SM: codigo_PM_I90} para mercados de Participante (banda/energía
            secundaria). Ej: {'GNERA':'GNE','AXPO IBERIA':'AXP'}. Si None, intenta usar
            el propio SM como código PM (probablemente incorrecto → avisa).
    """
    st.header("🏛️ Comparador de ofertas de representantes")
    st.caption("Curvas de oferta pay-as-bid desde BigQuery (pieza `ofertas-fetch-data`). "
               "Compara cómo ofertan distintos Sujetos del Mercado en cada mercado de balancing.")

    client = bq_client or _default_bq_client(project)

    # ── Maestro de UPs ───────────────────────────────────────────────
    master = _normalize_master(up_master) if up_master is not None \
        else _normalize_master(_load_up_master_bq(project, dataset))
    if master is None or master.empty:
        st.error("No se pudo cargar el maestro de UPs.")
        return

    sm_options = sorted(master["SM"].dropna().unique().tolist())

    # ── Controles ────────────────────────────────────────────────────
    c1, c2 = st.columns([2, 1])
    with c1:
        reps_sel = st.multiselect(
            "Representantes a comparar (Sujeto del Mercado)",
            sm_options,
            default=sm_options[:3] if len(sm_options) >= 3 else sm_options,
            help="Elige 2+ para comparar. Cada uno agrupa todas sus UPs (o su código PM).",
        )
    with c2:
        mkt_key = st.selectbox(
            "Mercado",
            list(MARKETS.keys()),
            format_func=lambda k: MARKETS[k]["label"],
        )
    mkt = MARKETS[mkt_key]

    c3, c4 = st.columns(2)
    with c3:
        d_ini = st.date_input("Desde", value=dt.date.today() - dt.timedelta(days=97))
    with c4:
        d_fin = st.date_input("Hasta", value=dt.date.today() - dt.timedelta(days=91))

    if not reps_sel:
        st.info("Selecciona al menos un representante.")
        return
    if d_ini > d_fin:
        st.error("El rango de fechas está invertido.")
        return

    # ── Resolver entidades por representante ──────────────────────────
    # Mercados UP → UPs del SM ;  Mercados PM → código PM I90.
    entity_to_rep = {}
    entities = []
    if mkt["entity"] == "UP":
        sub = master[master["SM"].isin(reps_sel)]
        for _, r in sub.iterrows():
            up = r["UP"]
            if pd.notna(up):
                entity_to_rep[up] = r["SM"]
                entities.append(up)
    else:  # PM
        if not pm_map:
            st.warning("Este mercado es de **Participante del Mercado** (banda/energía secundaria). "
                       "Necesito el mapeo SM→código PM I90 (p.ej. GNERA→GNE). "
                       "Pásalo como `pm_map=` al llamar a render(); de momento intento con el SM2.")
        for sm in reps_sel:
            code = (pm_map or {}).get(sm)
            if not code:
                # fallback: SM2 más común de ese SM (probablemente NO es el código PM I90)
                sm2s = master.loc[master["SM"] == sm, "SM2"].dropna()
                code = sm2s.mode().iloc[0] if not sm2s.empty else sm
            entity_to_rep[code] = sm
            entities.append(code)

    entities = sorted(set(entities))
    if not entities:
        st.error("Ningún representante seleccionado tiene entidades en el maestro.")
        return

    # ── Aviso de coste (dry-run) ──────────────────────────────────────
    with st.expander("Coste estimado de la consulta (dry-run)", expanded=False):
        try:
            b = dry_run_bytes(client, project, dataset, mkt, entities, d_ini, d_fin)
            gb = b / (1024 ** 3)
            st.write(f"Bytes a escanear: **{gb:.3f} GB** "
                     f"(~{gb*6.25:.4f} € fuera del TB gratis mensual).")
        except Exception as e:
            st.caption(f"No se pudo estimar: {e}")

    # ── Ejecutar ──────────────────────────────────────────────────────
    if not st.button("Comparar ofertas", type="primary"):
        st.stop()

    with st.spinner("Consultando BigQuery…"):
        if mkt["interleaved"]:
            df_blocks = _q_interleaved_market(client, project, dataset, mkt,
                                              entities, d_ini, d_fin)
        else:
            df_blocks = _q_simple_market(client, project, dataset, mkt,
                                         entities, d_ini, d_fin)
        metrics = _metrics_from_blocks(df_blocks, mkt, entity_to_rep)

    if metrics.empty:
        st.warning("Sin datos de oferta para esa selección y período. "
                   "¿Las particiones de esos días están cargadas? "
                   "(I90 se publica a D+90: prueba fechas de hace ~91 días o más).")
        return

    # ── Tabla + gráficos ──────────────────────────────────────────────
    st.subheader("Métricas comparables")
    st.dataframe(metrics, use_container_width=True, hide_index=True)

    g1, g2 = st.columns(2)
    with g1:
        fig = _fig_scatter(metrics, mkt)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    with g2:
        fig = _fig_bars(metrics, mkt)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    # ── Intérprete IA ─────────────────────────────────────────────────
    st.subheader("🤖 Interpretación con IA")
    payload = build_ai_payload(metrics, mkt, d_ini, d_fin, reps_sel)
    md = payload_to_markdown(payload)

    tab_b, tab_a = st.tabs(["Copiar para chat (recomendado)", "Llamar a la API (avanzado)"])
    with tab_b:
        st.caption("Copia esto y pégalo en un chat con Claude para la lectura.")
        st.code(md, language="markdown")
        st.download_button("Descargar resumen .md", md,
                           file_name=f"ofertas_{mkt_key}_{d_ini}_{d_fin}.md")
    with tab_a:
        st.caption("Requiere `anthropic` instalado y `ANTHROPIC_API_KEY` en secrets. "
                   "Comprueba que el egress a api.anthropic.com esté permitido tras el VPN.")
        if st.button("Interpretar con Claude (API)"):
            try:
                with st.spinner("Llamando a Claude…"):
                    out = call_claude_api(payload)
                st.markdown(out)
            except Exception as e:
                st.error(f"No se pudo llamar a la API: {e}")

    with st.expander("Payload JSON (debug / reutilización)"):
        st.json(payload)


# Permite probar el módulo aislado: `streamlit run representantes_explorer.py`
if __name__ == "__main__":
    st.set_page_config(page_title="Comparador de ofertas", layout="wide")
    render()
