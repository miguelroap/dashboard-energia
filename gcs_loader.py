# gcs_loader.py
# Lee ficheros desde Google Cloud Storage usando la cuenta de servicio
# configurada en st.secrets["gcp_service_account"].
# El nombre del bucket viene de st.secrets["gcs"]["bucket"].

import io
import glob
import streamlit as st
import pandas as pd
import gcsfs
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

@st.cache_resource
def _get_fs():
    """Crea y cachea el filesystem GCS autenticado."""
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gcsfs.GCSFileSystem(
        project=st.secrets["gcp_service_account"]["project_id"],
        token=creds
    )

def _bucket() -> str:
    return st.secrets["gcs"]["bucket"]

def _path(filename: str) -> str:
    return f"{_bucket()}/{filename}"

# ── API pública ───────────────────────────────────────────────────────────────

def gcs_available() -> bool:
    """True si los secrets de GCS están configurados."""
    try:
        _ = st.secrets["gcp_service_account"]["project_id"]
        _ = st.secrets["gcs"]["bucket"]
        return True
    except (KeyError, FileNotFoundError):
        return False

@st.cache_data(ttl=3600, show_spinner=False)
def load_parquet(filename: str) -> pd.DataFrame:
    """Descarga y carga un .parquet desde GCS. Cachea 1 hora."""
    try:
        fs = _get_fs()
        with fs.open(_path(filename), "rb") as f:
            return pd.read_parquet(f)
    except FileNotFoundError:
        st.error(f"Fichero '{filename}' no encontrado en GCS.")
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def load_excel(filename: str, **kwargs) -> pd.DataFrame:
    """Descarga y carga un .xlsx desde GCS."""
    try:
        fs = _get_fs()
        with fs.open(_path(filename), "rb") as f:
            return pd.read_excel(f, **kwargs)
    except FileNotFoundError:
        st.error(f"Fichero '{filename}' no encontrado en GCS.")
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def list_files(prefix: str = "") -> list[str]:
    """Lista los nombres de fichero en el bucket con el prefijo dado."""
    try:
        fs = _get_fs()
        paths = fs.ls(_bucket())
        names = [p.split("/")[-1] for p in paths]
        return [n for n in names if n.startswith(prefix)] if prefix else names
    except Exception:
        return []

@st.cache_data(ttl=3600, show_spinner=False)
def find_latest_excel(prefix: str, **kwargs) -> tuple[pd.DataFrame, str]:
    """
    Busca el fichero más reciente (alfabéticamente desc) con ese prefijo
    y lo carga. Devuelve (DataFrame, nombre_fichero).
    """
    matches = sorted([f for f in list_files(prefix) if f.endswith('.xlsx')], reverse=True)
    if not matches:
        return pd.DataFrame(), ""
    name = matches[0]
    return load_excel(name, **kwargs), name

def list_parquet_years(prefix: str = "allh_diario_") -> list[int]:
    """Devuelve los años disponibles para los parquets diarios."""
    files = list_files(prefix)
    years = []
    for f in files:
        stem = f.replace(prefix, "").replace(".parquet", "")
        if stem.isdigit():
            years.append(int(stem))
    return sorted(years)
