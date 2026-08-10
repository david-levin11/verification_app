import duckdb
import pandas as pd
from pathlib import Path

from pathlib import Path

WEB_APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_APP_DIR.parent
LOCAL_ARCHIVE_ROOT = PROJECT_ROOT / "model"


def generate_monthly_paths(root, model, element, start_date, end_date):
    """
    Generates a list of local parquet paths based on the date range.

    Expected structure:
        ./model/{model}/{element}/{YYYY}_{MM}_archive.parquet
    """
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)

    paths = []

    current = start.replace(day=1)

    while current <= end:
        year_month = current.strftime("%Y_%m")

        path = Path(root) / model / element / f"{year_month}_archive.parquet"
        paths.append(str(path))

        # Move to first of next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return paths


def fetch_data(
    analysis_mode,
    model,
    obs,
    start_date,
    end_date,
    station_list,
    forecast_hours,
    storm_init_time,
    percentile_col_dict,
    percentile,
    element="wind",
    archive_root=LOCAL_ARCHIVE_ROOT,
):
    """
    Connects to DuckDB, queries local parquet archives, and returns the raw
    model and observation dataframes.

    Local archive format:
        ./model/{model}/{element}/{YYYY}_{MM}_archive.parquet

    Notes:
        aws_key and aws_secret are retained for compatibility with the previous
        S3-based version, but they are no longer used.
    """

    query_start = start_date
    query_end = end_date
    query_stations = station_list

    con = duckdb.connect()

    modelfiles = generate_monthly_paths(
        root=archive_root,
        model=model,
        element=element,
        start_date=query_start,
        end_date=query_end,
    )

    obfiles = generate_monthly_paths(
        root=archive_root,
        model=obs,
        element=element,
        start_date=query_start,
        end_date=query_end,
    )

    station_placeholders = ", ".join(["?"] * len(query_stations))

    # 1. Dynamic SQL for model data
    if analysis_mode == "Storm Specific Zoom":
        if model == "ndfd":
            # NDFD does not have init_time natively
            modelquery = f"""
            SELECT * FROM read_parquet({modelfiles})
            WHERE station_id IN ({station_placeholders})
              AND valid_time BETWEEN ? AND ?
            """
            model_params = query_stations + [query_start, query_end]
        else:
            modelquery = f"""
            SELECT * FROM read_parquet({modelfiles})
            WHERE station_id IN ({station_placeholders})
              AND init_time = ?
              AND valid_time BETWEEN ? AND ?
            """
            model_params = query_stations + [storm_init_time, query_start, query_end]

    else:
        if forecast_hours:
            hour_str = ", ".join(str(h) for h in forecast_hours)

            modelquery = f"""
            SELECT * FROM read_parquet({modelfiles})
            WHERE station_id IN ({station_placeholders})
            AND forecast_hour IN ({hour_str})
            AND valid_time BETWEEN ? AND ?
            """
            model_params = query_stations + [query_start, query_end]

        else:
            modelquery = f"""
            SELECT * FROM read_parquet({modelfiles})
            WHERE station_id IN ({station_placeholders})
            AND valid_time BETWEEN ? AND ?
            """
            model_params = query_stations + [query_start, query_end]
    try:
        modeldf = con.execute(modelquery, model_params).df()

    except Exception as e:
        error_msg = str(e)

        if "No files found" in error_msg or "IO Error" in error_msg:
            return (
                pd.DataFrame(),
                pd.DataFrame(),
                f"Data Missing: Could not find local {model.upper()} {element} data "
                f"for the selected dates. Expected files like: "
                f"{Path(archive_root) / model / element / 'YYYY_MM_archive.parquet'}",
            )

        return pd.DataFrame(), pd.DataFrame(), f"Database error: {error_msg}"

    if modeldf.empty:
        return pd.DataFrame(), pd.DataFrame(), "No model data found for these parameters."

    # 2. Reconstruct init_time for NDFD
    if model == "ndfd":
        modeldf["init_time"] = (
            pd.to_datetime(modeldf["valid_time"])
            - pd.to_timedelta(modeldf["forecast_hour"], unit="h")
        )

        if analysis_mode == "Storm Specific Zoom":
            modeldf = modeldf[
                modeldf["init_time"] == pd.to_datetime(storm_init_time)
            ]

            if modeldf.empty:
                return (
                    pd.DataFrame(),
                    pd.DataFrame(),
                    f"No NDFD data matched the init time: {storm_init_time}.",
                )

    # 3. Rename percentile column for aggregate NBM QMD verification
    if model in ["nbmqmd_exp", "nbmqmd"] and analysis_mode == "Aggregate Verification":
        modeldf = modeldf.rename(
            columns={percentile_col_dict[model][percentile]: "wind_speed_kt"}
        )

    # 4. Query observations
    station_select = "station_id" if obs == "urma" else "stid"

    obquery = f"""
    SELECT * FROM read_parquet({obfiles})
    WHERE ({station_select}) IN ({station_placeholders})
      AND valid_time BETWEEN ? AND ?
    """
    ob_params = query_stations + [query_start, query_end]

    try:
        obdf = con.execute(obquery, ob_params).df()

    except Exception as e:
        return modeldf, pd.DataFrame(), f"Observation Database error: {e}"

    # 5. Standardize datetimes to be tz-naive
    for col in ["valid_time", "init_time"]:
        if col in modeldf.columns:
            modeldf[col] = pd.to_datetime(modeldf[col]).dt.tz_localize(None)

    if "valid_time" in obdf.columns:
        obdf["valid_time"] = pd.to_datetime(obdf["valid_time"]).dt.tz_localize(None)

    return modeldf, obdf, None