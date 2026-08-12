from pathlib import Path
import pandas as pd


# ---------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------

ARCHIVE_ROOT = Path(r"C:\Users\David.Levin\verification_app\model")

MODEL = "nbmqmd"
OBS = "obs"
ELEMENT = "maxt"
YEAR_MONTH = "2025_10"

STATION_ID = "PANC"   # change this to a station you know exists in both files


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def read_archive(source, element, year_month):
    path = ARCHIVE_ROOT / source / element / f"{year_month}_archive.parquet"

    print()
    print(f"Reading {source.upper()} file:")
    print(path)

    if not path.exists():
        raise FileNotFoundError(path)

    df = pd.read_parquet(path)

    for col in ["init_time", "valid_time", "date", "window_start", "window_end"]:
        if col in df.columns:
            df[col] = (
                pd.to_datetime(df[col], errors="coerce", utc=True)
                .dt.tz_convert(None)
                .astype("datetime64[ns]")
            )

    if "station_id" in df.columns:
        df["station_id"] = df["station_id"].astype(str).str.strip()

    if "stid" in df.columns:
        df["stid"] = df["stid"].astype(str).str.strip()

    return df


# ---------------------------------------------------------------------
# Read data
# ---------------------------------------------------------------------

model_df = read_archive(MODEL, ELEMENT, YEAR_MONTH)
obs_df = read_archive(OBS, ELEMENT, YEAR_MONTH)

print()
print("Model columns:")
print(model_df.columns.tolist())

print()
print("Obs columns:")
print(obs_df.columns.tolist())


# ---------------------------------------------------------------------
# Filter station
# ---------------------------------------------------------------------

model_station = model_df[model_df["station_id"] == STATION_ID].copy()
obs_station = obs_df[obs_df["stid"] == STATION_ID].copy()

print()
print(f"Station: {STATION_ID}")
print(f"Model rows: {len(model_station):,}")
print(f"Obs rows:   {len(obs_station):,}")

if model_station.empty:
    print("No model rows found for this station.")
if obs_station.empty:
    print("No obs rows found for this station.")

if model_station.empty or obs_station.empty:
    raise SystemExit


# ---------------------------------------------------------------------
# Add date-style fields for comparison
# ---------------------------------------------------------------------

model_station["model_valid_date"] = model_station["valid_time"].dt.date
model_station["model_init_date"] = model_station["init_time"].dt.date
obs_station["obs_date"] = obs_station["date"].dt.date
obs_station["obs_window_start_date"] = obs_station["window_start"].dt.date
obs_station["obs_window_end_date"] = obs_station["window_end"].dt.date


# ---------------------------------------------------------------------
# Print model timing summary
# ---------------------------------------------------------------------

print()
print("Model timing summary")
print("--------------------")
print("Unique forecast hours:")
print(sorted(model_station["forecast_hour"].dropna().unique().tolist()))

print()
print("Model valid_time values by date/hour:")
model_time_summary = (
    model_station
    .assign(valid_hour=model_station["valid_time"].dt.hour)
    .groupby(["forecast_hour", "valid_hour"])
    .size()
    .reset_index(name="count")
    .sort_values(["forecast_hour", "valid_hour"])
)
print(model_time_summary.to_string(index=False))


# ---------------------------------------------------------------------
# Print obs timing summary
# ---------------------------------------------------------------------

print()
print("Obs timing summary")
print("------------------")
obs_time_summary = (
    obs_station
    .assign(
        date_hour=obs_station["date"].dt.hour,
        window_start_hour=obs_station["window_start"].dt.hour,
        window_end_hour=obs_station["window_end"].dt.hour,
    )
    .groupby(["date_hour", "window_start_hour", "window_end_hour"])
    .size()
    .reset_index(name="count")
    .sort_values(["date_hour", "window_start_hour", "window_end_hour"])
)
print(obs_time_summary.to_string(index=False))


# ---------------------------------------------------------------------
# Show side-by-side samples
# ---------------------------------------------------------------------

print()
print("Model sample")
print("------------")
model_cols = [
    "station_id",
    "init_time",
    "valid_time",
    "forecast_hour",
    "maxt_p5",
    "maxt_p50",
    "maxt_p95",
    "model_valid_date",
]
print(
    model_station[model_cols]
    .sort_values(["valid_time", "forecast_hour"])
    .head(30)
    .to_string(index=False)
)

print()
print("Obs sample")
print("----------")
obs_cols = [
    "stid",
    "date",
    "window_start",
    "window_end",
    "tmax",
    "obs_date",
    "obs_window_start_date",
    "obs_window_end_date",
]
print(
    obs_station[obs_cols]
    .sort_values(["date", "window_start"])
    .head(30)
    .to_string(index=False)
)


# ---------------------------------------------------------------------
# Candidate pairing checks
# ---------------------------------------------------------------------

print()
print("Candidate pairing counts")
print("------------------------")

# A) model valid date == obs date
model_a = model_station.copy()
obs_a = obs_station.copy()

model_a["pair_date"] = model_a["valid_time"].dt.date
obs_a["pair_date"] = obs_a["date"].dt.date

pair_a = pd.merge(
    model_a,
    obs_a,
    left_on=["station_id", "pair_date"],
    right_on=["stid", "pair_date"],
    how="inner",
    suffixes=("_model", "_obs"),
)

print(f"A) model valid_time date == obs date: {len(pair_a):,} pairs")


# B) model valid date == obs window_start date
model_b = model_station.copy()
obs_b = obs_station.copy()

model_b["pair_date"] = model_b["valid_time"].dt.date
obs_b["pair_date"] = obs_b["window_start"].dt.date

pair_b = pd.merge(
    model_b,
    obs_b,
    left_on=["station_id", "pair_date"],
    right_on=["stid", "pair_date"],
    how="inner",
    suffixes=("_model", "_obs"),
)

print(f"B) model valid_time date == obs window_start date: {len(pair_b):,} pairs")


# C) model valid date + 1 == obs window_end date
model_c = model_station.copy()
obs_c = obs_station.copy()

model_c["pair_date"] = model_c["valid_time"].dt.date
obs_c["pair_date"] = obs_c["window_end"].dt.date

pair_c = pd.merge(
    model_c,
    obs_c,
    left_on=["station_id", "pair_date"],
    right_on=["stid", "pair_date"],
    how="inner",
    suffixes=("_model", "_obs"),
)

print(f"C) model valid_time date == obs window_end date: {len(pair_c):,} pairs")


# D) exact valid_time == window_end
model_d = model_station.copy()
obs_d = obs_station.copy()

pair_d = pd.merge(
    model_d,
    obs_d,
    left_on=["station_id", "valid_time"],
    right_on=["stid", "window_end"],
    how="inner",
    suffixes=("_model", "_obs"),
)

print(f"D) model valid_time == obs window_end: {len(pair_d):,} pairs")


# ---------------------------------------------------------------------
# Show pair samples for each candidate
# ---------------------------------------------------------------------

def show_pair_sample(label, pair_df):
    print()
    print(label)
    print("-" * len(label))

    if pair_df.empty:
        print("No pairs.")
        return

    cols = [
        "station_id",
        "init_time",
        "valid_time",
        "forecast_hour",
        "maxt_p50",
        "date",
        "window_start",
        "window_end",
        "tmax",
    ]

    existing_cols = [c for c in cols if c in pair_df.columns]

    print(
        pair_df[existing_cols]
        .sort_values(["valid_time", "forecast_hour"])
        .head(20)
        .to_string(index=False)
    )


show_pair_sample("Sample A: model valid date == obs date", pair_a)
show_pair_sample("Sample B: model valid date == obs window_start date", pair_b)
show_pair_sample("Sample C: model valid date == obs window_end date", pair_c)
show_pair_sample("Sample D: model valid_time == obs window_end", pair_d)