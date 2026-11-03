# Community Cloud usability pilot

Deploy **community-cloud-test**, a branch based on **model-comparison**. There is
no need to merge into main first. Main and model-comparison retain their local
setup; this branch also uses the existing local defaults unless cloud startup is
explicitly enabled in Streamlit secrets. The code branch and data Release need
not be the same: the existing test-data-v1 asset remains usable unchanged.

## Deploy the prepared branch

1. Open https://share.streamlit.io/ and choose **Create app**.
2. Select repository `david-levin11/verification_app`.
3. Select branch **community-cloud-test**.
4. Use entrypoint **web_app/app.py** and Python **3.12**.
5. In **Advanced settings → Secrets**, paste the `[cloud]` table from
   `.streamlit/secrets.toml.example`. The current public asset needs no token:

```toml
[cloud]
enabled = true
snapshot_id = "test-data-v1"
archive_url = "https://github.com/david-levin11/verification_app/releases/download/test-data-v1/verification-test-data-2026-11.zip"
archive_sha256 = "165ff495f35188ae6095fc0b55dbaef4a7bb708d052f12f7a4cef8502cf6a322"
```

6. Deploy and allow the first download/extraction to complete. The existing
   release asset is about 1.53 GB compressed, so startup can take several minutes.
7. Check each of the four pages before sharing. Map/Aggregate and comparison
   dates default to at most seven days within the snapshot's model/obs overlap.
   Storm Zoom gets an actual archived initialization, a date/hour picker, and the
   corresponding snapshot dates. Sample station IDs have both model and obs rows.
8. For organizational testing, open the deployed app's **Settings → Sharing** and
   choose **Only specific people can view this app**, then add testers yourself.
   This limits app viewers; it does not make a public GitHub Release private.

Do not commit actual tokens or `.streamlit/secrets.toml`. The tracked `.example`
file is a template only and will not turn cloud mode on by itself.

## Snapshot layout and automatic defaults

ZIP files may contain `model/`, `metadata/` and `derived/refs/` at the top level,
or beneath one wrapping directory. The app finds one model directory and prefers
`ak_station_metadata.parquet`. Model archives include observations under
`model/obs/{element}/`. REFS files remain under `derived/refs/{element}/`.

The loader streams the ZIP to a separate temporary cache, verifies its SHA-256,
checks extraction paths, extracts and validates the data, then atomically marks
the snapshot ready. It never extracts into your local production directories.
Concurrent viewers reuse the same prepared snapshot. Files are downloaded again
if the complete cache is removed. Cloud disk storage is a cache, not the durable
source; keep the Release asset available.

The homepage shows the fixed snapshot ID, default coverage and a file-based model/
element inventory. Defaults are obtained from bounded queries of time and station
columns rather than loading the entire archive into pandas. Each page gets
absolute model, observation-via-model-root, metadata and REFS paths. User edits and
map station selections retain their existing behavior; navigating pages does not
reset a chosen date or path. Verification/matching/scoring code is unchanged.

If autodetection reports ambiguity, add paths **relative to the ZIP root**:

```toml
model_subdir = "verification-test-data/model"
metadata_file = "verification-test-data/metadata/ak_station_metadata.parquet"
refs_subdir = "verification-test-data/derived/refs"
```

Optional `start_date` and `end_date` select a curated default window within the
detected default model/observation coverage. There is no promise that every
model, initialization, element or station is available throughout that window.
Existing missing-data diagnostics still apply.

## Updating code or data

Keep feature development on model-comparison. Merge reviewed feature updates into
community-cloud-test when ready to update the pilot. No main merge or Release
retagging is needed for code updates.

For new data, publish a new versioned Release asset, update `snapshot_id`,
`archive_url` and `archive_sha256` in Streamlit secrets, then reboot the cloud app.
Changing URL/digest selects a new isolated cache. Do not overwrite an asset while
leaving the configured digest unchanged: startup will correctly reject it.
Old cache directories may be removed while the app is stopped to recover disk.

For a private data repository, use a GitHub **release asset API URL** and a
read-only `github_token` in secrets. The token needs read access to that data
repository; do not use a private browser download URL with the token. Tokens are
sent only to api.github.com and are not included in snapshot manifests.

## Local development and validation

Install the pinned app dependencies with `python -m pip install -r requirements.txt`.
Without `[cloud] enabled = true`, `streamlit run web_app/app.py` uses the original
local path/date defaults. To test cloud behavior locally, copy the example to
`.streamlit/secrets.toml`; remove that file and restart to return to local mode.

Synthetic ZIP/Parquet tests cover streaming/digest checks, failed-download retry,
wrapped layouts, unsafe paths/links, concurrent startup, real date/run detection,
all four pages, and unchanged local defaults. The actual 1.53 GB production asset
still needs its initial cloud smoke test; preparing this branch does not deploy
the app or invite users automatically.


## Archive preparation and startup health checks

After clicking Prepare test archive, an archive preparation page shows progress while a shared background worker
streams the ZIP to disk, verifies its digest, extracts it and checks coverage.
The page refreshes its status every two seconds and opens the app when ready.
Download progress and coverage stages also appear in the server logs. A failed
preparation offers **Retry archive preparation** and logs the underlying error.
The worker does not hold up Streamlit's script health check; concurrent visitors
reuse the same job. The extracted archive is scanned once before publication.

If an older deployment reports a 60-second `/script-health-check` timeout, deploy
the latest `community-cloud-test` commit and reboot the app. That timeout alone
does not prove a memory limit was exceeded. If the process still stops, inspect
the new stage messages and the platform resource logs to identify the cause.

Validation includes a real Streamlit server with a deliberately slow archive
worker: repeated script-health checks return HTTP 200 without starting the worker.

Startup coverage discovery stops after finding the first usable model/observation
selection. Other models remain available; their shared coverage is checked when
a comparison is requested. Startup DuckDB queries use one thread and a 128 MB
buffer limit (this is not a limit on total Python process memory).


## Browser-initiated archive preparation

With cloud mode enabled, the initial page shows **Prepare test archive**. Click
it to start (or reuse) the shared snapshot preparation worker. Deployment health
checks render this landing screen without launching a download or a coverage scan.
After preparation, the page opens the dashboard automatically; **Check archive
status** provides a manual refresh if the automatic transition is delayed.
Every new browser session clicks Prepare once; the disk/process caches still
avoid duplicate downloads. Keep `[cloud] enabled = true` to use this workflow.

The homepage always completes its normal script run, including before preparation,
while waiting and on a preparation error. Archive-dependent verification pages
still pause until the snapshot is ready. The welcome screen does not use an
early `st.stop()` on the homepage.
