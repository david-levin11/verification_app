import numpy as np
import pandas as pd


def compute_station_metrics(
    merged,
    station_meta,
    threshold,
    model_value_col="model_value",
    obs_value_col="obs_value",
):
    """
    Compute station-level deterministic and threshold verification metrics.

    Expected input columns:
        station_id
        model_value
        obs_value
    """
    df = merged.copy()

    if "station_id" not in df.columns:
        return pd.DataFrame()

    if model_value_col not in df.columns or obs_value_col not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["station_id", model_value_col, obs_value_col]).copy()

    if df.empty:
        return pd.DataFrame()

    df["error"] = df[model_value_col] - df[obs_value_col]
    df["abs_error"] = df["error"].abs()
    df["sq_error"] = df["error"] ** 2

    df["obs_event"] = df[obs_value_col] >= threshold
    df["fcst_event"] = df[model_value_col] >= threshold

    grouped = df.groupby("station_id").agg(
        n=("error", "count"),
        bias=("error", "mean"),
        mae=("abs_error", "mean"),
        rmse=("sq_error", lambda x: np.sqrt(np.mean(x))),
        mean_obs=(obs_value_col, "mean"),
        mean_fcst=(model_value_col, "mean"),
        max_obs=(obs_value_col, "max"),
        max_fcst=(model_value_col, "max"),
    ).reset_index()

    contingency_rows = []

    for station_id, sdf in df.groupby("station_id"):
        hits = ((sdf["fcst_event"]) & (sdf["obs_event"])).sum()
        misses = ((~sdf["fcst_event"]) & (sdf["obs_event"])).sum()
        false_alarms = ((sdf["fcst_event"]) & (~sdf["obs_event"])).sum()
        correct_negatives = ((~sdf["fcst_event"]) & (~sdf["obs_event"])).sum()

        pod = hits / (hits + misses) if (hits + misses) > 0 else np.nan
        far = false_alarms / (hits + false_alarms) if (hits + false_alarms) > 0 else np.nan
        csi = hits / (hits + misses + false_alarms) if (hits + misses + false_alarms) > 0 else np.nan

        event_freq_obs = (hits + misses) / len(sdf) if len(sdf) > 0 else np.nan
        event_freq_fcst = (hits + false_alarms) / len(sdf) if len(sdf) > 0 else np.nan

        contingency_rows.append(
            {
                "station_id": station_id,
                "hits": hits,
                "misses": misses,
                "false_alarms": false_alarms,
                "correct_negatives": correct_negatives,
                "pod": pod,
                "far": far,
                "csi": csi,
                "event_freq_obs": event_freq_obs,
                "event_freq_fcst": event_freq_fcst,
            }
        )

    cont = pd.DataFrame(contingency_rows)

    metrics = grouped.merge(
        cont,
        on="station_id",
        how="left",
    )

    if not station_meta.empty:
        meta_cols = [
            c for c in [
                "station_id",
                "name",
                "latitude",
                "longitude",
                "elevation_ft",
                "wfo_best",
                "public_zone_id",
                "public_zone_name",
                "coastal_marine_zone_id",
                "coastal_marine_zone_name",
                "offshore_zone_id",
                "offshore_zone_name",
                "station_context",
            ]
            if c in station_meta.columns
        ]

        metrics = metrics.merge(
            station_meta[meta_cols].drop_duplicates(subset=["station_id"]),
            on="station_id",
            how="left",
        )

    metrics = metrics.dropna(subset=["latitude", "longitude"], how="any")

    return metrics


def compute_summary_metrics(
    merged,
    threshold,
    model_value_col="model_value",
    obs_value_col="obs_value",
):
    """
    Compute aggregate summary verification metrics.
    """
    df = merged.dropna(subset=[model_value_col, obs_value_col]).copy()

    if df.empty:
        return {}

    error = df[model_value_col] - df[obs_value_col]

    obs_event = df[obs_value_col] >= threshold
    fcst_event = df[model_value_col] >= threshold

    hits = ((fcst_event) & (obs_event)).sum()
    misses = ((~fcst_event) & (obs_event)).sum()
    false_alarms = ((fcst_event) & (~obs_event)).sum()
    correct_negatives = ((~fcst_event) & (~obs_event)).sum()

    return {
        "n": len(df),
        "bias": error.mean(),
        "mae": error.abs().mean(),
        "rmse": np.sqrt(np.mean(error ** 2)),
        "mean_obs": df[obs_value_col].mean(),
        "mean_fcst": df[model_value_col].mean(),
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "correct_negatives": correct_negatives,
        "pod": hits / (hits + misses) if (hits + misses) > 0 else np.nan,
        "far": false_alarms / (hits + false_alarms) if (hits + false_alarms) > 0 else np.nan,
        "csi": hits / (hits + misses + false_alarms) if (hits + misses + false_alarms) > 0 else np.nan,
    }