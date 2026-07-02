from pathlib import Path
import shutil
import pandas as pd
from datetime import datetime


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

BASE_DIR = Path(r"C:\Users\David.Levin\verification_app")

CURRENT_ROOT = BASE_DIR / "model"
UPDATE_ROOT = BASE_DIR / "updates" / "model"
BACKUP_ROOT = BASE_DIR / "archive_backups"

MODELS = [
    "hrrr",
    "nbm",
    "nbmqmd",
    "nbmqmd_exp",
    "nbm_exp",
    "urma",
    "ndfd",
]

ELEMENTS = [
    "wind",
    "precip6hr",
    "precip24hr",
    "snow6hr",
    "snow24hr",
    "snow48hr",
    "snow72hr",
    "rh",
    "maxt",
    "mint",
]

# Preview changes without modifying files
DRY_RUN = False

# If True, backup existing archive files before replacing them
MAKE_BACKUPS = True

# Compression for rewritten parquet files
PARQUET_COMPRESSION = "snappy"


# ---------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------
# By default, this drops exact duplicate rows across all columns.
#
# If you want to define duplicates by key fields instead, set this to
# something like:
#
# DEDUPE_KEY_COLUMNS = ["station_id", "valid_time", "init_time", "forecast_hour"]
#
# But because obs files may use stid instead of station_id, and some files
# may not have init_time or forecast_hour, the safest default is None.
# ---------------------------------------------------------------------

DEDUPE_KEY_COLUMNS = None


def get_dedupe_subset(df: pd.DataFrame):
    """
    Return the subset of columns to use for dropping duplicates.

    If DEDUPE_KEY_COLUMNS is None, use all columns.
    If specified, only use columns that actually exist in the dataframe.
    """
    if DEDUPE_KEY_COLUMNS is None:
        return None

    available = [col for col in DEDUPE_KEY_COLUMNS if col in df.columns]

    if not available:
        return None

    return available


def normalize_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize common datetime columns before de-duplication.

    This helps avoid cases where the same timestamp is stored with slightly
    different datetime metadata.
    """
    datetime_cols = [
        "valid_time",
        "init_time",
        "time",
        "datetime",
        "obs_time",
    ]

    for col in datetime_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.tz_localize(None)

    return df


def copy_new_file(update_file: Path, current_file: Path):
    """
    Copy a brand-new monthly archive file into the current archive.
    """
    if DRY_RUN:
        return

    current_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(update_file, current_file)


def backup_current_file(current_file: Path, model: str, element: str):
    """
    Backup an existing current archive file before replacing it.
    """
    if not MAKE_BACKUPS or DRY_RUN:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / timestamp / model / element
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_file = backup_dir / current_file.name
    shutil.copy2(current_file, backup_file)

    return backup_file


def merge_parquet_files(current_file: Path, update_file: Path, model: str, element: str):
    """
    Merge one current archive file with one update file.
    """
    current_df = pd.read_parquet(current_file)
    update_df = pd.read_parquet(update_file)

    current_rows = len(current_df)
    update_rows = len(update_df)

    current_df = normalize_datetime_columns(current_df)
    update_df = normalize_datetime_columns(update_df)

    combined = pd.concat([current_df, update_df], ignore_index=True, sort=False)

    combined_rows_before_dedupe = len(combined)

    dedupe_subset = get_dedupe_subset(combined)
    merged = combined.drop_duplicates(subset=dedupe_subset, keep="first")

    merged_rows = len(merged)
    duplicate_rows_removed = combined_rows_before_dedupe - merged_rows
    new_rows_added = merged_rows - current_rows

    backup_file = None

    if not DRY_RUN:
        backup_file = backup_current_file(current_file, model, element)

        temp_file = current_file.with_suffix(".tmp.parquet")

        merged.to_parquet(
            temp_file,
            index=False,
            compression=PARQUET_COMPRESSION,
        )

        temp_file.replace(current_file)

    return {
        "current_rows": current_rows,
        "update_rows": update_rows,
        "merged_rows": merged_rows,
        "new_rows_added": new_rows_added,
        "duplicate_rows_removed": duplicate_rows_removed,
        "backup_file": str(backup_file) if backup_file else "",
    }


def process_updates():
    """
    Loop through model/element directories and merge update files into
    the current archive.
    """
    log_rows = []

    print(f"Current archive root: {CURRENT_ROOT}")
    print(f"Update archive root:  {UPDATE_ROOT}")
    print(f"Dry run:              {DRY_RUN}")
    print()

    for model in MODELS:
        update_model_dir = UPDATE_ROOT / model

        if not update_model_dir.exists():
            print(f"[SKIP MODEL] No update directory: {update_model_dir}")
            continue

        for element in ELEMENTS:
            update_element_dir = update_model_dir / element
            current_element_dir = CURRENT_ROOT / model / element

            if not update_element_dir.exists():
                print(f"[SKIP ELEMENT] No update directory: {update_element_dir}")
                continue

            update_files = sorted(update_element_dir.glob("*_archive.parquet"))

            if not update_files:
                print(f"[SKIP ELEMENT] No update parquet files: {update_element_dir}")
                continue

            print()
            print(f"Processing {model}/{element}")
            print("-" * 80)

            for update_file in update_files:
                current_file = current_element_dir / update_file.name

                log_entry = {
                    "model": model,
                    "element": element,
                    "month_file": update_file.name,
                    "update_file": str(update_file),
                    "current_file": str(current_file),
                    "action": "",
                    "current_rows": "",
                    "update_rows": "",
                    "merged_rows": "",
                    "new_rows_added": "",
                    "duplicate_rows_removed": "",
                    "backup_file": "",
                    "status": "",
                    "error": "",
                }

                try:
                    if not current_file.exists():
                        print(f"[COPY NEW] {update_file.name}")

                        update_rows = len(pd.read_parquet(update_file))

                        copy_new_file(update_file, current_file)

                        log_entry.update(
                            {
                                "action": "copy_new_file",
                                "current_rows": 0,
                                "update_rows": update_rows,
                                "merged_rows": update_rows,
                                "new_rows_added": update_rows,
                                "duplicate_rows_removed": 0,
                                "status": "success",
                            }
                        )

                    else:
                        print(f"[MERGE] {update_file.name}")

                        merge_info = merge_parquet_files(
                            current_file=current_file,
                            update_file=update_file,
                            model=model,
                            element=element,
                        )

                        log_entry.update(
                            {
                                "action": "merge_existing_file",
                                "current_rows": merge_info["current_rows"],
                                "update_rows": merge_info["update_rows"],
                                "merged_rows": merge_info["merged_rows"],
                                "new_rows_added": merge_info["new_rows_added"],
                                "duplicate_rows_removed": merge_info["duplicate_rows_removed"],
                                "backup_file": merge_info["backup_file"],
                                "status": "success",
                            }
                        )

                        print(
                            f"        current={merge_info['current_rows']:,} | "
                            f"update={merge_info['update_rows']:,} | "
                            f"merged={merge_info['merged_rows']:,} | "
                            f"new_added={merge_info['new_rows_added']:,} | "
                            f"dupes_removed={merge_info['duplicate_rows_removed']:,}"
                        )

                except Exception as e:
                    print(f"[ERROR] {update_file}: {e}")

                    log_entry.update(
                        {
                            "action": "error",
                            "status": "failed",
                            "error": str(e),
                        }
                    )

                log_rows.append(log_entry)

    log_df = pd.DataFrame(log_rows)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_name = f"archive_update_log_{timestamp}{'_DRY_RUN' if DRY_RUN else ''}.csv"
    log_file = BASE_DIR / log_name

    log_df.to_csv(log_file, index=False)

    print()
    print("Summary")
    print("-------")
    print(f"Log written to: {log_file}")

    if DRY_RUN:
        print()
        print("DRY_RUN is True, so no archive files were modified.")
        print("Review the log, then set DRY_RUN = False to apply changes.")


if __name__ == "__main__":
    process_updates()