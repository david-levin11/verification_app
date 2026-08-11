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
    "nbm": [
        "wind",
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
    ],
}


# =============================================================================
# Probabilistic capability
# =============================================================================
# Based on archiver_config PROBABILISTIC_ELEMENTS.

PROBABILISTIC_ELEMENTS_BY_MODEL = {
    "nbm": [
        "snow6hr",
        "snow24hr",
        "snow48hr",
        "snow72hr",
        "maxt",
        "mint",
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
# Forecast hours
# =============================================================================
# Based on archiver_config HERBIE_FORECASTS, normalized to lowercase elements.

FORECAST_HOURS_BY_MODEL_ELEMENT = {
    "nbm": {
        "wind": [5, 11, 17, 23, 29, 35, 41, 47, 53, 59, 65, 71, 83, 95, 107, 119, 131, 143, 155, 167],
        "snow24hr": [29, 35, 41, 47, 53, 59, 65, 71, 83, 89, 95, 101, 107, 113, 119, 125, 131, 137, 143, 149, 155, 161],
        "snow48hr": [53, 59, 65, 71, 83, 89, 95, 101, 107, 113, 119, 125, 131, 137, 143, 149, 155, 161],
        "snow72hr": [83, 89, 95, 101, 107, 113, 119, 125, 131, 137, 143, 149, 155, 161],
        "snow6hr": [11, 17, 23, 29, 35, 41, 47, 53, 59, 65, 71, 83, 89, 95, 101, 107, 113, 119, 125, 131, 137, 143, 149, 155, 161],
        "maxt": [18, 30, 42, 54, 66, 78, 90, 102, 114, 126, 138, 150, 162, 174],
        "mint": [18, 30, 42, 54, 66, 78, 90, 102, 114, 126, 138, 150, 162, 174],
        "rh": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96, 102, 108, 114, 120],
    },
    "nbm_exp": {
        "wind": [5, 11, 17, 23, 29, 35, 41, 47, 53, 59, 65, 71, 83, 95, 107, 119, 131, 143, 155, 167],
        "snow24hr": [29, 35, 41, 47, 53, 59, 65, 71, 83, 89, 95, 101, 107, 113, 119, 125, 131, 137, 143, 149, 155, 161],
        "snow48hr": [53, 59, 65, 71, 83, 89, 95, 101, 107, 113, 119, 125, 131, 137, 143, 149, 155, 161],
        "snow72hr": [83, 89, 95, 101, 107, 113, 119, 125, 131, 137, 143, 149, 155, 161],
        "snow6hr": [11, 17, 23, 29, 35, 41, 47, 53, 59, 65, 71, 83, 89, 95, 101, 107, 113, 119, 125, 131, 137, 143, 149, 155, 161],
    },
    "nbmqmd": {
        "precip24hr": [24, 30, 36, 48, 60, 72, 84, 96, 108, 120, 132, 144, 156, 168],
        "precip6hr": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96, 102, 108, 114, 120],
        "maxt": [18, 30, 42, 54, 66, 78, 90, 102, 114, 126, 138, 150, 162, 174],
        "mint": [18, 30, 42, 54, 66, 78, 90, 102, 114, 126, 138, 150, 162, 174],
        "rh": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96, 102, 108, 114, 120],
        "wind": [12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 84, 96, 108, 120, 132, 144, 156, 168],
        "gust": [12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 84, 96, 108, 120, 132, 144, 156, 168],
    },
    "nbmqmd_exp": {
        "precip24hr": [24, 30, 36, 48, 60, 72, 84, 96, 108, 120, 132, 144, 156, 168],
        "precip6hr": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96, 102, 108, 114, 120],
        "maxt": [18, 30, 42, 54, 66, 78, 90, 102, 114, 126, 138, 150, 162, 174],
        "mint": [18, 30, 42, 54, 66, 78, 90, 102, 114, 126, 138, 150, 162, 174],
        "rh": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96, 102, 108, 114, 120],
        "wind": [12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 84, 96, 108, 120, 132, 144, 156, 168],
        "gust": [12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 84, 96, 108, 120, 132, 144, 156, 168],
    },
    "hrrr": {
        "wind": [12, 18, 24, 30, 36, 42, 48],
        "rh": [12, 18, 24, 30, 36, 42, 48],
        "precip6hr": [0, 6, 12, 18, 24, 30, 36, 42, 48],
        "snow6hr": [0, 6, 12, 18, 24, 30, 36, 42, 48],
    },
    "urma": {
        "wind": [0],
    },
    # Add NDFD forecast hours here if your archive contains them.
    "ndfd": {
        "wind": [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72, 78, 84, 90, 96, 102, 108, 114, 120, 126, 132, 138, 144, 150, 156, 162, 168],
        "gust": [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72],
        "precip6hr": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72],
        "snow6hr": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72],
        "maxt": [12, 24, 36, 48, 60, 72, 84, 96, 108, 120, 132, 144, 156, 168],
        "mint": [12, 24, 36, 48, 60, 72, 84, 96, 108, 120, 132, 144, 156],
        "rh": [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72, 78, 84, 90, 96, 102, 108, 114, 120, 126, 132, 138, 144, 150, 156, 162, 168],
    },
}


# =============================================================================
# Forecast projection groups
# =============================================================================
# These are approximate app-facing groupings. For elements with nonstandard
# valid periods, you can tune this later.

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


def get_forecast_hours(model: str, element: str, projection: str = "All") -> list[int]:
    """
    Return forecast hours for a model/element/projection combination.

    If projection == "All", return all configured forecast hours.
    """
    all_hours = FORECAST_HOURS_BY_MODEL_ELEMENT.get(model, {}).get(element, [])

    if projection == "All":
        return all_hours

    hour_range = FORECAST_PROJECTION_GROUPS.get(projection)

    if hour_range is None:
        return all_hours

    return [h for h in all_hours if h in hour_range]


# =============================================================================
# Element display and standardized value columns
# =============================================================================

ELEMENT_CONFIG = {
    "wind": {
        "label": "Wind Speed",
        "units": "kt",
        "obs_time_column": "valid_time",
        "model_value_candidates": ["wind_speed_kt", "si10"],
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
        "label": "6-hour Precipitation",
        "units": "in",
        "obs_time_column": "end_time",
        "model_value_candidates": ["precip_accum_6hr", "precip_accum", "precip6hr"],
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
        "label": "24-hour Precipitation",
        "units": "in",
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
        "label": "6-hour Snowfall",
        "units": "in",
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
        "label": "24-hour Snowfall",
        "units": "in",
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
        "label": "48-hour Snowfall",
        "units": "in",
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
        "label": "72-hour Snowfall",
        "units": "in",
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
        "obs_time_column": "valid_time",
        "model_value_candidates": ["rh"],
        "obs_value_candidates": ["rh", "relative_humidity"],
        "percentile_prefix": "rh_p",
        "default_percentile": "50",
        "default_threshold": 30,
        "thresholds": [15, 20, 25, 30, 40, 50, 70, 80, 90],
        "supports_direction_filter": False,
        "category_sets": ["rh"],
    },

    "maxt": {
        "label": "Maximum Temperature",
        "units": "F",
        "obs_time_column": "window_end",
        "model_value_candidates": ["tmax", "max_temp", "maxt", "temperature"],
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
        "units": "F",
        "obs_time_column": "window_end",
        "model_value_candidates": ["tmin", "min_temp", "mint", "temperature"],
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

def get_obs_time_column(element: str) -> str:
    """
    Return the observation archive time column used for filtering.

    The selected column is standardized to valid_time in data_loader.py.
    """
    return ELEMENT_CONFIG[element].get("obs_time_column", "valid_time")

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