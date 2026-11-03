# Local archive defaults

On the `model-comparison` branch, optional Streamlit secrets set initial paths
across Map Explorer, Aggregate Verification, Storm Zoom and Model Comparison.

In the directory from which you launch Streamlit, create `.streamlit/secrets.toml`:

```toml
[local]
archive_root = 'G:\My Drive\Verification\model'
refs_root = 'G:\My Drive\Verification\derived\refs'
# Optional; omit to keep your existing metadata default:
# metadata_path = 'G:\My Drive\Verification\metadata\ak_station_metadata.parquet'
```

Use your actual filesystem paths, not web URLs. Single-quoted TOML strings keep
Windows backslashes literal. `archive_root` contains model names and `obs`;
`refs_root` contains the REFS element folders (wind, rh, precip6hr).

For a predictable location, launch from the repository root:

```text
python -m streamlit run web_app/app.py
```

Restart Streamlit and refresh the browser after changing defaults. Existing
session/page edits take precedence. Inputs remain editable, independently per
page. REFS root is shown when REFS is selected. Keep Google Drive for desktop
running and wait for the files you need to synchronize.

The settings file is ignored by Git. This configuration neither downloads the
cloud test snapshot nor changes shared repository defaults. Remove `[local]`
to return to the original path defaults. These settings affect readers only;
they do not change the archiver's output paths.
