from pathlib import Path
import pandas as pd


# ---------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------

OBS_ROOT = Path(r"C:\Users\David.Levin\verification_app\model\obs")

ELEMENT = "maxt"     # examples: wind, precip6hr, precip24hr, maxt, mint, rh
YEAR_MONTH = "2025_10"    # YYYY_MM


# ---------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------

parquet_path = OBS_ROOT / ELEMENT / f"{YEAR_MONTH}_archive.parquet"

print()
print("Inspecting:")
print(parquet_path)
print()

if not parquet_path.exists():
    raise FileNotFoundError(f"Could not find file: {parquet_path}")

df = pd.read_parquet(parquet_path)

print("Basic info")
print("----------")
print(f"Rows:    {len(df):,}")
print(f"Columns: {len(df.columns):,}")
print()

print("Column names")
print("------------")
for col in df.columns:
    print(f"{col}: {df[col].dtype}")

print()
print("Head")
print("----")
print(df.head(20).to_string(index=False))

print()
print("Non-null counts")
print("---------------")
print(df.notna().sum().sort_values(ascending=False).to_string())

print()
print("Datetime-like column ranges")
print("---------------------------")

for col in df.columns:
    if "time" in col.lower() or "date" in col.lower():
        temp = pd.to_datetime(df[col], errors="coerce", utc=True)
        print(f"{col}")
        print(f"  dtype: {df[col].dtype}")
        print(f"  min:   {temp.min()}")
        print(f"  max:   {temp.max()}")
        print()

print("Likely station columns")
print("----------------------")
for col in ["stid", "station_id", "id"]:
    if col in df.columns:
        vals = df[col].dropna().astype(str).unique()
        print(f"{col}: {len(vals):,} unique")
        print(f"  first 20: {sorted(vals)[:20]}")

print()
print("Likely value columns")
print("--------------------")
for col in df.columns:
    if any(token in col.lower() for token in ["precip", "snow", "temp", "rh", "wind", "gust"]):
        print(f"{col}: dtype={df[col].dtype}")
        print(df[col].describe().to_string())
        print()