from pathlib import Path
import shutil

# Folder containing the downloaded model folders
SOURCE_ROOT = Path(".")

# New organized output root
DEST_ROOT = Path("./model")

# Preview changes without moving files
DRY_RUN = False

# Set to True if you want to overwrite existing destination files
OVERWRITE = False


def reorganize_parquet_files():
    parquet_files = list(SOURCE_ROOT.glob("*/*.parquet"))

    if not parquet_files:
        print("No parquet files found.")
        return

    moved_count = 0
    skipped_count = 0

    for src in parquet_files:
        old_model = src.parent.name
        stem = src.stem

        # Expected filename:
        # YYYY_MM_model_element_archive.parquet
        parts = stem.split("_")

        if len(parts) < 5:
            print(f"[SKIP] Unexpected filename format: {src}")
            skipped_count += 1
            continue

        year = parts[0]
        month = parts[1]

        # Last part should be "archive"
        if parts[-1] != "archive":
            print(f"[SKIP] Filename does not end with '_archive': {src}")
            skipped_count += 1
            continue

        # The model is expected to match the parent folder name
        model = old_model

        # Element is whatever comes between model and archive
        #
        # Example:
        # 2025_06_nbm_gust_archive.parquet
        # parts = ["2025", "06", "nbm", "gust", "archive"]
        #
        # Example with multi-part element:
        # 2025_06_nbm_24hr_qpf_archive.parquet
        # parts = ["2025", "06", "nbm", "24hr", "qpf", "archive"]
        filename_model = parts[2]
        element_parts = parts[3:-1]
        element = "_".join(element_parts)

        if filename_model != model:
            print(
                f"[WARN] Parent folder model '{model}' does not match "
                f"filename model '{filename_model}' for {src}"
            )

            # Use model from filename rather than folder if they differ
            model = filename_model

        if not element:
            print(f"[SKIP] Could not determine element from: {src}")
            skipped_count += 1
            continue

        new_filename = f"{year}_{month}_archive.parquet"
        dest = DEST_ROOT / model / element / new_filename

        if dest.exists() and not OVERWRITE:
            print(f"[SKIP] Destination exists: {dest}")
            skipped_count += 1
            continue

        print(f"{'[DRY RUN]' if DRY_RUN else '[MOVE]'} {src} -> {dest}")

        if not DRY_RUN:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))

        moved_count += 1

    print()
    print("Summary")
    print("-------")
    print(f"Files processed: {len(parquet_files)}")
    print(f"Files moved:     {moved_count}")
    print(f"Files skipped:   {skipped_count}")

    if DRY_RUN:
        print()
        print("DRY_RUN is True, so no files were actually moved.")


if __name__ == "__main__":
    reorganize_parquet_files()