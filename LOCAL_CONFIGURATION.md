# Administrator archive configuration

Archive locations are configured on the machine hosting Streamlit. Visitors cannot
view or edit these locations through sidebar controls. All four pages use the
same configuration; browser session values cannot override it.

Create `.streamlit/secrets.toml` in the repository root and launch from that root:

```toml
[local]
archive_root = '/path/to/alaska_verification/model'
refs_root = '/path/to/alaska_verification/derived/refs'
metadata_path = '/path/to/alaska_verification/metadata/ak_station_metadata.parquet'
```

Windows users can keep their existing Google Drive paths in this same section.
Use single-quoted TOML strings for Windows paths so backslashes remain literal.
Do not commit machine-specific secrets; the file is ignored by Git.

`archive_root` contains model-name directories and `obs`. `refs_root` directly
contains `wind`, `rh`, and `precip6hr` (omit the element from the configured path).
Metadata may be a Parquet or CSV file supported by the app.

If not configured, paths default to `model/`, `derived/refs/`, and
`metadata/ak_station_metadata.parquet` inside the repository. Relative configured
paths are also resolved from the repository root, independent of the launch
working directory. Streamlit discovers project secrets from the launch working
directory, so launch from the repository root. Restart after changing settings.
The server account needs read access to archives/metadata and writable temporary
space. These settings do not change archiver output locations.

## Installation and local smoke test

Use a dedicated environment, separate from the production archiver:

```bash
conda env create -f environment.yml
conda run --no-capture-output -n verification-app python -m streamlit run web_app/app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true
```

The pinned Python 3.12 dependencies are in `requirements.txt`. This installation
uses the local/production archives; it has no Community Cloud snapshot startup.
First verify a short date range and a few stations, including a REFS case, against
the real production archive. Automated tests use synthetic data and do not replace
this server smoke test. Apache proxy and process-manager configuration must be
adapted by the server administrator to the internal URL and operating system.

Deploy `main` or a tested release tag. For updates, record the running commit/tag,
stop the app, update code/dependencies, then restart and repeat the smoke test.
Use the recorded tag for rollback; do not modify the production archive to roll
back the viewer. Keep the experimental `community-cloud-test` branch separate.
