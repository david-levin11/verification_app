import duckdb
import pandas as pd
from pathlib import Path
from config import get_obs_time_column, get_obs_filter_time_column, get_pairing_method
from forecast_targets import forecast_target_sql
from archive_files import resolve_archive_paths, gust_observation_coverage, forecast_archive_lookback
from datetime import date, datetime

WEB_APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_APP_DIR.parent
LOCAL_ARCHIVE_ROOT = PROJECT_ROOT / "model"


def generate_monthly_paths(root, model, element, start_date, end_date):
    files, missing, _ = resolve_archive_paths(root, model, element, start_date, end_date,
                                              observation=model in ['obs', 'urma'])
    return files, missing

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
    obs_time_tolerance="1h",
    forecast_lead_range=None,
):
    """
    Connects to DuckDB, queries local parquet archives, and returns the raw
    model and observation dataframes.

    Local archive format:
        ./model/{model}/{element}/{YYYY}_{MM}_archive.parquet

    Notes:
        This loader should only load/filter archive data.
        pairing.py is responsible for choosing model_value and obs_value.

    Returns
    -------
    modeldf : pd.DataFrame
    obdf : pd.DataFrame
    message : str | None
        Fatal errors and partial-missing-file warnings are returned here.
        The Streamlit page should treat messages beginning with "Data Missing",
        "Database error", or "Observation Database error" as fatal.
    """

    query_start = pd.Timestamp(start_date)
    query_end = pd.Timestamp(end_date)
    # Sidebar date selections include the entire end date.
    if isinstance(end_date, date) and not isinstance(end_date, datetime):
        query_end += pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    tolerance = pd.Timedelta(obs_time_tolerance)
    if forecast_lead_range is not None:
        low,high=map(float,forecast_lead_range)
        if not (0<=low<=high<float('inf')):
            raise ValueError('Invalid forecast lead range')
    if tolerance < pd.Timedelta(0):
        raise ValueError("Observation time tolerance must be non-negative")
    padding = tolerance if get_pairing_method(element) == "time" else pd.Timedelta(0)
    obs_query_start = query_start - padding
    obs_query_end = query_end + padding
    target_sql = forecast_target_sql(model, element)
    model_read_end = query_end + (pd.Timedelta(days=1) if element == "maxt" else pd.Timedelta(0))
    query_stations = station_list

    if not query_stations:
        return pd.DataFrame(), pd.DataFrame(), "No stations were provided."

    con = duckdb.connect()
    # Archive timestamps and naive UI bounds are UTC. In older DuckDB versions,
    # comparing TIMESTAMPTZ observations with naive bounds otherwise interprets
    # midnight in the computer's local zone and drops the first UTC date.
    con.execute("SET TimeZone = 'UTC'")

    warnings = []

    # ------------------------------------------------------------------
    # 0. Resolve available monthly files
    # ------------------------------------------------------------------

    if analysis_mode == 'Storm Specific Zoom':
        init_date = pd.Timestamp(storm_init_time)
        if init_date.tzinfo is not None:
            init_date = init_date.tz_convert('UTC').tz_localize(None)
        model_read_start = min(query_start, init_date)
    else:
        horizon=(high if forecast_lead_range is not None else max(forecast_hours) if forecast_hours else
                 forecast_archive_lookback(archive_root,model,element,query_start,model_read_end))
        model_read_start = query_start - pd.Timedelta(hours=horizon)
    modelfiles, missing_modelfiles, source_warnings = resolve_archive_paths(
        archive_root, model, element, model_read_start, model_read_end)
    warnings.extend(source_warnings)

    if not modelfiles:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            f"Data Missing: Could not find any local {model.upper()} {element} data "
            f"for the selected dates. Missing files included: {missing_modelfiles[:5]} "
            + " ".join(source_warnings),
        )

    if missing_modelfiles:
        warnings.append(
            f"Some {model.upper()} {element} monthly archive files were missing. "
            f"Proceeding with {len(modelfiles)} available file(s). "
            f"Missing: {missing_modelfiles[:5]}"
        )

    obfiles, missing_obfiles, source_warnings = resolve_archive_paths(
        archive_root, obs, element, obs_query_start, obs_query_end, observation=True)
    warnings.extend(source_warnings)

    if not obfiles:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            f"Data Missing: Could not find any local {obs.upper()} {element} observation data "
            f"for the selected dates. Missing files included: {missing_obfiles[:5]} "
            + " ".join(source_warnings),
        )

    if missing_obfiles:
        warnings.append(
            f"Some {obs.upper()} {element} observation monthly archive files were missing. "
            f"Proceeding with {len(obfiles)} available file(s). "
            f"Missing: {missing_obfiles[:5]}"
        )

    station_placeholders = ", ".join(["?"] * len(query_stations))

    # ------------------------------------------------------------------
    # 1. Query model data
    # ------------------------------------------------------------------

    if analysis_mode == "Storm Specific Zoom":
        if model == "ndfd":
            # NDFD does not have init_time natively.
            modelquery = f"""
            SELECT * FROM read_parquet(?, union_by_name=true)
            WHERE station_id IN ({station_placeholders})
              AND ({target_sql}) BETWEEN ? AND ?
            """
            model_params = [modelfiles] + query_stations + [query_start, query_end]

        else:
            modelquery = f"""
            SELECT * FROM read_parquet(?, union_by_name=true)
            WHERE station_id IN ({station_placeholders})
              AND init_time = ?
              AND ({target_sql}) BETWEEN ? AND ?
            """
            model_params = [modelfiles] + query_stations + [storm_init_time, query_start, query_end]

    else:
        if forecast_lead_range is not None:
            lower_operator='>=' if low==0 else '>'
            modelquery=f"""
            SELECT * FROM read_parquet(?, union_by_name=true)
            WHERE station_id IN ({station_placeholders})
              AND forecast_hour {lower_operator} ? AND forecast_hour <= ?
              AND ({target_sql}) BETWEEN ? AND ?
            """
            model_params=[modelfiles]+query_stations+[low,high,query_start,query_end]
        elif forecast_hours:
            hour_str = ", ".join(str(h) for h in forecast_hours)

            modelquery = f"""
            SELECT * FROM read_parquet(?, union_by_name=true)
            WHERE station_id IN ({station_placeholders})
              AND forecast_hour IN ({hour_str})
              AND ({target_sql}) BETWEEN ? AND ?
            """
            model_params = [modelfiles] + query_stations + [query_start, query_end]

        else:
            modelquery = f"""
            SELECT * FROM read_parquet(?, union_by_name=true)
            WHERE station_id IN ({station_placeholders})
              AND ({target_sql}) BETWEEN ? AND ?
            """
            model_params = [modelfiles] + query_stations + [query_start, query_end]

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

    # Column used to create standardized obdf["valid_time"].
    obs_time_col = get_obs_time_column(element)

    # Optional: if you add get_obs_filter_time_column() to config.py,
    # use it here. Otherwise default to obs_time_col.
    try:
        obs_filter_time_col = get_obs_filter_time_column(element)
    except NameError:
        obs_filter_time_col = obs_time_col

    obquery = f"""
    SELECT * FROM read_parquet(?, union_by_name=true)
    WHERE {station_select} IN ({station_placeholders})
      AND {obs_filter_time_col} BETWEEN ? AND ?
    """
    ob_params = [obfiles] + query_stations + [obs_query_start, obs_query_end]

    try:
        obdf = con.execute(obquery, ob_params).df()

    except Exception as e:
        error_msg = str(e)

        if "Referenced column" in error_msg and obs_filter_time_col in error_msg:
            return (
                modeldf,
                pd.DataFrame(),
                f"Observation Database error: Expected filter time column "
                f"'{obs_filter_time_col}' for {obs} {element}, but it was not found. "
                f"Original error: {e}",
            )

        return modeldf, pd.DataFrame(), f"Observation Database error: {e}"

    if obdf.empty:
        return modeldf, pd.DataFrame(), "No observation data found for these parameters."

    # ------------------------------------------------------------------
    # 4. Standardize obs schema for pairing.py
    # ------------------------------------------------------------------

    # Pairing expects a common valid_time column. Preserve the original
    # time column too, e.g. end_time/window_end/date, for diagnostics and
    # date-based pairing.
    if obs_time_col in obdf.columns:
        if obs_time_col != "valid_time":
            obdf["valid_time"] = obdf[obs_time_col]
    else:
        return (
            modeldf,
            pd.DataFrame(),
            f"Observation schema error: Expected obs time column '{obs_time_col}' "
            f"for {obs} {element}, but available columns are: {obdf.columns.tolist()}",
        )

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

    for col in [
        "valid_time",
        "init_time",
        "start_time",
        "end_time",
        "window_start",
        "window_end",
        "date",
    ]:
        if col in obdf.columns:
            obdf[col] = (
                pd.to_datetime(obdf[col], errors="coerce", utc=True)
                .dt.tz_convert(None)
                .astype("datetime64[ns]")
            )

    # ------------------------------------------------------------------
    # 6. Return data and any non-fatal warnings
    # ------------------------------------------------------------------

    if element == 'gust':
        coverage = gust_observation_coverage(obdf)
        if coverage:
            warnings.append(coverage)
    message = "\n\n".join(warnings) if warnings else None

    return modeldf, obdf, message
