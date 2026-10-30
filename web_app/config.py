"""
Configuration for the Alaska Point Verification Dashboard.

This config is intentionally frontend/verification focused. It borrows from the
archiver config, but does not include download/API/S3-specific settings.
"""

# =============================================================================
# Models and elements
# =============================================================================

MODELS = [
    "nbm",
    "nbm_exp",
    "nbmqmd",
    "nbmqmd_exp",
    "hrrr",
    "ndfd",
    "urma",
    "rrfs",
    "refs",
]

OBS_SOURCES = [
    "obs",
    "urma",
]

ELEMENTS = [
    "wind",
    "gust",
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


# =============================================================================
# Available model/element combinations
# =============================================================================
# Based on archiver_config AVAILABLE_FIELDS, but normalized to lowercase names.

AVAILABLE_ELEMENTS_BY_MODEL = {
    "rrfs": ["wind", "gust", "rh", "precip6hr"],
    "refs": ["wind", "gust", "rh", "precip6hr"],
    "nbm": [
        "wind",
        "gust",
        "precip6hr",
        "precip24hr",
        "snow6hr",
        "snow24hr",
        "snow48hr",
        "snow72hr",
        "mint",
        "maxt",
        "rh",
    ],
    "nbm_exp": [
        "wind",
        "gust",
        "snow6hr",
        "snow24hr",
        "snow48hr",
        "snow72hr",
    ],
    "nbmqmd": [
        "wind",
        "gust",
        "precip24hr",
        "precip6hr",
        "maxt",
        "mint",
        "rh",
    ],
    "nbmqmd_exp": [
        "wind",
        "gust",
        "precip24hr",
        "precip6hr",
        "maxt",
        "mint",
    ],
    "hrrr": [
        "wind",
        "gust",
        "precip6hr",
        "snow6hr",
        "rh",
    ],
    "ndfd": [
        "wind",
        "gust",
        "precip6hr",
        "snow6hr",
        "maxt",
        "mint",
        "rh",
    ],
    "urma": [
        "wind",
        "gust",
    ],
}


# =============================================================================
# Probabilistic capability
# =============================================================================
# NBM temperature/precipitation interval archives contain scalar forecasts.
# NBMQMD and NBMQMD_EXP retain their separately archived quantile distributions.

PROBABILISTIC_ELEMENTS_BY_MODEL = {
    "rrfs": [],
    "refs": ["wind", "gust", "rh", "precip6hr"],
    "nbm": [
        "snow6hr",
        "snow24hr",
        "snow48hr",
        "snow72hr",
        "rh",
    ],
    "nbm_exp": [
        "snow6hr",
        "snow24hr",
        "snow48hr",
        "snow72hr",
    ],
    "nbmqmd": [
        "precip6hr",
        "precip24hr",
        "wind",
        "gust",
        "maxt",
        "mint",
        "rh",
    ],
    "nbmqmd_exp": [
        "precip6hr",
        "precip24hr",
        "wind",
        "gust",
        "maxt",
        "mint",
    ],
    "hrrr": [],
    "ndfd": [],
    "urma": [],
}

PERCENTILES = ["5", "10", "25", "50", "75", "90", "95"]


def is_probabilistic(model: str, element: str) -> bool:
    """
    Return True if the selected model/element supports percentile verification.
    """
    return element in PROBABILISTIC_ELEMENTS_BY_MODEL.get(model, [])


def get_available_elements(model: str) -> list[str]:
    """
    Return elements available for a selected model.
    """
    return AVAILABLE_ELEMENTS_BY_MODEL.get(model, [])


# =============================================================================
# Forecast projection groups
# =============================================================================
# Day labels are lead intervals, independent of model cadence or missing steps.

FORECAST_PROJECTION_GROUPS = {
    "All": None,
    "Day 1": range(0, 25),
    "Day 2": range(25, 49),
    "Day 3": range(49, 73),
    "Day 4": range(73, 97),
    "Day 5": range(97, 121),
    "Day 6": range(121, 145),
    "Day 7": range(145, 169),
}


def get_projection_lead_bounds(start_projection, end_projection):
    """Continuous lead range: Day 1=[0,24], Day 2=(24,48], etc."""
    names=[name for name in FORECAST_PROJECTION_GROUPS if name != 'All']
    if start_projection not in names or end_projection not in names:
        raise ValueError('Unknown forecast projection day')
    first,last=sorted([names.index(start_projection),names.index(end_projection)])
    return first*24, (last+1)*24


def get_forecast_hours(model: str, element: str, projection: str = "All") -> list[int]:
    """Compatibility helper for integer day bounds, not model availability.

    All returns the seven-day display range. Actual all-hours loading uses no
    lead filter and determines its archive lookback from file metadata.
    """
    if projection == 'All':return list(range(169))
    if projection not in FORECAST_PROJECTION_GROUPS:
        raise ValueError(f'Unknown forecast projection: {projection}')
    return list(FORECAST_PROJECTION_GROUPS[projection])


def get_forecast_hours_for_projection_range(model, element, start_projection, end_projection):
    low,high=get_projection_lead_bounds(start_projection,end_projection)
    return list(range(low if low==0 else low+1,high+1))

# =============================================================================
# Element display and standardized value columns
# =============================================================================

ELEMENT_CONFIG = {
    "wind": {
        "label": "Wind Speed",
        "units": "kt",
        "available_obs_sources": ["obs", "urma"],
        "obs_time_column": "valid_time",
        "model_value_candidates": ["wind_speed_kt", "si10"],
        "forecast_direction_candidates": ["wind_dir_deg", "wind_direction"],
        "obs_value_candidates": ["obs_wind_speed_kts", "wind_speed_kt"],
        "direction_candidates": ["obs_wind_dir_deg", "wind_dir_deg", "wind_direction"],
        "percentile_prefix": "wind_p",
        "default_percentile": "75",
        "default_threshold": 25,
        "thresholds": [15, 20, 25, 30, 34, 40, 48, 50, 64],
        "supports_direction_filter": True,
        "category_sets": ["marine", "beaufort"],
    },

    "gust": {
        "label": "Wind Gust",
        "units": "kt",
        "available_obs_sources": ["obs", "urma"],
        "obs_time_column": "valid_time",
        "model_value_candidates": ["wind_gust_kt", "i10fg"],
        "obs_value_candidates": ["obs_wind_gust_kts", "wind_gust_kt"],
        "direction_candidates": ["obs_wind_dir_deg", "wind_dir_deg", "wind_direction"],
        "percentile_prefix": "gust_p",
        "default_percentile": "75",
        "default_threshold": 34,
        "thresholds": [25, 30, 34, 40, 48, 50, 58, 64],
        "supports_direction_filter": True,
        "category_sets": ["marine"],
    },

    "precip6hr": {
        "accum_hours": 6,
        "label": "6-hour Precipitation",
        "units": "in",
        "available_obs_sources": ["obs"],
        "obs_time_column": "end_time",
        "model_value_candidates": ["verification_precip_6h", "precip_6h", "precip_accum_6hr", "precip6hr", "precip_accum"],
        "obs_value_candidates": [
            "precip_total",
            "precip_6h",
            "obs_precip_6h",
            "precip_accum_6hr",
            "precip_accum",
        ],
        "percentile_prefix": "qpf_p",
        "default_percentile": "75",
        "default_threshold": 0.25,
        "thresholds": [0.01, 0.10, 0.25, 0.50, 1.00, 2.00],
        "supports_direction_filter": False,
        "category_sets": ["precip"],
    },

    "precip24hr": {
        "accum_hours": 24,
        "label": "24-hour Precipitation",
        "units": "in",
        "available_obs_sources": ["obs"],
        "obs_time_column": "end_time",
        "model_value_candidates": ["precip_accum_24hr", "precip24hr"],
        "obs_value_candidates": [
            "precip_total",
            "precip_24h",
            "obs_precip_24h",
            "precip_accum_24hr",
            "precip_accum",
        ],
        "percentile_prefix": "qpf_p",
        "default_percentile": "75",
        "default_threshold": 1.00,
        "thresholds": [0.01, 0.25, 0.50, 1.00, 2.00, 3.00],
        "supports_direction_filter": False,
        "category_sets": ["precip"],
    },

    "snow6hr": {
        "accum_hours": 6,
        "label": "6-hour Snowfall",
        "units": "in",
        "available_obs_sources": ["obs"],
        "obs_time_column": "end_time",
        "model_value_candidates": ["snow_accum_6hr", "snow_accum", "snow6hr"],
        "obs_value_candidates": ["snow_6h", "obs_snow_6h", "snow_accum_6hr", "snow_accum"],
        "percentile_prefix": "snow_p",
        "default_percentile": "75",
        "default_threshold": 1.0,
        "thresholds": [0.1, 1.0, 2.0, 4.0, 6.0],
        "supports_direction_filter": False,
        "category_sets": ["snow"],
    },

    "snow24hr": {
        "accum_hours": 24,
        "label": "24-hour Snowfall",
        "units": "in",
        "available_obs_sources": ["obs"],
        "obs_time_column": "end_time",
        "model_value_candidates": ["snow_accum_24hr", "snow24hr"],
        "obs_value_candidates": ["snow_24h", "obs_snow_24h", "snow_accum_24hr", "snow_accum"],
        "percentile_prefix": "snow_p",
        "default_percentile": "75",
        "default_threshold": 4.0,
        "thresholds": [0.1, 1.0, 2.0, 4.0, 6.0, 12.0],
        "supports_direction_filter": False,
        "category_sets": ["snow"],
    },

    "snow48hr": {
        "accum_hours": 48,
        "label": "48-hour Snowfall",
        "units": "in",
        "available_obs_sources": ["obs"],
        "obs_time_column": "end_time",
        "model_value_candidates": ["snow_accum_48hr", "snow48hr"],
        "obs_value_candidates": ["snow_48h", "obs_snow_48h", "snow_accum_48hr", "snow_accum"],
        "percentile_prefix": "snow_p",
        "default_percentile": "75",
        "default_threshold": 6.0,
        "thresholds": [0.1, 2.0, 4.0, 6.0, 12.0, 18.0],
        "supports_direction_filter": False,
        "category_sets": ["snow"],
    },

    "snow72hr": {
        "accum_hours": 72,
        "label": "72-hour Snowfall",
        "units": "in",
        "available_obs_sources": ["obs"],
        "obs_time_column": "end_time",
        "model_value_candidates": ["snow_accum_72hr", "snow72hr"],
        "obs_value_candidates": ["snow_72h", "obs_snow_72h", "snow_accum_72hr", "snow_accum"],
        "percentile_prefix": "snow_p",
        "default_percentile": "75",
        "default_threshold": 8.0,
        "thresholds": [0.1, 2.0, 4.0, 6.0, 12.0, 18.0, 24.0],
        "supports_direction_filter": False,
        "category_sets": ["snow"],
    },

    "rh": {
        "label": "Relative Humidity",
        "units": "%",
        "available_obs_sources": ["obs"],
        "obs_time_column": "valid_time",
        "model_value_candidates": ["rh"],
        "obs_value_candidates": ["rh", "relative_humidity"],
        "percentile_prefix": "rh_p",
        "default_percentile": "50",
        "default_threshold": 30,
        "threshold_operator": "<=",
        "thresholds": [15, 20, 25, 30, 40, 50, 70, 80, 90],
        "supports_direction_filter": False,
        "category_sets": ["rh"],
    },

    "maxt": {
        "label": "Maximum Temperature",
        "units": "F",
        "available_obs_sources": ["obs"],
        "obs_time_column": "window_end",
        "obs_filter_time_column": "date",
        "pairing_method": "date",
        "model_pair_date_column": "valid_time",
        "obs_pair_date_column": "date",
        "model_value_candidates": ["max_temp", "maxt", "temperature", "tmax"],
        "obs_value_candidates": [
            "tmax",
            "max_t",
            "obs_max_temp",
            "max_temp",
            "maxt",
        ],
        "percentile_prefix": "maxt_p",
        "default_percentile": "50",
        "default_threshold": 32,
        "thresholds": [-20, 0, 10, 20, 32, 40, 50, 60, 70, 80],
        "supports_direction_filter": False,
        "category_sets": ["temperature"],
    },

    "mint": {
        "label": "Minimum Temperature",
        "threshold_operator": "<=",
        "units": "F",
        "available_obs_sources": ["obs"],
        "obs_time_column": "window_end",
        "obs_filter_time_column": "date",
        "pairing_method": "date",
        "model_pair_date_column": "valid_time",
        "obs_pair_date_column": "date",
        "model_value_candidates": ["min_temp", "mint", "temperature", "tmin"],
        "obs_value_candidates": [
            "tmin",
            "min_t",
            "obs_min_temp",
            "min_temp",
            "mint",
        ],
        "percentile_prefix": "mint_p",
        "default_percentile": "50",
        "default_threshold": 32,
        "thresholds": [-40, -20, 0, 10, 20, 32, 40, 50],
        "supports_direction_filter": False,
        "category_sets": ["temperature"],
    },
}

def get_available_obs_sources(element: str) -> list[str]:
    return ELEMENT_CONFIG[element].get("available_obs_sources", ["obs"])

def get_pairing_method(element: str) -> str:
    return ELEMENT_CONFIG[element].get("pairing_method", "time")


def get_model_pair_date_column(element: str) -> str:
    return ELEMENT_CONFIG[element].get("model_pair_date_column", "valid_time")


def get_obs_pair_date_column(element: str) -> str:
    return ELEMENT_CONFIG[element].get("obs_pair_date_column", "valid_time")

def get_obs_time_column(element: str) -> str:
    """
    Return the observation archive time column used for filtering.

    The selected column is standardized to valid_time in data_loader.py.
    """
    return ELEMENT_CONFIG[element].get("obs_time_column", "valid_time")

def get_obs_filter_time_column(element: str) -> str:
    """
    Return the observation archive time column used in the DuckDB WHERE clause.

    Defaults to obs_time_column. This allows daily extrema to filter by date
    while still using window_end as the standardized valid_time.
    """
    cfg = ELEMENT_CONFIG[element]
    return cfg.get("obs_filter_time_column", cfg.get("obs_time_column", "valid_time"))

def get_element_config(element: str) -> dict:
    """
    Return config for selected weather element.
    """
    return ELEMENT_CONFIG[element]


# =============================================================================
# Percentile column names
# =============================================================================

def get_percentile_columns(element: str) -> dict[str, str]:
    """
    Return expected percentile column names for an element.

    This assumes the archive uses columns like:
        wind_p5, wind_p10, ..., wind_p95
        precip_p5, precip_p10, ...
        snow_p5, snow_p10, ...
    """
    prefix = ELEMENT_CONFIG[element]["percentile_prefix"]

    return {
        p: f"{prefix}{p}"
        for p in PERCENTILES
    }


# =============================================================================
# Category definitions
# =============================================================================

CATEGORY_CONFIG = {
    "marine": {
        "label": "Marine Category",
        "bins": [-0.1, 25, 33, 48, 63, float("inf")],
        "labels": {
            0: "None",
            1: "SCA",
            2: "Gale",
            3: "Storm",
            4: "Hurricane Force",
        },
    },
    "beaufort": {
        "label": "Beaufort Category",
        "bins": [-0.1, 1, 3, 6, 10, 16, 21, 27, 33, 40, 47, 55, 63, float("inf")],
        "labels": {
            0: "Calm",
            1: "Light Air",
            2: "Light Breeze",
            3: "Gentle Breeze",
            4: "Moderate Breeze",
            5: "Fresh Breeze",
            6: "Strong Breeze",
            7: "Near Gale",
            8: "Gale",
            9: "Strong Gale",
            10: "Storm",
            11: "Violent Storm",
            12: "Hurricane",
        },
    },
    "precip": {
        "label": "Precipitation Category",
        "bins": [-0.001, 0.01, 0.10, 0.25, 0.50, 1.00, 2.00, float("inf")],
        "labels": {
            0: "None/Trace",
            1: "Very Light",
            2: "Light",
            3: "Moderate",
            4: "Heavy",
            5: "Very Heavy",
            6: "Extreme",
        },
    },
    "snow": {
        "label": "Snowfall Category",
        "bins": [-0.001, 0.1, 1.0, 2.0, 4.0, 6.0, 12.0, float("inf")],
        "labels": {
            0: "None/Trace",
            1: "Light",
            2: "Moderate",
            3: "Advisory",
            4: "Heavy",
            5: "Major",
            6: "Extreme",
        },
    },
    "temperature": {
        "label": "Temperature Category",
        "bins": [-100, 0, 20, 32, 50, 70, 85, 100, float("inf")],
        "labels": {
            0: "Bitter Cold",
            1: "Very Cold",
            2: "Freezing",
            3: "Cool",
            4: "Mild",
            5: "Warm",
            6: "Hot",
            7: "Very Hot",
        },
    },
    "rh": {
        "label": "Relative Humidity Category",
        "bins": [-0.1, 15, 25, 35, 50, 70, 90, 100],
        "labels": {
            0: "Very Dry",
            1: "Dry",
            2: "Moderately Dry",
            3: "Moderate",
            4: "Humid",
            5: "Very Humid",
            6: "Near Saturation",
        },
    },
}


def get_available_category_sets(element: str) -> list[str]:
    """
    Return category sets available for a given element.
    """
    return ELEMENT_CONFIG[element].get("category_sets", [])


# =============================================================================
# Map metric options
# =============================================================================

DETERMINISTIC_MAP_METRICS = [
    "n",
    "bias",
    "mae",
    "rmse",
    "pod",
    "far",
    "csi",
    "event_freq_obs",
    "event_freq_fcst",
    "max_obs",
    "max_fcst",
]

PROBABILISTIC_MAP_METRICS = [
    "n",
    "bias",
    "mae",
    "rmse",
    "pod",
    "far",
    "csi",
    "event_freq_obs",
    "event_freq_fcst",
    "max_obs",
    "max_fcst",
    "n_prob",
    "brier_score",
    "reliability_error",
]


def get_map_metrics(model: str, element: str) -> list[str]:
    """
    Return valid map metrics for selected model/element.
    """
    if is_probabilistic(model, element):
        return PROBABILISTIC_MAP_METRICS

    return DETERMINISTIC_MAP_METRICS

