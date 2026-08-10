"""
Pairing utilities for the Alaska Point Verification Dashboard.

Primary goal:
    Convert any model/obs/element pair into a standardized dataframe:

        station_id
        valid_time
        init_time
        forecast_hour
        model_value
        obs_value

The rest of the app should use model_value and obs_value whenever possible,
rather than element-specific names like wind_speed_kt, precip_accum_6hr, etc.
"""

from __future__ import annotations

import pandas as pd

from config import (
    get_element_config,
    get_percentile_columns,
    is_probabilistic,
)


# ---------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------

def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """
    Return the first column from candidates that exists in df.
    """
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _standardize_station_id(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize station ID naming and dtype.

    Synoptic obs commonly use 'stid', while model data usually use 'station_id'.
    Force station_id to plain Python string/object dtype for merge_asof.
    """
    df = df.copy()

    if "station_id" not in df.columns and "stid" in df.columns:
        df = df.rename(columns={"stid": "station_id"})

    if "station_id" in df.columns:
        df["station_id"] = (
            df["station_id"]
            .astype(str)
            .str.strip()
        )

    return df

def _standardize_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert common time columns to timezone-naive datetime64[ns].
    """
    df = df.copy()

    for col in ["valid_time", "init_time"]:
        if col in df.columns:
            df[col] = (
                pd.to_datetime(df[col], errors="coerce", utc=True)
                .dt.tz_convert(None)
                .astype("datetime64[ns]")
            )

    return df

def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply common station/time standardization.
    """
    df = _standardize_station_id(df)
    df = _standardize_datetime(df)
    return df


# ---------------------------------------------------------------------
# Column selection
# ---------------------------------------------------------------------

def get_model_value_column(
    modeldf: pd.DataFrame,
    model: str,
    element: str,
    percentile: str | None = None,
) -> str:
    """
    Determine which model column should be used as the deterministic model value.

    For probabilistic model/element combinations, this uses the selected
    percentile column if available. For deterministic combinations, it uses
    the configured model_value_candidates.
    """
    element_cfg = get_element_config(element)

    # Probabilistic case: use selected percentile as the app's model_value.
    if percentile is not None and is_probabilistic(model, element):
        pct_cols = get_percentile_columns(element)
        pct_col = pct_cols.get(str(percentile))

        if pct_col in modeldf.columns:
            return pct_col

        # Fall back gracefully if the selected percentile column is missing.
        # This can happen while archive column names are still being normalized.
        default_pct = element_cfg.get("default_percentile")
        default_pct_col = pct_cols.get(str(default_pct))

        if default_pct_col in modeldf.columns:
            return default_pct_col

    # Deterministic case or fallback.
    candidates = element_cfg.get("model_value_candidates", [])
    model_col = _first_existing_column(modeldf, candidates)

    if model_col is not None:
        return model_col

    raise ValueError(
        f"Could not find a model value column for model={model}, element={element}. "
        f"Tried: {candidates}. Available columns: {list(modeldf.columns)}"
    )


def get_obs_value_column(
    obdf: pd.DataFrame,
    element: str,
) -> str:
    """
    Determine which observation column should be used as obs_value.
    """
    element_cfg = get_element_config(element)

    candidates = element_cfg.get("obs_value_candidates", [])
    obs_col = _first_existing_column(obdf, candidates)

    if obs_col is not None:
        return obs_col

    raise ValueError(
        f"Could not find an observation value column for element={element}. "
        f"Tried: {candidates}. Available columns: {list(obdf.columns)}"
    )


def get_direction_column(
    merged: pd.DataFrame,
    element: str,
) -> str | None:
    """
    Return an observed wind direction column if available.

    This is only relevant for wind/gust workflows.
    """
    element_cfg = get_element_config(element)

    direction_candidates = element_cfg.get("direction_candidates", [])
    return _first_existing_column(merged, direction_candidates)


# ---------------------------------------------------------------------
# Main pairing function
# ---------------------------------------------------------------------

def build_verification_pairs(
    modeldf: pd.DataFrame,
    obdf: pd.DataFrame,
    model: str,
    obs: str,
    element: str,
    percentile: str | None = None,
    obs_time_tolerance: str = "1h",
) -> pd.DataFrame:
    """
    Build standardized verification pairs.

    Returns dataframe with at least:

        station_id
        valid_time
        init_time
        forecast_hour
        model_value
        obs_value

    Parameters
    ----------
    modeldf : pd.DataFrame
        Forecast dataframe returned from fetch_data().
    obdf : pd.DataFrame
        Observation dataframe returned from fetch_data().
    model : str
        Model name, e.g. 'nbmqmd_exp', 'nbm', 'hrrr', 'ndfd'.
    obs : str
        Observation source, usually 'obs' or 'urma'.
    element : str
        Element name, e.g. 'wind', 'precip6hr', 'maxt'.
    percentile : str | None
        Selected percentile for probabilistic model/element combinations.
    obs_time_tolerance : str
        Tolerance for nearest-time matching when obs source is point observations.

    Notes
    -----
    For obs == 'obs', this uses merge_asof with a time tolerance because
    Synoptic observation times may not land exactly on model valid_time.

    For obs == 'urma', this first attempts an exact match on station_id and
    valid_time. If station_id is unavailable in the URMA dataframe, it falls
    back to valid_time only.
    """
    if modeldf is None or modeldf.empty:
        return pd.DataFrame()

    if obdf is None or obdf.empty:
        return pd.DataFrame()

    modeldf = _prepare_dataframe(modeldf)
    obdf = _prepare_dataframe(obdf)

    model_col = get_model_value_column(
        modeldf=modeldf,
        model=model,
        element=element,
        percentile=percentile,
    )

    obs_col = get_obs_value_column(
        obdf=obdf,
        element=element,
    )

    # Preserve original column names for debugging / downstream plots.
    modeldf = modeldf.copy()
    obdf = obdf.copy()

    modeldf["model_value"] = pd.to_numeric(modeldf[model_col], errors="coerce")
    obdf["obs_value"] = pd.to_numeric(obdf[obs_col], errors="coerce")

    required_model_cols = [
        "station_id",
        "valid_time",
        "model_value",
    ]

    optional_model_cols = [
        "init_time",
        "forecast_hour",
        model_col,
    ]

    required_obs_cols = [
        "station_id",
        "valid_time",
        "obs_value",
    ]

    optional_obs_cols = [
        obs_col,
    ]

    # Keep percentile columns if available. This allows reliability/rank
    # histogram functions to continue using the probabilistic information.
    if is_probabilistic(model, element):
        pct_cols = list(get_percentile_columns(element).values())
        optional_model_cols.extend([c for c in pct_cols if c in modeldf.columns])

    # Keep wind direction if available for direction filtering.
    element_cfg = get_element_config(element)
    for direction_col in element_cfg.get("direction_candidates", []):
        if direction_col in obdf.columns:
            optional_obs_cols.append(direction_col)
        if direction_col in modeldf.columns:
            optional_model_cols.append(direction_col)

    model_keep_cols = [
        c for c in required_model_cols + optional_model_cols
        if c in modeldf.columns
    ]

    obs_keep_cols = [
        c for c in required_obs_cols + optional_obs_cols
        if c in obdf.columns
    ]

    modeldf = modeldf[model_keep_cols].dropna(subset=["station_id", "valid_time", "model_value"])
    obdf = obdf[obs_keep_cols].dropna(subset=["station_id", "valid_time", "obs_value"])

    if modeldf.empty or obdf.empty:
        return pd.DataFrame()

    if obs == "obs":
        # Nearest-time point observation matching.

        # Force merge key dtypes to match exactly before merge_asof.
        modeldf["station_id"] = modeldf["station_id"].astype(str)
        obdf["station_id"] = obdf["station_id"].astype(str)

        modeldf["valid_time"] = (
            pd.to_datetime(modeldf["valid_time"], errors="coerce", utc=True)
            .dt.tz_convert(None)
            .astype("datetime64[ns]")
        )

        obdf["valid_time"] = (
            pd.to_datetime(obdf["valid_time"], errors="coerce", utc=True)
            .dt.tz_convert(None)
            .astype("datetime64[ns]")
        )

        modeldf = modeldf.dropna(subset=["station_id", "valid_time"])
        obdf = obdf.dropna(subset=["station_id", "valid_time"])

        modeldf = modeldf.sort_values(["valid_time", "station_id"])
        obdf = obdf.sort_values(["valid_time", "station_id"])

        merged = pd.merge_asof(
            modeldf,
            obdf,
            on="valid_time",
            by="station_id",
            direction="nearest",
            tolerance=pd.Timedelta(obs_time_tolerance),
            suffixes=("_model", "_obs"),
        )
    else:
        # Analysis-style verification source, usually exact valid_time match.
        if "station_id" in obdf.columns and "station_id" in modeldf.columns:
            merged = pd.merge(
                modeldf,
                obdf,
                on=["station_id", "valid_time"],
                how="inner",
                suffixes=("_model", "_obs"),
            )
        else:
            merged = pd.merge(
                modeldf,
                obdf,
                on="valid_time",
                how="inner",
                suffixes=("_model", "_obs"),
            )

    if merged.empty:
        return merged

    # After merge, ensure standard columns exist and are numeric.
    merged["model_value"] = pd.to_numeric(merged["model_value"], errors="coerce")
    merged["obs_value"] = pd.to_numeric(merged["obs_value"], errors="coerce")

    standard_cols = [
        "station_id",
        "valid_time",
        "init_time",
        "forecast_hour",
        "model_value",
        "obs_value",
    ]

    # Some edge cases may not have init_time/forecast_hour.
    for col in standard_cols:
        if col not in merged.columns:
            merged[col] = pd.NA

    merged = merged.dropna(subset=["station_id", "valid_time", "model_value", "obs_value"])

    # Put standard columns first, keep everything else after.
    remaining_cols = [c for c in merged.columns if c not in standard_cols]

    return merged[standard_cols + remaining_cols]


# ---------------------------------------------------------------------
# Optional category helper
# ---------------------------------------------------------------------

def add_category_columns(
    pairs: pd.DataFrame,
    bins: list[float],
    label_values: list[int],
    model_category_col: str = "model_category",
    obs_category_col: str = "obs_category",
) -> pd.DataFrame:
    """
    Add categorical verification columns based on model_value and obs_value.

    This replaces the old wind-specific category creation logic and works for
    wind, precip, snow, temperature, etc., as long as the bins make sense.
    """
    if pairs.empty:
        return pairs

    df = pairs.copy()

    df[model_category_col] = pd.cut(
        df["model_value"],
        bins=bins,
        labels=label_values,
    )

    df[obs_category_col] = pd.cut(
        df["obs_value"],
        bins=bins,
        labels=label_values,
    )

    df[model_category_col] = pd.to_numeric(df[model_category_col], errors="coerce")
    df[obs_category_col] = pd.to_numeric(df[obs_category_col], errors="coerce")

    return df