# Alaska Point Verification Dashboard

A Streamlit app for verifying archived weather forecasts against station
observations in Alaska. It reads monthly Parquet archives produced by the
[Alaska verification archiver](https://github.com/david-levin11/alaska_verification).
Forecast and observation archives are read-only inputs; this app does not collect
new forecasts or observations.

## What you can do

| Page | Purpose |
| --- | --- |
| Map Explorer | Map station verification metrics, filter stations by metadata, and select stations for other pages. |
| Aggregate Verification | Summarize performance across stations, dates, forecast leads, and event categories. |
| Storm Specific Zoom | Explore a model run through spatial snapshots, storm evolution, and station details; optionally compare a second model. |
| Model Comparison | Compare two models against the same matched observations, with reference-time offsets and deterministic or probabilistic scoring. |

Model options include NBM, NBMQMD, NDFD, HRRR, RRFS, REFS, and configured
experimental variants. URMA is available for supported verification combinations.
Core workflows cover wind, gust, relative humidity, minimum RH, maximum/minimum temperature,
and 6-/24-hour precipitation. Available elements and probability controls depend
on the selected model and page; see [the configuration](web_app/config.py).
Snow has separate archive/observation requirements and is not supported in Storm
Specific Zoom.

Features include bias, MAE/RMSE, categorical event verification, probabilistic
diagnostics where available, wind-direction angular errors, and minimum observed
wind-speed filters. Probabilistic station graphics show distribution information;
deterministic guidance does not require percentile fields. REFS completeness is
judged against the expected membership at each lead, including scheduled member
departures.

Each page has independent analysis controls. Map Explorer station selections
propagate to the other analysis pages; manual station lists are also supported.
All available archived forecast hours are eligible within the selected lead
range, without inventing missing forecast increments.

## Map color scales

Map Explorer, Model Comparison station differences, and Storm Zoom spatial
snapshots offer **Standard**, **Fit to data**, and **Custom** under **Map color
scale**. Standard uses fixed ranges by element/metric; Fit to data uses robust
95th-percentile limits (5th–95th for forecast/observed values). Custom accepts a
symmetric ± limit for signed metrics and minimum/maximum limits otherwise.
Settings are independent by page, element, and metric and survive page changes.
These controls recolor existing results without rerunning archive queries.

| Element | Standard bias/signed error | Standard MAE/RMSE/absolute error |
| --- | --- | --- |
| 6-hour precipitation | ±0.25 in | 0–0.50 in |
| 24-hour precipitation | ±0.50 in | 0–1.00 in |
| Maximum/minimum temperature | ±5°F | 0–10°F |
| RH/minimum RH | ±10 percentage points | 0–20 percentage points |
| Wind/gust | ±5 kt | 0–10 kt |

Model Comparison maps show **advantage for A**, not the original scores; their
standard signed limits use the element's bias limit for continuous metrics and
±0.25 for probability/proportion-score differences. Positive advantage favors A;
negative favors B. Bias compares distance from zero, and frequency bias compares
distance from one. Standard POD/FAR/CSI/probability maps keep a 0–1 scale;
percentiles use 0–100. Counts adapt to the data rather than use physical defaults.

Colorbars sit below each map, use compact labels, and always have extensions at
both ends. Sequential scales (including MAE and POD) use five discrete color bands
with identical boundaries for markers and legends. Signed scales remain smooth.
Values outside a color range use end colors;
a caption reports how many plotted station values fall outside each limit.
Tooltips, tables, scores, and selected stations retain their actual values.
Fixed ranges are display defaults, not acceptable-error thresholds. Current
limits and units appear inside the scale controls. Shared defaults live in
[web_app/color_scales.py](web_app/color_scales.py).

## Quick start with conda

Use Python 3.12 in a dedicated environment, separate from the archiver.
Run these commands from the directory where you want to install the app:

```bash
git clone --branch main https://github.com/david-levin11/verification_app.git
cd verification_app
conda env create -f environment.yml
```

Before launching, configure your data locations as described below. Then, from
the repository root:

```bash
conda run --no-capture-output -n verification-app python -m streamlit run web_app/app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true
```

For local use, open `http://localhost:8501`. Stop the foreground process with
Ctrl+C. The conda environment uses the pinned runtime dependencies in
[requirements.txt](requirements.txt). An existing Python 3.12 environment can
instead install them with `python -m pip install -r requirements.txt`.

## Configure the archive paths

Create `.streamlit/secrets.toml` **inside the repository root**:

```toml
[local]
archive_root = '/data/alaska_verification/model'
refs_root = '/data/alaska_verification/derived/refs'
metadata_path = '/data/alaska_verification/metadata/ak_station_metadata.parquet'
```

Replace these example paths with the actual server or local paths. Windows paths
are supported; use single-quoted TOML strings to keep backslashes literal, e.g.
`archive_root = 'G:\My Drive\Verification\model'`.

| Setting | Must point to |
| --- | --- |
| `archive_root` | The directory containing model-name folders and `obs`. |
| `refs_root` | The REFS derived directory containing element folders such as `wind`, `rh`, and `precip6hr`; do not append the element to this setting. |
| `metadata_path` | The station metadata Parquet or CSV file. |

These are administrator settings. Visitors cannot edit data paths through the
app. The same settings apply to all four pages, independently of browser state.
The settings file is excluded from Git; create it separately on each machine.
Restart Streamlit after changing it, and launch from the repository root so
Streamlit can discover the file.

When settings are omitted, the app uses `model/`, `derived/refs/`, and
`metadata/ak_station_metadata.parquet` inside the repository. Relative configured
paths also resolve from the repository root. No data archives are bundled with
the app. See [LOCAL_CONFIGURATION.md](LOCAL_CONFIGURATION.md) for details.

## Expected archive layout

The three configured locations can be on different filesystems. A typical layout
contains paths like:

```text
model/nbm/wind/2026_10_archive.parquet
model/nbmqmd/wind/2026_10_archive.parquet
model/ndfd/wind/2026_10_archive.parquet
model/rrfs/wind/2026_10_archive.parquet
model/obs/wind/2026_10_archive.parquet
derived/refs/wind/2026_10_archive.parquet
derived/refs/rh/2026_10_archive.parquet
derived/refs/precip6hr/2026_10_archive.parquet
metadata/ak_station_metadata.parquet
```

Other elements use their own element directories. Some model and observation
archives combine wind and gust; the app supports documented gust-column fallback.
REFS wind and gust share the derived `wind` archive. Archive schemas must be
compatible with the archiver and app; arbitrary Parquet files are not sufficient.
Google Drive for desktop can expose a local filesystem path on Windows. Keep
Drive running and allow files to synchronize; offline availability can reduce
on-demand download delays.

## Matching and interpreting comparisons

- Instantaneous observations match using a configurable time tolerance, so an
  observation reported at :53 can verify the following top-of-hour forecast.
- Temperature extrema and precipitation retain their date/window and accumulation
  conventions. A wide time tolerance does not make different accumulation
  durations equivalent.
- Model Comparison scores common forecast cases against the same observation.
  A negative Model B reference offset selects earlier guidance, useful when
  comparing human-edited NDFD with the NBM cycle available to forecasters.
- A configured model/element does not guarantee archive coverage. Review the
  matching diagnostics and sample counts before interpreting a score difference.

## Internal server deployment

`main` is the deployment baseline. The experimental `community-cloud-test` branch
is separate and is not required to read the production archive.

The intended server setup uses a dedicated conda environment, a persistent
Streamlit process managed by systemd or the site's process manager, and Apache
as the internal reverse proxy. Apache must forward both HTTP and WebSocket
traffic. Keeping Apache running alone does not keep Streamlit running. Adapt
proxy configuration to the Apache version and chosen URL/subpath.

The server account needs read access to the archive and metadata, and writable
temporary space. Configure internal-network access at the server/proxy layer;
this app does not supply an organizational sign-in flow. Before making it
available to users, run a short production-data test, including a REFS case, and
confirm navigation, maps, tables, and WebSocket connectivity through Apache.

Record the deployed commit or published release tag. Stop the app for code and
dependency updates, restart, and repeat the production-data test. Viewer rollback
should not modify the production archive. Paths and installation details are in
[LOCAL_CONFIGURATION.md](LOCAL_CONFIGURATION.md).

## Tests and troubleshooting

The regression suite uses synthetic data. In the app environment:

```bash
conda run -n verification-app python -m pip install pytest
conda run --no-capture-output -n verification-app python -m pytest -q
```

Passing Python tests does not validate the production archive or the browser's
network connection to a hosted app. If a map or table fails to render, inspect
both the Streamlit service log and browser network/console errors. For missing
verification cases, first check configured paths, archive months, station IDs,
lead ranges, reference offsets, and observation windows.

## Detailed guides

- [Administrator paths and installation](LOCAL_CONFIGURATION.md)
- [Model comparison and matching](MODEL_COMPARISON.md)
- [Storm verification](STORM_VERIFICATION.md)
- [Minimum relative humidity](MINRH_VERIFICATION.md)
- [Wind gust verification](GUST_VERIFICATION.md)
- [RRFS and derived REFS](RRFS_REFS_VERIFICATION.md)
- [Verification changes and conventions](VERIFICATION_CHANGES.md)
- [Legacy interval timestamp repair](INTERVAL_TIMESTAMP_REPAIR.md)
