from pathlib import Path
import pandas as pd


ARCHIVE_ROOT = Path(r"C:\Users\David.Levin\verification_app\model")
MODEL = "ndfd"

ELEMENTS = [
    "wind",
    "gust",
    "precip6hr",
    "snow6hr",
    "maxt",
    "mint",
    "rh",
]


def inspect_all_ndfd_files():
    rows = []

    for element in ELEMENTS:
        element_dir = ARCHIVE_ROOT / MODEL / element

        if not element_dir.exists():
            print(f"[SKIP] Missing directory: {element_dir}")
            continue

        parquet_files = sorted(element_dir.glob("*_archive.parquet"))

        if not parquet_files:
            print(f"[SKIP] No parquet files found: {element_dir}")
            continue

        for parquet_path in parquet_files:
            print(f"Reading {parquet_path}")

            try:
                df = pd.read_parquet(parquet_path)

                if "forecast_hour" in df.columns:
                    forecast_hours = sorted(df["forecast_hour"].dropna().unique())
                else:
                    forecast_hours = []

                row = {
                    "element": element,
                    "file": parquet_path.name,
                    "rows": len(df),
                    "columns": ", ".join(df.columns),
                    "has_forecast_hour": "forecast_hour" in df.columns,
                    "unique_forecast_hours": forecast_hours,
                    "num_unique_forecast_hours": len(forecast_hours),
                }

                if "valid_time" in df.columns:
                    valid_time = pd.to_datetime(df["valid_time"], errors="coerce")
                    row["valid_time_min"] = valid_time.min()
                    row["valid_time_max"] = valid_time.max()

                if "init_time" in df.columns:
                    init_time = pd.to_datetime(df["init_time"], errors="coerce")
                    row["init_time_min"] = init_time.min()
                    row["init_time_max"] = init_time.max()

                rows.append(row)

            except Exception as e:
                rows.append(
                    {
                        "element": element,
                        "file": parquet_path.name,
                        "error": str(e),
                    }
                )

    summary = pd.DataFrame(rows)

    out_file = Path("ndfd_parquet_inspection_summary.csv")
    summary.to_csv(out_file, index=False)

    print()
    print("Summary written to:")
    print(out_file.resolve())

    if not summary.empty:
        print()
        print(summary[[
            "element",
            "file",
            "rows",
            "has_forecast_hour",
            "num_unique_forecast_hours",
            "unique_forecast_hours",
        ]].to_string(index=False))


if __name__ == "__main__":
    inspect_all_ndfd_files()