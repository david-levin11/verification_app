from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd
import geopandas as gpd
import requests
from shapely.geometry import Point


# =============================================================================
# Configuration
# =============================================================================

BASE_DIR = Path(r"C:\Users\David.Levin\verification_app")
OUTPUT_DIR = BASE_DIR / "metadata"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SYNOPTIC_METADATA_URL = "https://api.synopticdata.com/v2/stations/metadata"

NWS_MAPSERVER_BASE = (
    "https://mapservices.weather.noaa.gov/static/rest/services/"
    "nws_reference_maps/nws_reference_map/MapServer"
)

ZONE_LAYERS = {
    "public_zone": 8,
    "coastal_marine_zone": 5,
    "offshore_zone": 6,
}

# Alaska WFOs
AK_WFOS = ["AJK", "AFC", "AFG"]

# Use active stations by default. Set to None to include all stations returned by Synoptic.
SYNOPTIC_STATUS = "active"

# If you want only wind-reporting stations, keep this as wind_speed.
# You can change to None if you want all AK Synoptic sites.
SYNOPTIC_VARS = None

# Output files
CSV_OUT = OUTPUT_DIR / "ak_station_metadata.csv"
PARQUET_OUT = OUTPUT_DIR / "ak_station_metadata.parquet"
GPKG_OUT = OUTPUT_DIR / "ak_station_metadata.gpkg"


# =============================================================================
# Helper functions
# =============================================================================

def get_synoptic_token() -> str:
    """
    Get Synoptic API token from environment variable.

    In PowerShell:
        $env:SYNOPTIC_TOKEN = "your_token_here"

    Or permanently:
        setx SYNOPTIC_TOKEN "your_token_here"
    """
    token = os.getenv("SYNOPTIC_TOKEN")

    if not token:
        raise RuntimeError(
            "Missing SYNOPTIC_TOKEN environment variable. "
            "In PowerShell, run: $env:SYNOPTIC_TOKEN = 'your_token_here'"
        )

    return token


def request_json(url: str, params: dict, timeout: int = 60) -> dict:
    """
    Request JSON with basic error handling.
    """
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_synoptic_ak_stations(token: str) -> pd.DataFrame:
    """
    Fetch Alaska station metadata from Synoptic.

    Uses:
        state=AK
        vars=wind_speed
        status=active
        complete=1
        sensorvars=1

    Returns a flat pandas DataFrame.
    """
    params = {
        "token": token,
        "state": "AK",
        "complete": 1,
        "sensorvars": 1,
        "output": "json",
    }

    if SYNOPTIC_STATUS:
        params["status"] = SYNOPTIC_STATUS

    if SYNOPTIC_VARS:
        params["vars"] = SYNOPTIC_VARS

    data = request_json(SYNOPTIC_METADATA_URL, params=params)

    summary = data.get("SUMMARY", {})
    response_code = str(summary.get("RESPONSE_CODE", ""))

    if response_code not in {"1", "OK"}:
        raise RuntimeError(f"Synoptic metadata request failed: {summary}")

    stations = data.get("STATION", [])

    if not stations:
        raise RuntimeError("Synoptic returned zero AK stations.")

    rows = []

    for stn in stations:
        por = stn.get("PERIOD_OF_RECORD") or {}

        sensor_vars = stn.get("SENSOR_VARIABLES") or {}
        available_vars = ",".join(sorted(sensor_vars.keys())) if isinstance(sensor_vars, dict) else ""

        row = {
            "station_id": stn.get("STID"),
            "synoptic_id": stn.get("ID"),
            "name": stn.get("NAME"),
            "status": stn.get("STATUS"),
            "mnet_id": stn.get("MNET_ID"),
            "state": stn.get("STATE"),
            "country": stn.get("COUNTRY"),
            "cwa_synoptic": stn.get("CWA"),
            "nws_zone_synoptic": stn.get("NWSZONE"),
            "nws_fire_zone_synoptic": stn.get("NWSFIREZONE"),
            "latitude": pd.to_numeric(stn.get("LATITUDE"), errors="coerce"),
            "longitude": pd.to_numeric(stn.get("LONGITUDE"), errors="coerce"),
            "elevation_ft": pd.to_numeric(stn.get("ELEVATION"), errors="coerce"),
            "elevation_dem_ft": pd.to_numeric(stn.get("ELEV_DEM"), errors="coerce"),
            "timezone": stn.get("TIMEZONE"),
            "restricted": stn.get("RESTRICTED"),
            "period_of_record_start": por.get("start"),
            "period_of_record_end": por.get("end"),
            "available_vars": available_vars,
        }

        rows.append(row)

    df = pd.DataFrame(rows)

    df = df.dropna(subset=["station_id", "latitude", "longitude"]).copy()
    df = df.drop_duplicates(subset=["station_id"]).copy()

    return df


def stations_to_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Convert station DataFrame to GeoDataFrame in EPSG:4326.
    """
    geometry = [
        Point(lon, lat)
        for lon, lat in zip(df["longitude"], df["latitude"])
    ]

    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


def fetch_arcgis_layer_geojson(
    layer_id: int,
    where: str = "1=1",
    out_fields: str = "*",
) -> gpd.GeoDataFrame:
    """
    Fetch an ArcGIS REST layer as GeoJSON.

    Uses resultOffset/resultRecordCount pagination because some layers
    can exceed one request's max record count.
    """
    query_url = f"{NWS_MAPSERVER_BASE}/{layer_id}/query"

    all_features = []
    offset = 0
    page_size = 2000

    while True:
        params = {
            "f": "geojson",
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": 4326,
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }

        response = requests.get(query_url, params=params, timeout=120)
        response.raise_for_status()
        geojson = response.json()

        features = geojson.get("features", [])

        if not features:
            break

        all_features.extend(features)

        if len(features) < page_size:
            break

        offset += page_size

    if not all_features:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")

    return gdf


def clean_zone_gdf(gdf: gpd.GeoDataFrame, zone_type: str) -> gpd.GeoDataFrame:
    """
    Standardize NWS zone field names.

    Public zones:
        state_zone = AK701, AK022, etc.
        cwa        = AJK/AFC/AFG
        name       = zone name

    Marine/offshore zones:
        id         = PKZxxx
        wfo        = AJK/AFC/AFG
        name       = zone name
    """
    if gdf.empty:
        return gdf

    gdf = gdf.rename(columns={c: c.lower() for c in gdf.columns})

    rename_map = {}

    if zone_type == "public_zone":
        if "state_zone" in gdf.columns:
            rename_map["state_zone"] = "public_zone_id"
        elif "id" in gdf.columns:
            rename_map["id"] = "public_zone_id"

        if "name" in gdf.columns:
            rename_map["name"] = "public_zone_name"

        if "cwa" in gdf.columns:
            rename_map["cwa"] = "public_zone_wfo"

        if "url" in gdf.columns:
            rename_map["url"] = "public_zone_url"

        if "zoneurl" in gdf.columns:
            rename_map["zoneurl"] = "public_zone_zoneurl"

        if "zone" in gdf.columns:
            rename_map["zone"] = "public_zone_number"

        if "shortname" in gdf.columns:
            rename_map["shortname"] = "public_zone_shortname"

    else:
        if "id" in gdf.columns:
            rename_map["id"] = f"{zone_type}_id"

        if "name" in gdf.columns:
            rename_map["name"] = f"{zone_type}_name"

        if "wfo" in gdf.columns:
            rename_map["wfo"] = f"{zone_type}_wfo"

        if "url" in gdf.columns:
            rename_map["url"] = f"{zone_type}_url"

        if "zoneurl" in gdf.columns:
            rename_map["zoneurl"] = f"{zone_type}_zoneurl"

    gdf = gdf.rename(columns=rename_map)

    keep_cols = ["geometry"] + [
        c for c in gdf.columns
        if c.startswith(f"{zone_type}_")
    ]

    return gdf[keep_cols].copy()


def fetch_ak_zones() -> Dict[str, gpd.GeoDataFrame]:
    """
    Fetch public, coastal marine, and offshore zone polygons.

    Important:
      - Public zones use fields like state, cwa, zone, state_zone.
      - Marine/offshore zones use fields like id, wfo, name.
    """
    zones = {}

    layer_where = {
        # Public weather zones layer 8 has no "wfo" field.
        # It uses "state" and "cwa".
        "public_zone": "state = 'AK'",

        # Marine layers have "wfo".
        "coastal_marine_zone": "wfo IN ('AJK', 'AFC', 'AFG')",
        "offshore_zone": "wfo IN ('AJK', 'AFC', 'AFG')",
    }

    for zone_type, layer_id in ZONE_LAYERS.items():
        where = layer_where.get(zone_type, "1=1")

        print(f"Fetching {zone_type} layer {layer_id}...")
        print(f"  where: {where}")

        try:
            gdf = fetch_arcgis_layer_geojson(
                layer_id=layer_id,
                where=where,
                out_fields="*",
            )
        except Exception as e:
            print(f"  Filtered query failed for {zone_type}: {e}")
            print("  Falling back to full layer query.")
            gdf = fetch_arcgis_layer_geojson(
                layer_id=layer_id,
                where="1=1",
                out_fields="*",
            )

            # Local fallback filtering
            gdf = gdf.rename(columns={c: c.lower() for c in gdf.columns})

            if zone_type == "public_zone" and "state" in gdf.columns:
                gdf = gdf[gdf["state"] == "AK"].copy()

            elif zone_type in ["coastal_marine_zone", "offshore_zone"] and "wfo" in gdf.columns:
                gdf = gdf[gdf["wfo"].isin(AK_WFOS)].copy()

        gdf = clean_zone_gdf(gdf, zone_type)

        if not gdf.empty:
            gdf = gdf.to_crs("EPSG:4326")

        print(f"  Retrieved {len(gdf):,} {zone_type} polygons.")
        zones[zone_type] = gdf

    return zones

def spatial_join_zone(
    stations: gpd.GeoDataFrame,
    zones: gpd.GeoDataFrame,
    zone_type: str,
) -> gpd.GeoDataFrame:
    """
    Spatially join station points to a zone polygon layer.

    Uses predicate='within'. If a station lies exactly on a boundary,
    within may miss it. A nearest-zone fallback is provided separately.
    """
    if zones.empty:
        return stations

    joined = gpd.sjoin(
        stations,
        zones,
        how="left",
        predicate="within",
    ).drop(columns=["index_right"], errors="ignore")

    # If overlapping polygons somehow duplicate station rows, keep first.
    joined = joined.drop_duplicates(subset=["station_id"]).copy()

    return joined


def nearest_zone_fallback(
    stations: gpd.GeoDataFrame,
    zones: gpd.GeoDataFrame,
    zone_type: str,
    max_distance_km: float = 5.0,
) -> gpd.GeoDataFrame:
    """
    Fill missing zone IDs with nearest polygon within max_distance_km.

    This helps with points exactly on polygon boundaries or slightly offshore.
    """
    if zones.empty:
        return stations

    zone_id_col = f"{zone_type}_id"

    if zone_id_col not in stations.columns:
        return stations

    missing = stations[stations[zone_id_col].isna()].copy()

    if missing.empty:
        return stations

    # Project to Alaska Albers for distance in meters
    stations_proj = stations.to_crs("EPSG:3338")
    missing_proj = missing.to_crs("EPSG:3338")
    zones_proj = zones.to_crs("EPSG:3338")

    nearest = gpd.sjoin_nearest(
        missing_proj,
        zones_proj,
        how="left",
        max_distance=max_distance_km * 1000,
        distance_col=f"{zone_type}_nearest_distance_m",
    ).drop(columns=["index_right"], errors="ignore")

    # Bring nearest attributes back to original rows
    nearest = nearest.to_crs("EPSG:4326")

    fill_cols = [
        c for c in nearest.columns
        if c.startswith(f"{zone_type}_")
    ]

    stations_out = stations.copy()

    for _, row in nearest.iterrows():
        station_id = row["station_id"]
        idx = stations_out["station_id"] == station_id

        for col in fill_cols:
            if col in stations_out.columns and pd.isna(stations_out.loc[idx, col]).all():
                stations_out.loc[idx, col] = row[col]

    return stations_out


def assign_zones_to_stations(
    stations: gpd.GeoDataFrame,
    zones: Dict[str, gpd.GeoDataFrame],
) -> gpd.GeoDataFrame:
    """
    Join public, coastal marine, and offshore zone attributes to stations.
    """
    out = stations.copy()

    for zone_type, zone_gdf in zones.items():
        print(f"Spatially joining stations to {zone_type}...")

        out = spatial_join_zone(out, zone_gdf, zone_type)

        # Fallback for boundary/slightly-misaligned points.
        out = nearest_zone_fallback(out, zone_gdf, zone_type, max_distance_km=5.0)

    return out

def fill_public_zone_from_synoptic(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Use Synoptic's NWSZONE field as a fallback for public_zone_id.
    This does not provide the public zone name by itself, but it helps retain
    the zone ID if spatial joining misses a site.
    """
    out = gdf.copy()

    if "public_zone_id" not in out.columns:
        out["public_zone_id"] = pd.NA

    if "nws_zone_synoptic" in out.columns:
        out["public_zone_id"] = out["public_zone_id"].fillna(out["nws_zone_synoptic"])

    return out


def add_station_group_helpers(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Add convenience columns for app filtering/grouping.
    """
    out = gdf.copy()

    # Simple land/marine classification based on joined zones
    out["has_public_zone"] = out.get("public_zone_id").notna() if "public_zone_id" in out.columns else False
    out["has_coastal_marine_zone"] = out.get("coastal_marine_zone_id").notna() if "coastal_marine_zone_id" in out.columns else False
    out["has_offshore_zone"] = out.get("offshore_zone_id").notna() if "offshore_zone_id" in out.columns else False

    def classify(row):
        if row.get("has_coastal_marine_zone") or row.get("has_offshore_zone"):
            return "marine"
        if row.get("has_public_zone"):
            return "land"
        return "unassigned"

    out["station_context"] = out.apply(classify, axis=1)

    # Prefer spatially joined WFO, fall back to Synoptic CWA
    if "public_zone_wfo" in out.columns:
        out["wfo_best"] = out["public_zone_wfo"].fillna(out.get("cwa_synoptic"))
    else:
        out["wfo_best"] = out.get("cwa_synoptic")

    return out


def save_outputs(gdf: gpd.GeoDataFrame):
    """
    Save metadata outputs.
    """
    # CSV cannot preserve geometry well, so save lon/lat plus zone columns.
    df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))

    df.to_csv(CSV_OUT, index=False)
    df.to_parquet(PARQUET_OUT, index=False)

    # GeoPackage is useful if you want to inspect in ArcGIS/QGIS.
    gdf.to_file(GPKG_OUT, layer="ak_station_metadata", driver="GPKG")

    print()
    print("Outputs written:")
    print(f"  CSV:     {CSV_OUT}")
    print(f"  Parquet: {PARQUET_OUT}")
    print(f"  GPKG:    {GPKG_OUT}")


def main():
    token = get_synoptic_token()

    print("Fetching Synoptic AK station metadata...")
    station_df = fetch_synoptic_ak_stations(token)
    print(f"Retrieved {len(station_df):,} AK stations from Synoptic.")

    stations = stations_to_gdf(station_df)

    print()
    print("Fetching NWS zone polygons...")
    zones = fetch_ak_zones()

    print()
    print("Assigning zones to stations...")
    stations_with_zones = assign_zones_to_stations(stations, zones)
    stations_with_zones = fill_public_zone_from_synoptic(stations_with_zones)
    stations_with_zones = add_station_group_helpers(stations_with_zones)

    print()
    print("Station context counts:")
    print(stations_with_zones["station_context"].value_counts(dropna=False))

    save_outputs(stations_with_zones)


if __name__ == "__main__":
    main()