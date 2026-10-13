from pathlib import Path
import pandas as pd

root = Path(r"C:\Users\David.Levin\verification_app\model\nbmqmd\precip6hr")
keys = ["station_id", "init_time", "valid_time", "forecast_hour"]

for path in sorted(root.glob("*_archive.parquet")):
    df = pd.read_parquet(path)
    duplicates = df.loc[df.duplicated(keys, keep=False)]

    if duplicates.empty:
        print(f"OK: {path.name}", flush=True)
        continue

    groups = duplicates.groupby(keys, dropna=False).ngroups
    distinct_rows = duplicates.drop_duplicates()
    conflicts = distinct_rows.loc[
        distinct_rows.duplicated(keys, keep=False)
    ]
    conflict_groups = (
        conflicts.groupby(keys, dropna=False).ngroups
        if not conflicts.empty else 0
    )

    print(f"\nFILE: {path}", flush=True)
    print(f"Total rows: {len(df):,}")
    print(f"Rows involved in duplicate keys: {len(duplicates):,}")
    print(f"Duplicate key groups: {groups:,}")
    print(f"Exact repeated rows: {len(duplicates) - len(distinct_rows):,}")
    print(f"Key groups with differing row contents: {conflict_groups:,}")
    print("\nExample duplicate rows:")
    print(duplicates.sort_values(keys).head(12).to_string(index=False))
    break
