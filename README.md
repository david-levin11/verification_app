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
wind-speed filters. Six-hour precipitation station graphics show endpoint markers
for deterministic forecasts or a single probabilistic plume, without accumulation
window bars or a lower window panel. Probabilistic station graphics show distribution information;
deterministic guidance does not require percentile fields. REFS completeness is
judged against the expected membership at each lead, including scheduled member
departures.

Each page has independent analysis controls. Map Explorer station selections
propagate to the other analysis pages; manual station lists are also supported.
All available archived forecast hours are eligible within the selected lead
range, without inventing missing forecast increments.

## Dates, archive coverage, and downloads

Analysis pages default to the latest calendar month with overlapping forecast
and observation archive coverage, ending on the last available day. Model
Comparison considers both models and observations. Untouched defaults follow a
change of model or element; deliberately selected dates remain unchanged.
Storm Zoom also defaults its initialization to the latest archived run whose
initialization timestamps are available in the metadata.

Before running, the controls show available UTC dates and explain partial
coverage or gaps in plain language. A request with no archive overlap is disabled;
a partial request can run using available data. Each monthly file is checked for
an appropriate value field, so a temperature file misplaced in a precipitation
folder is identified before querying. These checks read cached Parquet footer
statistics, not full archives. Dates fall back to filename months with an explicit
estimate notice if statistics are missing. Coverage describes archive dates;
individual stations, runs, leads, observation windows, and valid values still
require matching when an analysis runs.

Results show maps, plots, and headline metrics. Detailed tables, station metadata,
paired cases, scorecards, and technical diagnostics are available as CSV/JSON
under **Downloads — tables and diagnostics**, rather than displayed inline.
Archives and administrator-configured data paths are not changed by these controls.

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

Colorbars are centered below each map, use compact labels, and always have extensions at
both ends. Sequential scales (including MAE and POD) use five discrete color bands
with identical boundaries for markers and legends. Signed scales remain smooth. Absolute temperature maps (forecast/observed values
and station forecast/observed maxima) use 5°F bands, including negative temperatures.
The compact legend thins its tick labels when needed; all 5°F color boundaries
remain present. Custom limits are honored exactly, with shorter end bands when needed.
Values outside a color range use end colors;
a caption reports how many plotted station values fall outside each limit.
Tooltips, tables, scores, and selected stations retain their actual values.
Fixed ranges are display defaults, not acceptable-error thresholds. Current
limits and units appear inside the scale controls. Shared defaults live in
[web_app/color_scales.py](web_app/color_scales.py).

## Category charts and all-sites overview

After building a station map, **Station map** and **All-sites overview** tabs
separate the map from category-frequency and confusion-matrix graphics. The
overview pools every matched pair in the completed run, including sites without
coordinates. Station selections and map sample/color filters do not restrict it;
use Aggregate Verification for a selected group. Probability verification also
appears in the overview for probabilistic models. Rebuild a map from an older
session to populate its category chart inputs.

Map Explorer and Aggregate Verification share **Chart categories** controls.
Choose **Default** or **Custom**, entering strictly increasing, comma-separated
numeric upper boundaries (1–30 values). Categories include open-ended tails;
each boundary belongs to the bin ending at that value. Invalid entries show a
message and use defaults until corrected. Controls are independent by page and
weather element, redraw the saved paired values without querying archives, and
do not change matching, threshold metrics, or map color scales. Wind defaults
retain Marine/Beaufort names; custom categories use numeric labels. Precipitation
and wind defaults are unchanged.

New default finite boundaries (upper inclusive):

| Element | Boundaries |
| --- | --- |
| Maximum temperature (°F) | −40, −20, 0, 10, 20, 32, 50, 70, 80 |
| Minimum temperature (°F) | −50, −40, −30, −20, −10, 0, 10, 20, 32, 50 |
| RH and minimum RH (%) | 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90 |

For example, MaxT starts with ≤−40°F and ends with >80°F. Numeric interval
labels make every category explicit. Empty categories remain on the axes.
Category-frequency bars show same/lower/higher forecast categories within each
observed category (each populated bar sums to 100%, with case counts). Confusion
matrix cells show percentages of all categorized pairs. Stations with more pairs
contribute more weight. Detailed categorized cases, confusion counts, and category
definitions remain downloadable, without inline text tables.

## Map Explorer probability verification

For probabilistic guidance, Map Explorer offers Brier score, binned reliability
error, mean forecast probability, observed event frequency on probability cases,
and mean probability minus observed frequency (percentage points). Positive
probability differences mean probabilities were too high on average; errors in
different probability bins can cancel, so inspect the reliability plot as well.
The existing deterministic forecast event frequency uses the selected point
forecast; it is distinct from mean forecast probability.

Zero-probability event counts and rates identify observed threshold events given
exactly zero probability. The rate denominator is **all observed events among
valid matched probability cases**, not all forecasts. No observed events gives an
undefined rate, omitted from that map. Tooltips include probability case counts,
observed event counts, and zero-probability forecast counts. A minimum probability
case control filters map stations only; colors retain Standard/Fit/Custom options.

The all-sites probability overview reuses Aggregate Verification's reliability
plot with 10% probability bins and sample-count bars. It includes all valid cases
in the completed map run, even stations without coordinates, and weights each
forecast/observation case equally. Stations with more cases contribute more.
Map selection and display filters do not change this overview; use Aggregate
Verification for selected groups. The plot and scores keep the completed run's
threshold, operator, dates, and model when controls are edited. Detailed case,
bin, summary, and station results remain downloads rather than inline tables.
Missing probabilities/observations and incomplete REFS ensembles are excluded,
never converted to zero. Matching rules and the Storm comparison map are unchanged.

## Storm probability outcomes

For a probabilistic Storm Zoom snapshot, choose **Threshold probability**.
**Observed outcomes to highlight** lets users highlight observed events with
non-zero probability, observed events with exactly zero probability, or both.
**Show only highlighted outcomes** filters the map display without changing
verification cases, scores, station selection, or the other graphics.

Probability remains the circle fill color. A green outline and **+** identify an
observed event assigned non-zero probability; a red outline and **!** identify an
observed event assigned zero probability. Other outcomes are gray, and tooltips
identify observations that are missing. Missing observations never count as an
event not occurring. Very small positive probabilities remain distinct from zero
in classifications and tooltip text. Gold still marks the selected station.

The event uses the selected threshold/operator and the existing matched report
or accumulation window. These are snapshot outcomes, not a reliability assessment:
a small non-zero chance followed by an event is not automatically a good forecast.
Quantile-derived probabilities remain estimates with the documented tie/tail
assumptions; tooltips retain the probability source. Incomplete REFS distributions
and unavailable probabilities are not converted to zero.

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
