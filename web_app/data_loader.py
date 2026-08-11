import duckdb
import pandas as pd
from pathlib import Path
from config import get_obs_time_column

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
        This loader should only load/filter archive data.
        pairing.py is responsible for choosing model_value and obs_value.
    """

    ACCUM_ELEMENTS = [
        "precip6hr",
        "precip24hr",
        "snow6hr",
        "snow24hr",
        "snow48hr",
        "snow72hr",
    ]

    query_start = start_date
    query_end = end_date
    query_stations = station_list

    if not query_stations:
        return pd.DataFrame(), pd.DataFrame(), "No stations were provided."

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

    # ------------------------------------------------------------------
    # 1. Query model data
    # ------------------------------------------------------------------

    if analysis_mode == "Storm Specific Zoom":
        if model == "ndfd":
            # NDFD does not have init_time natively.
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

    # ------------------------------------------------------------------
    # 2. Reconstruct init_time for NDFD
    # ------------------------------------------------------------------

    if model == "ndfd":
        if "forecast_hour" in modeldf.columns:
            modeldf["init_time"] = (
                pd.to_datetime(modeldf["valid_time"], errors="coerce", utc=True)
                - pd.to_timedelta(modeldf["forecast_hour"], unit="h")
            )

            if analysis_mode == "Storm Specific Zoom":
                target_init = pd.to_datetime(storm_init_time, errors="coerce", utc=True)

                modeldf = modeldf[
                    pd.to_datetime(modeldf["init_time"], errors="coerce", utc=True)
                    == target_init
                ]

                if modeldf.empty:
                    return (
                        pd.DataFrame(),
                        pd.DataFrame(),
                        f"No NDFD data matched the init time: {storm_init_time}.",
                    )

    # ------------------------------------------------------------------
    # 3. Query observations
    # ------------------------------------------------------------------

    station_select = "station_id" if obs == "urma" else "stid"

    # Accumulation obs archives use end_time as the valid time.
    # Example precip6hr columns:
    #     start_time, end_time, precip_total
    #obs_time_col = "end_time" if element in ACCUM_ELEMENTS else "valid_time"
    obs_time_col = get_obs_time_column(element)

    obquery = f"""
    SELECT * FROM read_parquet({obfiles})
    WHERE {station_select} IN ({station_placeholders})
      AND {obs_time_col} BETWEEN ? AND ?
    """
    ob_params = query_stations + [query_start, query_end]

    try:
        obdf = con.execute(obquery, ob_params).df()

    except Exception as e:
        error_msg = str(e)

        if "Referenced column" in error_msg and obs_time_col in error_msg:
            return (
                modeldf,
                pd.DataFrame(),
                f"Observation Database error: Expected time column '{obs_time_col}' "
                f"for {obs} {element}, but it was not found. Original error: {e}",
            )

        return modeldf, pd.DataFrame(), f"Observation Database error: {e}"

    if obdf.empty:
        return modeldf, pd.DataFrame(), "No observation data found for these parameters."

    # ------------------------------------------------------------------
    # 4. Standardize obs schema for pairing.py
    # ------------------------------------------------------------------
    # Standardize observation time column for pairing.py.
    # Pairing expects valid_time.
    if obs_time_col in obdf.columns and obs_time_col != "valid_time":
        obdf["valid_time"] = obdf[obs_time_col]
    # Accumulation obs use end_time as the verification valid_time.
    if element in ACCUM_ELEMENTS:
        if "end_time" in obdf.columns and "valid_time" not in obdf.columns:
            obdf = obdf.rename(columns={"end_time": "valid_time"})

    # ------------------------------------------------------------------
    # 5. Standardize datetimes to tz-naive datetime64[ns]
    # ------------------------------------------------------------------

    for col in ["valid_time", "init_time"]:
        if col in modeldf.columns:
            modeldf[col] = (
                pd.to_datetime(modeldf[col], errors="coerce", utc=True)
                .dt.tz_convert(None)
                .astype("datetime64[ns]")
            )

    for col in ["valid_time", "init_time", "start_time", "end_time"]:
        if col in obdf.columns:
            obdf[col] = (
                pd.to_datetime(obdf[col], errors="coerce", utc=True)
                .dt.tz_convert(None)
                .astype("datetime64[ns]")
            )

    return modeldf, obdf, None