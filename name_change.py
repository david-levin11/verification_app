from pathlib import Path

ROOT = Path("./model")

MODELS = ["hrrr", "nbm", "nbmqmd", "nbmqmd_exp", "nbm_exp", "urma", "ndfd"]

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
    "gust"
]

DRY_RUN = False
OVERWRITE = False


def rename_archive_files():
    renamed_count = 0
    skipped_count = 0
    checked_count = 0

    root = ROOT.resolve()
    print(f"Root directory: {root}")
    print()

    for model in MODELS:
        model_dir = ROOT / model

        if not model_dir.exists():
            print(f"[SKIP MODEL] Missing directory: {model_dir}")
            continue

        for element in ELEMENTS:
            element_dir = model_dir / element

            if not element_dir.exists():
                print(f"[SKIP ELEMENT] Missing directory: {element_dir}")
                continue

            parquet_files = list(element_dir.glob("*.parquet"))

            if not parquet_files:
                print(f"[SKIP ELEMENT] No parquet files in: {element_dir}")
                continue

            print(f"\nChecking: {element_dir}")

            expected_suffix = f"_{model}_{element}_archive"

            for src in parquet_files:
                checked_count += 1
                stem = src.stem

                # Already renamed correctly, e.g. 2025_10_archive.parquet
                if stem.endswith("_archive") and not stem.endswith(expected_suffix):
                    parts = stem.split("_")
                    if len(parts) == 3 and parts[2] == "archive":
                        print(f"[OK] Already renamed: {src.name}")
                        skipped_count += 1
                        continue

                # Expected old format:
                # YYYY_MM_{model}_{element}_archive.parquet
                if not stem.endswith(expected_suffix):
                    print(f"[SKIP FILE] Unexpected filename pattern: {src.name}")
                    skipped_count += 1
                    continue

                year_month = stem.removesuffix(expected_suffix)

                # Basic sanity check: should be YYYY_MM
                ym_parts = year_month.split("_")
                if len(ym_parts) != 2:
                    print(f"[SKIP FILE] Could not parse YYYY_MM from: {src.name}")
                    skipped_count += 1
                    continue

                year, month = ym_parts

                if not (year.isdigit() and len(year) == 4 and month.isdigit() and len(month) == 2):
                    print(f"[SKIP FILE] Invalid YYYY_MM in: {src.name}")
                    skipped_count += 1
                    continue

                dest = src.with_name(f"{year_month}_archive.parquet")

                if dest.exists() and not OVERWRITE:
                    print(f"[SKIP FILE] Destination already exists: {dest.name}")
                    skipped_count += 1
                    continue

                action = "[DRY RUN]" if DRY_RUN else "[RENAME]"
                print(f"{action} {src.name} -> {dest.name}")

                if not DRY_RUN:
                    src.rename(dest)

                renamed_count += 1

    print()
    print("Summary")
    print("-------")
    print(f"Files checked:  {checked_count}")
    print(f"Files renamed:  {renamed_count}")
    print(f"Files skipped:  {skipped_count}")

    if DRY_RUN:
        print()
        print("DRY_RUN is True, so no files were actually renamed.")
        print("Set DRY_RUN = False after reviewing the output.")


if __name__ == "__main__":
    rename_archive_files()