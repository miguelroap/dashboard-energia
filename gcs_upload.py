# gcs_upload.py — versión NUBE (Cloud Function)
# ------------------------------------------------------------------------------
# Sube/actualiza parquets en GCS con upsert idempotente:
#   - upload_diario_to_gcs   -> allh_diario_{YYYY}.parquet   (clave UP+MA+Tech+Day)
#   - upload_horario_to_gcs  -> allh_{YYYY-MM}.parquet       (clave UP+MA+Tech+Day+hour)
#
# Diferencia clave vs. la versión local:
#   - NO usa un JSON de credenciales. En la Cloud Function se autentica con el
#     service account de la propia función (Application Default Credentials).
#     creds_path se mantiene como parámetro OPCIONAL por compatibilidad: si se
#     pasa, se usa; si es None (caso nube), se usa el SA por defecto.
#
# Lógica de upsert (idéntica en ambos): descarga la partición existente de GCS
# (si la hay), concatena lo nuevo, deduplica por la clave quedándose con la
# última versión, y reescribe. Relanzar una fecha la sobreescribe sin duplicar.

import io
import gcsfs
import pandas as pd

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def _get_fs(creds_path=None):
    """Filesystem GCS. Sin creds_path -> ADC (service account de la función)."""
    if creds_path:
        from google.oauth2 import service_account
        import json
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES)
        with open(creds_path) as f:
            project = creds.project_id or json.load(f).get("project_id", "")
        return gcsfs.GCSFileSystem(project=project, token=creds)
    # Nube: ADC. gcsfs detecta el SA de la función automáticamente.
    return gcsfs.GCSFileSystem()


def _cast_str_cols(df, cols=("Tech", "MA", "UP")):
    for col in cols:
        if col in df.columns:
            df[col] = df[col].astype(str)
    return df


def _upsert_to_gcs(df_nuevo, gcs_path, subset_keys, fs, sort_cols, log):
    """Descarga (si existe) -> concat -> drop_duplicates(keep='last') -> reescribe."""
    if fs.exists(gcs_path):
        log(f"Descargando {gcs_path} para upsert...")
        with fs.open(gcs_path, "rb") as f:
            df_old = pd.read_parquet(f)
        df_final = (pd.concat([df_old, df_nuevo])
                    .drop_duplicates(subset=subset_keys, keep="last"))
        log(f"Upsert: {len(df_nuevo):,} filas nuevas -> {len(df_final):,} totales")
    else:
        df_final = df_nuevo.copy()
        log(f"{gcs_path} no existe -> se crea desde cero ({len(df_final):,} filas)")

    # tipados de salida coherentes con el builder
    df_final = _cast_str_cols(df_final)
    if "Day" in df_final.columns:
        df_final["Day"] = pd.to_datetime(df_final["Day"]).dt.normalize()
    for col in df_final.select_dtypes(include=["float64"]).columns:
        df_final[col] = df_final[col].astype("float32")
    sort_present = [c for c in sort_cols if c in df_final.columns]
    if sort_present:
        df_final = df_final.sort_values(sort_present).reset_index(drop=True)

    buf = io.BytesIO()
    df_final.to_parquet(buf, index=False, compression="brotli")
    buf.seek(0)
    with fs.open(gcs_path, "wb") as f:
        f.write(buf.read())
    log(f"✅ Subido {gcs_path} ({buf.tell()/1024/1024:.1f} MB)")
    return True


def upload_diario_to_gcs(df_nuevo, year, bucket, creds_path=None, verbose=True):
    """Upsert del diario anual: allh_diario_{year}.parquet (clave UP+MA+Tech+Day)."""
    filename = f"allh_diario_{year}.parquet"
    gcs_path = f"{bucket}/{filename}"

    def log(m):
        if verbose:
            print(f"  [GCS diario] {m}")

    try:
        fs = _get_fs(creds_path)
        return _upsert_to_gcs(
            df_nuevo=df_nuevo, gcs_path=gcs_path,
            subset_keys=["UP", "MA", "Tech", "Day"],
            fs=fs, sort_cols=["Day", "UP"], log=log)
    except Exception as e:
        print(f"  [GCS diario] ❌ Error en {filename}: {e}")
        return False


def upload_horario_to_gcs(df_nuevo, year_month, keys, bucket,
                          creds_path=None, verbose=True):
    """Upsert del horario mensual: allh_{YYYY-MM}.parquet.

    keys: lista de columnas clave de upsert (típicamente UP+MA+Tech+Day+hour).
    """
    filename = f"allh_{year_month}.parquet"
    gcs_path = f"{bucket}/{filename}"

    def log(m):
        if verbose:
            print(f"  [GCS horario] {m}")

    try:
        fs = _get_fs(creds_path)
        return _upsert_to_gcs(
            df_nuevo=df_nuevo, gcs_path=gcs_path,
            subset_keys=list(keys),
            fs=fs, sort_cols=["Day", "hour", "qhour", "UP"], log=log)
    except Exception as e:
        print(f"  [GCS horario] ❌ Error en {filename}: {e}")
        return False
