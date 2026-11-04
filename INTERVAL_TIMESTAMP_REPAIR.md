# Correct legacy temperature and precipitation archives

Run this from the verification_app repository root, after pulling model-comparison.
Requires pandas and pyarrow in the active verification environment.

For your confirmed legacy NBMQMD archive, stop archive writers and the app, then run:

```powershell
python repair_local_interval_timestamps.py --source-root .\model --in-place --models nbmqmd
```

Use your actual local model root if different. It is the directory containing
`nbmqmd`, `obs`, `ndfd`, etc., not the individual maxt folder. Only selected model
interval datasets are repaired. Observations, NDFD, wind, gust, RH and snow are
untouched. No data is downloaded.

| Element | Shift both init_time and valid_time forward |
| --- | --- |
| maxt | 18 hours |
| mint | 18 hours |
| precip6hr | 6 hours |
| precip24hr | 24 hours |

Forecast lead hours and values are preserved. Rows crossing a month boundary are
routed to the corrected initialization-month file. Duplicate forecast keys keep
exactly their second occurrence in source filename/row order, matching the existing
repair policy; this is not a choice of a different forecast cycle.

The script checks lead consistency, exact Parquet round trips, row counts and file
hashes before installing replacements. It retains original datasets in a sibling
`model_timestamp_backup_<timestamp>_<id>/originals` directory and reports its path.
Wait for **INSTALLED**, not just the intermediate COMPLETE staging message. Keep
the backup, installation journal and repair manifest. A persistent root marker
and Parquet metadata block accidental repeated correction. An interrupted install
can be restored with `--rollback-backup <backup-directory>`; completed installs
are not automatically rolled back after new writes.

Only run this on datasets entirely created by the old decoder. Do not shift a mix
of legacy and already-corrected rows. For additional confirmed legacy datasets,
include their models in the same invocation, for example:

```powershell
python repair_local_interval_timestamps.py --source-root .\model --in-place --models nbmqmd nbmqmd_exp
```

Supported optional models are nbmqmd_exp (all four elements) and nbm/nbm_exp
(maxt/mint percentile archives). Select these only when their historical decoder
and affected fields are confirmed. `--elements maxt mint` can restrict the scope.

To write corrected copies without installing them:

```powershell
python repair_local_interval_timestamps.py --source-root .\model --output-root .\model_corrected_intervals --models nbmqmd
```

The output root must not already exist. Copy mode contains only repaired datasets,
so it is not a complete replacement archive containing observations and other models.

## App matching after correction

All pages use the same temperature target-date rule:

- NBM-family MaxT ending June 18 at 06Z verifies against the June 17 observation
  date, whose window is June 17 at 12Z through June 18 at 06Z.
- Corrected MinT ending June 17 at 18Z verifies against the June 17 observation date.
- Legacy MaxT labels at June 17 at 12Z and NDFD's June 17 date labels continue to
  verify against June 17 observations. The app does not fix legacy initialization
  labels automatically or guess their correct cycles.
- Precipitation uses the corrected valid timestamp as accumulation endpoint, with
  the existing duration check and reporting-time tolerance around that endpoint.

Date-range filters use the verification date, so a last-day MaxT endpoint falling
on the following day/month is still loaded. Model comparison uses that same date
for both forecast models and shared observations, including with a reference offset.

Restart the app and regenerate saved results after repair. Use real initialization
times (00Z/12Z for the default QMD schedule), not the old 06Z/18Z labels. Ensure the
fixed archiver decoder is deployed before resuming archive writes.

## Windows manifest replacement errors

`WinError 5` while replacing `manifest.json.tmp` with `manifest.json` means Windows
denied the progress-file replacement. A transient sharing lock is one possible
cause; the message alone does not identify the locking process or rule out a
permissions problem. The writer now uses unique temporary names, flushes and closes
files before replacement, and retries Windows access/sharing/lock errors up to
10 times (under 10 seconds of waiting). It never deletes the previous journal
as a workaround and preserves the original failure if recording that failure
also fails.

If this happens during staging, before any installation message, the model
archives have not been replaced. After a successful rollback/unchanged message,
pull the fixed script and rerun the same command. It creates a fresh backup and
staging directory. Keep the old incomplete directory for diagnostics; do not copy
its staged files over the live archive. If the replacement remains blocked,
close editors/previews or sync tools accessing the JSON files and check folder
permissions. The script still stops rather than installing unverified output.
