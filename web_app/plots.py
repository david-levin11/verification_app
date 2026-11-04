import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.patches as patches
from probability import probability_cases, reliability_table
from config import get_percentile_columns, get_element_config, is_probabilistic
from pairing import get_model_value_column, get_obs_value_column

def plot_storm_timeseries(
    model_df, obs_df, target_station, target_init_time, plot_start, plot_end,
    model, savepath=None, element='wind', percentile=None, intervals=None,
):
    """Plot the selected element/percentile from one model run and actual reports."""
    from datetime import date, datetime
    cfg = get_element_config(element)
    probabilistic = is_probabilistic(model, element)
    percentile = str(percentile or '50') if probabilistic else None
    model_col = get_model_value_column(model_df, model, element, percentile)
    obs_col = get_obs_value_column(obs_df, element)
    start = pd.to_datetime(plot_start, utc=True).tz_convert(None)
    finish = pd.to_datetime(plot_end, utc=True).tz_convert(None)
    if isinstance(plot_end, date) and not isinstance(plot_end, datetime):
        finish += pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    if start > finish:
        raise ValueError('Plot start date must not be after end date')
    init = pd.to_datetime(target_init_time, utc=True).tz_convert(None)
    data = model_df.copy()
    observations = obs_df.copy()
    for frame in [data, observations]:
        frame['valid_time'] = pd.to_datetime(frame.valid_time, utc=True).dt.tz_convert(None)
    data['init_time'] = pd.to_datetime(data.init_time, utc=True).dt.tz_convert(None)
    data = data.loc[data.station_id.astype(str).str.strip().eq(target_station) &
        data.init_time.eq(init) & data.valid_time.between(start, finish)].copy()
    data[model_col] = pd.to_numeric(data[model_col], errors='coerce')
    data = data.loc[np.isfinite(data[model_col])].sort_values('valid_time')
    if data.empty:
        return None
    station_col = 'station_id' if 'station_id' in observations else 'stid'
    observations = observations.loc[observations[station_col].astype(str).str.strip().eq(target_station) &
        observations.valid_time.between(start, finish)].sort_values('valid_time').copy()
    observations[obs_col] = pd.to_numeric(observations[obs_col], errors='coerce')
    observations[obs_col] = observations[obs_col].where(np.isfinite(observations[obs_col]))
    fig, ax = plt.subplots(figsize=(12, 6))
    if probabilistic:
        columns = get_percentile_columns(element)
        from probability import quantile_probability
        available = [(col,float(level)/100) for level,col in columns.items() if col in data]
        values = data[[col for col,_ in available]].apply(pd.to_numeric,errors='coerce')
        valid_distribution = pd.Series([np.isfinite(quantile_probability(row,
            [level for _,level in available],0)) for row in values.to_numpy()],index=data.index)
        bands = intervals or [('10','90'),('25','75')]
        for lo, hi in bands:
            color,alpha = ('#003399',.35) if lo=='25' else ('#99CCFF',.4) if lo=='10' else ('#BBBBBB',.25)
            if columns[lo] in data and columns[hi] in data:
                ax.fill_between(data.valid_time, pd.to_numeric(data[columns[lo]], errors='coerce').where(valid_distribution),
                    pd.to_numeric(data[columns[hi]], errors='coerce').where(valid_distribution), color=color, alpha=alpha,
                    label=f'{lo}th–{hi}th percentiles')
        ax.plot(data.valid_time, data[model_col], color='#000066', linewidth=2,
                linestyle='--', label=f'{model.upper()} p{percentile}')
    else:
        ax.plot(data.valid_time, data[model_col], color='#000066', linewidth=2,
                label=f'{model.upper()} Forecast')
    if observations[obs_col].notna().any():
        # Leave NaNs in the line to show gaps; explicit zero reports remain valid.
        ax.plot(observations.valid_time, observations[obs_col], color='#CC0000', linewidth=2.5,
                marker='o', markersize=4, label='Observed')
    ax.set_ylabel(f"{cfg['label']} ({cfg['units']})")
    ax.set_xlabel('Valid Time (UTC)')
    ax.set_title(f"{model.upper()} {cfg['label']} Forecast Init: {target_init_time} at {target_station.upper()}\nValid: {plot_start} to {plot_end}")
    ax.legend(loc='upper left'); ax.grid(True, linestyle=':', alpha=.7)
    fig.autofmt_xdate(); fig.tight_layout()
    if savepath:
        fig.savefig(savepath)
    return fig



def plot_confusion_matrix(
    merged_df,
    category_col_obs,
    category_col_model,
    model,
    obs,
    station_id,
    start_date,
    end_date,
    forecast_projection,
    category_labels=None,
    savepath=None,
    percentile=None,
    varname=None,
    criteria=None
):
    """
    Plots a confusion matrix showing forecast accuracy for any categorical scale.

    Parameters:
        merged_df (pd.DataFrame): DataFrame with observation and forecast categories
        category_col_obs (str): column name for observed categories
        category_col_model (str): column name for modeled categories
        category_labels (dict or list): optional mapping of category values to strings
        model, obs, station_id, start_date, end_date, forecast_projection: metadata
        savepath (str): optional file path to save PNG image
    """

    # Drop NaNs
    cleaned = merged_df.dropna(subset=[category_col_obs, category_col_model]).copy()

    # Convert to numeric
    cleaned[category_col_obs] = pd.to_numeric(cleaned[category_col_obs])
    cleaned[category_col_model] = pd.to_numeric(cleaned[category_col_model])

    # Convert to consistent categorical type
    full_range = sorted(set(cleaned[category_col_obs]).union(set(cleaned[category_col_model])))
    cat_type = pd.CategoricalDtype(categories=full_range, ordered=True)
    cleaned[category_col_obs] = cleaned[category_col_obs].astype(cat_type)
    cleaned[category_col_model] = cleaned[category_col_model].astype(cat_type)

    # Confusion matrix
    conf_matrix = pd.crosstab(
        cleaned[category_col_obs],
        cleaned[category_col_model],
        rownames=["Observed"],
        colnames=["Model"],
        dropna=False
    )
    conf_matrix = conf_matrix.drop(index=np.nan, errors='ignore')
    conf_matrix = conf_matrix.drop(columns=np.nan, errors='ignore')

    # Normalize to percent
    conf_matrix_pct = conf_matrix / conf_matrix.values.sum() * 100

    # Plot
    plt.figure(figsize=(10, 8))
    ax = sns.heatmap(
        conf_matrix_pct,
        annot=False,
        fmt=".1f",
        cmap="Blues",
        cbar_kws={'label': '% of All Forecast/Obs Pairs'},
        linewidths=0.5,
        linecolor='gray'
    )

    # Annotate cells
    for i, row in enumerate(conf_matrix_pct.index):
        for j, col in enumerate(conf_matrix_pct.columns):
            val = conf_matrix_pct.loc[row, col]
            if pd.isna(val) or val == 0:
                continue
            brightness = conf_matrix_pct.values[i, j] / conf_matrix_pct.values.max()
            text_color = 'white' if brightness > 0.5 else 'black'
            ax.text(j + 0.5, i + 0.5, f"{val:.1f}%", ha='center', va='center', color=text_color, fontsize=9)

    # Diagonal highlighting
    n = len(conf_matrix_pct)
    for i in range(n):
        if conf_matrix_pct.columns[i] in conf_matrix_pct.index:
            rect = patches.Rectangle((i, i), 1, 1, fill=False, edgecolor='red', linewidth=2)
            ax.add_patch(rect)

    # Optional label mapping
    if category_labels:
        if isinstance(category_labels, dict):
            conf_matrix_pct.index = [category_labels.get(i, str(i)) for i in conf_matrix_pct.index]
            conf_matrix_pct.columns = [category_labels.get(i, str(i)) for i in conf_matrix_pct.columns]
    
    # Labels and layout
    plt.title(f"{criteria} {model.upper()} {varname} Forecast Accuracy at {station_id.upper()} From {start_date} to {end_date}")
    plt.xlabel(f"{model.upper()} {forecast_projection} Forecasts")
    plt.ylabel(f"{obs.upper()}")
    plt.xticks(rotation=45)
    plt.yticks(rotation=0)
    # If labels are already strings, set directly
    ax.set_yticklabels(conf_matrix_pct.index)
    ax.set_xticklabels(conf_matrix_pct.columns)
    plt.tight_layout()
    fig = plt.gcf()
    return fig


def plot_forecast_bias_bar_chart(
    merged_df,
    category_col_obs,
    category_col_model,
    model,
    obs,
    station_id,
    start_date,
    end_date,
    forecast_projection,
    category_labels=None,
    savepath=None,
    percentile=None,
    varname=None
):
    """
    Creates a stacked bar plot showing forecast bias across observed categories,
    now including the total count (n) of valid pairs for each bin.
    """
    
    # Compute deviation and bias type
    merged = merged_df.copy()
    merged["deviation"] = merged[category_col_model] - merged[category_col_obs]

    def categorize_deviation(dev):
        if pd.isna(dev):
            return None
        if dev == 0:
            return "Correct"
        elif dev == -1:
            return "Under by 1"
        elif dev <= -2:
            return "Under by 2+"
        elif dev == 1:
            return "Over by 1"
        elif dev >= 2:
            return "Over by 2+"

    merged["bias_category"] = merged["deviation"].apply(categorize_deviation)

    # Bias summary by observed category (Percentages)
    summary = (
        merged.groupby(category_col_obs, observed=False)["bias_category"]
        .value_counts(normalize=True)
        .unstack(fill_value=0)
        .sort_index()
        * 100
    )

    # Calculate the raw counts of valid pairs per category
    counts = merged.groupby(category_col_obs, observed=False)["bias_category"].count().sort_index()

    # Ensure expected order of columns
    expected_bins = ["Correct", "Under by 1", "Under by 2+", "Over by 1", "Over by 2+"]
    for col in expected_bins:
        if col not in summary.columns:
            summary[col] = 0
    summary = summary[expected_bins]

    # Apply label mapping to BOTH the summary and the counts
    if category_labels:
        if isinstance(category_labels, dict):
            new_labels = [category_labels.get(i, str(i)) for i in summary.index]
        elif isinstance(category_labels, list):
            def safe_label(i):
                try:
                    return category_labels[int(i)] if int(i) < len(category_labels) else str(i)
                except:
                    return str(i)
            new_labels = [safe_label(i) for i in summary.index]
        else:
            new_labels = summary.index

        summary.index = new_labels
        counts.index = new_labels

    # Colors
    color_map = {
        "Correct": "#4CAF50",
        "Under by 1": "#FF9999",
        "Under by 2+": "#CC0000",
        "Over by 1": "#99CCFF",
        "Over by 2+": "#003399",
    }
    colors = [color_map[b] for b in expected_bins]
    plt.figure(figsize=(10, 8))
    # Plot (assigning to 'ax' so we can add text)
    ax = summary.plot(
        kind='bar',
        stacked=True,
        color=colors,
        figsize=(12, 6),
        edgecolor='black'
    )

    # Add count text above each bar
    for i, category in enumerate(summary.index):
        count = counts.iloc[i]
        if count > 0:  # Only label bars that actually have data
            # Place text slightly above the 100% mark (y=102)
            ax.text(i, 102, f'n={int(count)}', ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='#333333', rotation=0)

    # Extend the y-axis limit to make room for the text annotations
    ax.set_ylim(0, 115)

    plt.ylabel("Percentage of Forecasts")
    plt.xlabel("Observed Category")
    plt.title(f"{model.upper()} {varname} Forecast Deviation Relative to Observed Category at {station_id.upper()}\nFrom {start_date} to {end_date}")
    plt.legend(title="Forecast Bias", loc="upper left", bbox_to_anchor=(1.0, 1.0))
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    fig = plt.gcf()
    return fig

def _get_percentile_columns_for_element(element):
    """Use the same element/percentile definitions as pairing and scores."""
    columns = get_percentile_columns(element.lower())
    return list(columns.values()), [int(level) for level in columns]


def _get_available_percentile_columns(merged_df, element):
    """
    Return available percentile columns and their percentile levels.

    Raises a helpful error if required columns are missing.
    """

    pct_cols, pct_levels = _get_percentile_columns_for_element(element)

    missing_cols = [c for c in pct_cols if c not in merged_df.columns]

    if missing_cols:
        available_prob_cols = [
            c for c in merged_df.columns
            if c.endswith(("_p5", "_p10", "_p25", "_p50", "_p75", "_p90", "_p95"))
            or "_p" in c
        ]

        raise ValueError(
            f"Missing percentile columns for {element}: {missing_cols}. "
            f"Available probabilistic-looking columns: {available_prob_cols}"
        )

    return pct_cols, pct_levels


def plot_threshold_reliability(
    merged_df,
    threshold,
    model,
    obs,
    station_id,
    start_date,
    end_date,
    element,
    obs_col="obs_value",
    savepath=None,
    threshold_operator=">=",
):
    """
    Reliability plot for probability of exceeding a threshold.

    Uses element-specific percentile columns, such as:
        precip24hr -> qpf_p5 ... qpf_p95
        maxt       -> maxt_p5 ... maxt_p95
        Wind       -> wind_p5 ... wind_p95
    """

    if obs_col not in merged_df.columns:
        raise ValueError(
            f"Observation column '{obs_col}' not found. "
            f"Available columns: {merged_df.columns.tolist()}"
        )

    cases = probability_cases(merged_df, element, threshold, threshold_operator, obs_col)
    if cases.empty:
        raise ValueError("No valid forecast probabilities could be computed.")
    reliability_data = reliability_table(cases)

    if reliability_data.empty:
        raise ValueError("No non-empty probability bins available for reliability plot.")

    fig, ax1 = plt.subplots(figsize=(9, 8))

    ax1.plot(
        reliability_data["mean_forecast"],
        reliability_data["observed_freq"],
        marker="o",
        linewidth=2,
        markersize=8,
        label="Model reliability",
    )

    ax1.plot(
        [0, 1],
        [0, 1],
        linestyle="--",
        linewidth=1.5,
        label="Perfect reliability",
    )

    ax1.set_xlim([0, 1])
    ax1.set_ylim([0, 1])
    ax1.set_xlabel("Forecast probability")
    ax1.set_ylabel("Observed relative frequency")
    ax1.set_title(
        f"{model.upper()} Reliability: {element} {threshold_operator} {threshold}\n"
        f"{station_id} from {start_date} to {end_date}"
    )
    ax1.grid(True, linestyle=":", alpha=0.7)

    ax2 = ax1.twinx()
    bin_centers = [interval.mid for interval in reliability_data["prob_bin"]]

    ax2.bar(
        bin_centers,
        reliability_data["count"],
        width=0.08,
        alpha=0.2,
        label="Forecast count",
    )

    ax2.set_ylabel("Number of forecasts")

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()

    ax1.legend(
        lines_1 + lines_2,
        labels_1 + labels_2,
        loc="upper left",
        framealpha=0.9,
    )

    plt.tight_layout()

    return fig


def plot_quantile_rank_histogram(
    merged_df,
    model,
    station_id,
    start_date,
    end_date,
    element,
    obs_col="obs_value",
    savepath=None,
):
    """
    Quantile rank histogram for element-specific percentile columns.
    """

    if obs_col not in merged_df.columns:
        raise ValueError(
            f"Observation column '{obs_col}' not found. "
            f"Available columns: {merged_df.columns.tolist()}"
        )

    pct_cols, pct_levels = _get_available_percentile_columns(merged_df, element)

    cleaned = merged_df.dropna(subset=[obs_col] + pct_cols).copy()

    if cleaned.empty:
        raise ValueError(
            f"No valid rows available for rank histogram after dropping missing "
            f"{obs_col} and percentile columns."
        )

    # Sort percentile columns by percentile level just to be safe.
    pct_pairs = sorted(zip(pct_levels, pct_cols), key=lambda x: x[0])
    pct_levels = [p for p, c in pct_pairs]
    pct_cols = [c for p, c in pct_pairs]

    counts = []

    first_col = pct_cols[0]
    last_col = pct_cols[-1]

    counts.append((cleaned[obs_col] < cleaned[first_col]).sum())

    for lower_col, upper_col in zip(pct_cols[:-1], pct_cols[1:]):
        counts.append(
            (
                (cleaned[obs_col] >= cleaned[lower_col])
                & (cleaned[obs_col] < cleaned[upper_col])
            ).sum()
        )

    counts.append((cleaned[obs_col] >= cleaned[last_col]).sum())

    total = len(cleaned)

    if total == 0:
        raise ValueError("No valid observations available for rank histogram.")

    obs_pcts = [c / total * 100.0 for c in counts]

    # Expected bin widths:
    # <p5, p5-p10, p10-p25, p25-p50, p50-p75, p75-p90, p90-p95, >p95
    expected_widths = [pct_levels[0]]

    for lower, upper in zip(pct_levels[:-1], pct_levels[1:]):
        expected_widths.append(upper - lower)

    expected_widths.append(100 - pct_levels[-1])

    labels = [f"< p{pct_levels[0]}"]

    for lower, upper in zip(pct_levels[:-1], pct_levels[1:]):
        labels.append(f"p{lower}-p{upper}")

    labels.append(f">= p{pct_levels[-1]}")

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(
        x - width / 2,
        obs_pcts,
        width,
        label="Observed frequency",
        edgecolor="black",
    )

    ax.bar(
        x + width / 2,
        expected_widths,
        width,
        label="Expected frequency",
        alpha=0.7,
        edgecolor="black",
    )

    ax.set_ylabel("Percentage of observations")
    ax.set_xlabel("Forecast percentile interval")
    ax.set_title(
        f"{model.upper()} Quantile Rank Histogram: {element}\n"
        f"{station_id} from {start_date} to {end_date}"
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.legend()
    ax.grid(axis="y", linestyle=":", alpha=0.7)

    plt.tight_layout()

    return fig
