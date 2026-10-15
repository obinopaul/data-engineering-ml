"""Stage 36–40 analytics workspace.

HOW TO RUN (from the main folder, using the existing environment):
    .venv/bin/python main.py
Or retain all DataFrames for interactive inspection:
    .venv/bin/python -i main.py
    load36.head()
    deep_frames[36]["upwards"].head()

WHAT TO CHANGE:
    BOTTOM_WINDOW_FT: distance above each stage's observed maximum (3,000 ft).
    ACTIVITY_THRESHOLDS: absolute departure from the zero/off baseline, in V/mA.
    These thresholds are NOT a change-from-previous-reading rule. Delta columns
    are exported for inspection; they are not used to flag candidate activity.

WHAT IS SAVED (all analysis outputs under main/results, not .cache):
    stage_36/ ... stage_40/: all_readings.csv, bottom_points.csv,
        bottom_window.csv, downwards.csv, upwards.csv, stationary.csv,
        unknown.csv, anomaly_rows.csv, candidate_episodes.csv.
    activity_summary.csv: row/episode counts by stage and direction.
    anomaly_thresholds.csv: actual rules, thresholds, quartiles and IQR fences.
    candidate_episodes.csv: combined candidates with UTC times/depths.
    first_last_candidates.csv: first/last candidate START times and depths,
        last active reading, and candidate episode counts per stage.
    bottom_summary.csv: deepest readings and turnaround checks.
    spike_report.md: separate channel counts, first/last readings and example.
    plots/: per-stage activity plots, activity_zoom plots bounded by flagged
        readings' min/max depth and first/last time, and voltage/current boxes.
    full_dataset_iqr_summary.csv / full_dataset_boxplots.md: full-stage means,
        quartiles, 1.5*IQR fences and outlier counts (no depth/activity filter).
    stage_XX/full_data_iqr_outliers.csv: original features and per-channel flags.
    plots/full_dataset_boxplots.png / stage_XX_full_dataset_boxplots.png:
        full-stage distributions, mean markers and individual IQR outlier points.

READ THIS BEFORE REPORTING SHOTS:
    A nonzero reading marks electrical activity, not necessarily a firing.
    BOTH episodes require voltage AND current to exceed their thresholds.
    Multiple active rows form one episode, but dropouts can split a physical
    event. These are candidate shot estimates needing pattern validation.
    Box plots are diagnostics only: Q1=Q3=0 is common for mostly-off channels,
    so an IQR outlier is not independent evidence of a shot.
    Rerunning replaces generated files with the same names; inputs are unchanged.

LATEST SHOT ASSUMPTION:
    SHOT_CURRENT_THRESHOLD_MA = 500.0, inclusive TCURR >= 500 mA (0.5 A).
    current_threshold_analysis(annotated, bottoms) writes results/current_500mA/:
    report.md, shot_summary.csv, stage_XX_readings.csv, stage_XX_pulses.csv,
    and stage_XX_threshold.png. No voltage or IQR condition is used here.
    One contiguous above-threshold pulse is one assumed shot. Rows within that
    pulse are NOT separate shots; dips below threshold split pulses without
    debounce. Review that assumption before claiming a verified firing count.
"""

import csv
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
(ROOT / ".cache/matplotlib").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
from ThreeWToolkit.dataset import load_csv


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/shot_count_case/data"
SENSORS = ["ADPTH", "LTEN", "LSPD", "TVOLT", "TCURR", "CCL"]
BOTTOM_WINDOW_FT = 3000.0
DEPTH_TOLERANCE_FT = 0.1  # Sensor quantization tolerance, not a well-depth cutoff.
TREND_NEIGHBORS = 5  # Offline inspection: five readings before and after each row.
ACTIVITY_THRESHOLDS = {"TVOLT": 0.0, "TCURR": 0.0}
OUTPUT = ROOT / "results"
MAX_EPISODE_GAP_SECONDS = 2.0
SHOT_CURRENT_THRESHOLD_MA = 500.0


def load_stage(stage: int) -> pd.DataFrame:
    """Read one stage as a pandas DataFrame using the toolkit CSV loader."""
    path = DATA / f"stage_{stage}.csv"
    with path.open(newline="") as stream:
        columns = next(csv.reader(stream))
    frame = load_csv(str(path), columns, ["time_utc"], True)
    frame["source_row"] = range(len(frame))  # zero-based CSV data row before sorting
    frame["time_utc"] = pd.to_datetime(frame["time_utc"], utc=True, errors="raise")
    for column in ["frame_seq", *SENSORS]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    # Preserve all readings, ordering tied timestamps by frame_seq.
    return frame.sort_values(
        ["time_utc", "frame_seq"], kind="stable"
    ).reset_index(drop=True)


def infer_bottom(frame: pd.DataFrame, window_ft=BOTTOM_WINDOW_FT) -> dict:
    """Find the observed maximum and audit its neighboring depth readings.

    Increasing depth before and decreasing depth after support a turnaround.
    Repeated maximum values form a plateau. A maximum alone is not proof of
    physical bottom: report missing/contradictory neighbors or repeated visits.
    """
    if frame.empty or frame.ADPTH.dropna().empty or window_ft <= 0:
        raise ValueError("Need valid depth readings and a positive bottom window.")
    if not frame.ADPTH.dropna().between(-float("inf"), float("inf"), inclusive="neither").all():
        raise ValueError("Infinite depth readings must be investigated before finding bottom.")
    depth = frame.ADPTH.reset_index(drop=True)
    maximum = float(depth.max())
    positions = depth.index[depth.eq(maximum)]
    first, last = int(positions[0]), int(positions[-1])
    contiguous = last - first + 1 == len(positions)
    before = frame.iloc[max(0, first - 20):first + 1]
    after = frame.iloc[last:min(len(frame), last + 21)]

    def trend_supported(part, increasing):
        delta = part.ADPTH.diff().dropna()
        connected = (part.device_id.nunique() == 1
                     and not part.time_utc.diff().dt.total_seconds().gt(2).any())
        correct_sign = (delta >= -1e-8).all() if increasing else (delta <= 1e-8).all()
        net = part.ADPTH.iloc[-1] - part.ADPTH.iloc[0]
        return bool(len(delta) > 0 and connected and correct_sign
                    and (net > 0 if increasing else net < 0))

    rising = trend_supported(before, True)
    falling = trend_supported(after, False)
    return {"bottom_depth_ft": maximum, "depth_cutoff_ft": maximum - window_ft,
            "window_ft": window_ft, "first_bottom_row": first, "last_bottom_row": last,
            "first_bottom_utc": frame.time_utc.iloc[first],
            "last_bottom_utc": frame.time_utc.iloc[last],
            "contiguous_maximum_plateau": contiguous,
            "increasing_before": rising, "decreasing_after": falling,
            "turnaround_supported": contiguous and rising and falling}


def infer_depth_movement(frame: pd.DataFrame, bottom: dict) -> pd.DataFrame:
    """Use neighboring depth readings, not speed, for local movement.

    Flat/quantized neighborhoods are stationary; conflicting local trends are
    unknown. Never compare across telemetry gaps or devices. This uses future
    rows for retrospective analysis, so it is not an online detector.
    travel_phase describes the overall trip; movement describes local motion.
    """
    result = frame.copy()
    boundary = (result.time_utc.diff().dt.total_seconds().gt(2)
                | result.device_id.ne(result.device_id.shift())
                | result.ADPTH.isna() | result.ADPTH.shift().isna())
    segments = boundary.cumsum()
    grouped = result.ADPTH.groupby(segments)
    previous = grouped.shift(TREND_NEIGHBORS).fillna(result.ADPTH)
    following = grouped.shift(-TREND_NEIGHBORS).fillna(result.ADPTH)
    result["depth_change_ft"] = grouped.diff()
    result["depth_trend_ft"] = following - previous
    span = grouped.transform(lambda s: s.rolling(2 * TREND_NEIGHBORS + 1,
                                                center=True, min_periods=1).max()
                              - s.rolling(2 * TREND_NEIGHBORS + 1,
                                          center=True, min_periods=1).min())
    result["movement"] = "unknown"
    tolerance = DEPTH_TOLERANCE_FT + 1e-8
    result.loc[span.le(tolerance), "movement"] = "stationary"
    result.loc[result.depth_trend_ft.gt(tolerance), "movement"] = "downwards"
    result.loc[result.depth_trend_ft.lt(-tolerance), "movement"] = "upwards"
    result.loc[result.ADPTH.isna(), "movement"] = "unknown"
    result["travel_phase"] = "unconfirmed"
    if bottom["turnaround_supported"]:
        result.loc[result.index < bottom["first_bottom_row"], "travel_phase"] = "before_bottom"
        result.loc[result.index > bottom["last_bottom_row"], "travel_phase"] = "after_bottom"
        result.loc[result.index.to_series().between(bottom["first_bottom_row"],
                                                    bottom["last_bottom_row"]), "travel_phase"] = "bottom_plateau"
    return result


def mark_electrical_activity(frame: pd.DataFrame, max_gap_seconds=MAX_EPISODE_GAP_SECONDS) -> pd.DataFrame:
    """Flag departures from panel-off zero; these are NOT confirmed shots.

    Assign contiguous episode IDs BEFORE depth/direction filtering. A new
    episode starts after an inactive reading, device change, or telemetry gap.
    One pulse can contain many rows; do not treat active rows as shot counts.
    """
    result = frame.copy()
    boundary = (result.time_utc.diff().dt.total_seconds().gt(max_gap_seconds)
                | result.device_id.ne(result.device_id.shift()))
    for sensor, threshold in ACTIVITY_THRESHOLDS.items():
        result[f"{sensor}_active"] = result[sensor].abs().gt(threshold)
        result[f"{sensor}_departure_from_zero"] = result[sensor].abs()
        result[f"{sensor}_threshold"] = threshold
        # Blank delta at a gap/device boundary: there is no comparable prior reading.
        result[f"{sensor}_change_from_previous"] = result[sensor].diff().mask(boundary)
        result[f"{sensor}_abs_change_from_previous"] = result[f"{sensor}_change_from_previous"].abs()
    result["BOTH_active"] = result.TVOLT_active & result.TCURR_active
    result["ANY_active"] = result.TVOLT_active | result.TCURR_active
    for sensor in ["TVOLT", "TCURR", "BOTH"]:
        active = result[f"{sensor}_active"]
        starts = active & (~active.shift(fill_value=False) | boundary)
        result[f"{sensor}_episode"] = starts.cumsum().where(active).astype("Int64")
    return result


def split_directions(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Separate locally inferred depth movement while preserving time order."""
    return {direction: frame.loc[frame.movement.eq(direction)].copy()
            for direction in ["downwards", "upwards", "stationary", "unknown"]}


def filter_depth(frame: pd.DataFrame, bottom: dict) -> pd.DataFrame:
    """Keep [stage maximum - 3,000 ft, stage maximum] for every direction.

    Infer bottom from the COMPLETE stage, never from a direction subset.
    Never sort by depth: upwards data must retain its bottom-to-surface order.
    """
    return frame.loc[frame.ADPTH.between(bottom["depth_cutoff_ft"], bottom["bottom_depth_ft"])].copy()


def count_activity(frame: pd.DataFrame, stage: int, direction: str, bottom: dict) -> dict:
    """Count candidate rows and distinct electrical episodes, not shots.

    Episodes spanning multiple motion states appear in multiple state counts;
    those counts must not be added to obtain the stage total.
    """
    result = {"stage": stage, "direction": direction,
              "depth_cutoff_ft": bottom["depth_cutoff_ft"], "bottom_depth_ft": bottom["bottom_depth_ft"],
              "rows_in_depth_band": len(frame), "has_depth_coverage": not frame.empty}
    for sensor in ["TVOLT", "TCURR", "BOTH"]:
        result[f"{sensor}_active_rows"] = int(frame[f"{sensor}_active"].sum())
        result[f"{sensor}_episodes"] = frame[f"{sensor}_episode"].nunique()
    return result


def candidate_episode_table(frame: pd.DataFrame, stage: int) -> pd.DataFrame:
    """List each simultaneous voltage/current episode in the selected band.

    Times are first/last OBSERVED active readings within the depth band.
    These candidates can include panel activation or other non-firing activity.
    """
    records = []
    for episode, group in frame[frame.BOTH_active].groupby("BOTH_episode"):
        records.append({
            "stage": stage, "candidate_episode": int(episode),
            "first_active_utc": group.time_utc.iloc[0],
            "last_active_utc": group.time_utc.iloc[-1],
            "first_depth_ft": group.ADPTH.iloc[0], "last_depth_ft": group.ADPTH.iloc[-1],
            "active_rows": len(group), "peak_voltage_V": group.TVOLT.max(),
            "peak_current_mA": group.TCURR.max(),
            "movement_states": ",".join(group.movement.unique()),
        })
    return pd.DataFrame(records, columns=[
        "stage", "candidate_episode", "first_active_utc", "last_active_utc",
        "first_depth_ft", "last_depth_ft", "active_rows", "peak_voltage_V",
        "peak_current_mA", "movement_states",
    ])


def threshold_report(frame: pd.DataFrame, stage: int, bottom: dict) -> pd.DataFrame:
    """Export the actual detection rule separately from box-plot diagnostics."""
    records = []
    for sensor, threshold in ACTIVITY_THRESHOLDS.items():
        values = frame[sensor].dropna()
        q1, median, q3 = values.quantile([.25, .5, .75])
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        records.append({
            "stage": stage, "sensor": sensor, "units": "V" if sensor == "TVOLT" else "mA",
            "baseline": 0.0, "actual_rule": "abs(value - baseline) > threshold",
            "actual_threshold": threshold, "previous_reading_change_used": False,
            "previous_reading_change_threshold": None,
            "max_episode_gap_seconds": MAX_EPISODE_GAP_SECONDS,
            "depth_cutoff_ft": bottom["depth_cutoff_ft"], "bottom_depth_ft": bottom["bottom_depth_ft"],
            "rows": len(frame), "flagged_rows": int(frame[f"{sensor}_active"].sum()),
            "q1": q1, "median": median, "q3": q3, "iqr": iqr,
            "iqr_lower_fence": low, "iqr_upper_fence": high,
            "iqr_degenerate": bool(iqr == 0), "iqr_used_for_detection": False,
            "iqr_outlier_rows_diagnostic_only": int(((values < low) | (values > high)).sum()),
            "largest_abs_step": frame[f"{sensor}_abs_change_from_previous"].max(),
        })
    return pd.DataFrame(records)


def export_stage_results(stage: int, full: pd.DataFrame, deep: pd.DataFrame,
                         bottom: dict, episodes: pd.DataFrame) -> None:
    """Save every original feature plus derived flags/deltas, preserving UTC."""
    directory = OUTPUT / f"stage_{stage}"
    directory.mkdir(parents=True, exist_ok=True)

    def save(frame, filename):
        frame.assign(stage=stage).to_csv(directory / filename, index=False)

    save(full, "all_readings.csv")
    save(full[full.ADPTH.eq(bottom["bottom_depth_ft"])], "bottom_points.csv")
    save(deep, "bottom_window.csv")
    for name, part in split_directions(deep).items():
        save(part, f"{name}.csv")
    # Includes voltage-only OR current-only readings; BOTH_active identifies
    # the stricter simultaneous subset used to generate candidate episodes.
    save(deep[deep.ANY_active], "anomaly_rows.csv")
    episodes.to_csv(directory / "candidate_episodes.csv", index=False)


def first_last_candidates(episodes: pd.DataFrame, stage: int, bottom: dict) -> dict:
    """Summarize candidate starts, rather than confusing final row with final shot."""
    result = {"stage": stage, "candidate_episode_count": len(episodes),
              "status": "electrical candidates; not confirmed shots",
              "depth_cutoff_ft": bottom["depth_cutoff_ft"],
              "bottom_depth_ft": bottom["bottom_depth_ft"],
              "first_candidate_start_utc": None, "first_candidate_depth_ft": None,
              "last_candidate_start_utc": None, "last_candidate_depth_ft": None,
              "last_active_reading_utc": None, "last_active_depth_ft": None}
    if not episodes.empty:
        ordered = episodes.sort_values("first_active_utc")
        first, last = ordered.iloc[0], ordered.iloc[-1]
        result.update({
            "first_candidate_start_utc": first.first_active_utc,
            "first_candidate_depth_ft": first.first_depth_ft,
            "last_candidate_start_utc": last.first_active_utc,
            "last_candidate_depth_ft": last.first_depth_ft,
            "last_active_reading_utc": last.last_active_utc,
            "last_active_depth_ft": last.last_depth_ft,
        })
    return result


def analyze_full_stage_outliers(stages: dict) -> pd.DataFrame:
    """Box plots and Tukey outliers on ALL rows, including panel-off zeros.

    Outlier = value < Q1 - 1.5*IQR OR value > Q3 + 1.5*IQR.
    Mean is descriptive and not the detection threshold. When IQR is zero,
    report that degeneracy; do not silently substitute a different baseline.
    A statistical outlier is not automatically a shot or a sensor fault.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory = OUTPUT / "plots"
    directory.mkdir(parents=True, exist_ok=True)
    summaries = []
    style = dict(whis=1.5, showfliers=True, showmeans=True,
                 flierprops={"marker": "o", "markersize": 3, "markerfacecolor": "#d76416",
                             "markeredgecolor": "#d76416", "alpha": .5},
                 meanprops={"marker": "D", "markersize": 5, "markerfacecolor": "#008755",
                            "markeredgecolor": "#008755"})
    for stage, frame in stages.items():
        export = frame.copy()
        fig, axes = plt.subplots(1, 2, figsize=(11, 6))
        for ax, sensor in zip(axes, ["TVOLT", "TCURR"]):
            values = frame[sensor].dropna()
            if values.empty or not values.between(-float("inf"), float("inf"), inclusive="neither").all():
                raise ValueError(f"Stage {stage} {sensor}: need finite readings for box plots.")
            q1, median, q3 = values.quantile([.25, .5, .75])
            iqr = q3 - q1
            low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            flag = frame[sensor].lt(low) | frame[sensor].gt(high)
            export[f"{sensor}_iqr_outlier"] = flag
            export[f"{sensor}_iqr_lower_fence"] = low
            export[f"{sensor}_iqr_upper_fence"] = high
            inside = values[values.between(low, high)]
            summaries.append({
                "stage": stage, "sensor": sensor, "units": "V" if sensor == "TVOLT" else "mA",
                "total_rows": len(frame), "valid_rows": len(values), "missing_rows": frame[sensor].isna().sum(),
                "zero_rows": int(values.eq(0).sum()), "mean": values.mean(),
                "std": values.std(), "min": values.min(), "q1": q1, "median": median,
                "q3": q3, "max": values.max(), "iqr": iqr,
                "lower_fence": low, "upper_fence": high,
                "observed_inlier_min": inside.min(), "observed_inlier_max": inside.max(),
                "outlier_rows": int(flag.sum()), "outlier_percent": 100 * flag.sum() / len(values),
                "iqr_degenerate": bool(iqr == 0), "scope": "all stage rows, zeros included",
                "rule": "value < Q1-1.5*IQR or value > Q3+1.5*IQR",
            })
            ax.boxplot(values, **style)
            ax.set_xticks([1], [sensor])
            ax.set_ylabel("Voltage (V)" if sensor == "TVOLT" else "Current (mA)")
            ax.set_title(f"Mean {values.mean():.4f} | Median {median:.2f}\n"
                         f"IQR fences [{low:.2f}, {high:.2f}] | {flag.sum()} outlier rows")
            ax.grid(axis="y", alpha=.2)
        fig.suptitle(f"Stage {stage}: ALL {len(frame):,} readings — no depth or nonzero filter")
        fig.text(.5, .015, "Orange dots: 1.5×IQR outliers. Green diamond: mean. "
                 "Box may collapse to zero when most readings are off; outliers are not confirmed shots.",
                 ha="center", fontsize=8)
        fig.tight_layout(rect=(0, .05, 1, .93))
        fig.savefig(directory / f"stage_{stage}_full_dataset_boxplots.png", dpi=140)
        plt.close(fig)
        stage_dir = OUTPUT / f"stage_{stage}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        export.loc[export.TVOLT_iqr_outlier | export.TCURR_iqr_outlier].assign(stage=stage).to_csv(
            stage_dir / "full_data_iqr_outliers.csv", index=False)

    summary = pd.DataFrame(summaries)
    summary.to_csv(OUTPUT / "full_dataset_iqr_summary.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, sensor in zip(axes, ["TVOLT", "TCURR"]):
        ax.boxplot([frame[sensor].dropna() for frame in stages.values()], **style)
        ax.set_xticks(range(1, len(stages) + 1), [str(stage) for stage in stages])
        ax.set(xlabel="Stage", ylabel="V" if sensor == "TVOLT" else "mA", title=sensor)
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Full datasets: voltage and current by stage — all readings including zeros")
    fig.text(.5, .015, "Orange dots = IQR outliers; green diamonds = means. "
             "Collapsed boxes reflect mostly-zero data, not absent outliers.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, .94))
    fig.savefig(directory / "full_dataset_boxplots.png", dpi=140)
    plt.close(fig)
    lines = ["# Full-dataset voltage and current box plots", "",
             "All stage readings are included; no depth or activity filter is applied. "
             "Outliers lie below Q1 − 1.5×IQR or above Q3 + 1.5×IQR. The mean is not a threshold.", "",
             "| Stage | Sensor | Mean | Median | IQR lower fence | IQR upper fence | Outlier rows |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in summary.itertuples():
        lines.append(f"| {row.stage} | {row.sensor} | {row.mean:.4f} | {row.median:.2f} | "
                     f"{row.lower_fence:.2f} | {row.upper_fence:.2f} | {row.outlier_rows} |")
    if summary.iqr_degenerate.any():
        lines.extend(["", "Some distributions have IQR = 0 because readings are mostly zero. "
                      "Their box-plot fences collapse to zero: both a small nonzero reading and a large spike "
                      "can therefore be IQR outliers. This does not establish a firing threshold or a normal "
                      "range while the panel is energized."])
    lines.extend(["", "![All-stage box plots](plots/full_dataset_boxplots.png)"])
    (OUTPUT / "full_dataset_boxplots.md").write_text("\n".join(lines) + "\n")
    return summary


def plot_boxplots(frame: pd.DataFrame, stage: int) -> None:
    """Show all readings and active-only distributions; IQR is diagnostic."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    for column, sensor in enumerate(["TVOLT", "TCURR"]):
        for row, active_only in enumerate([False, True]):
            ax = axes[row, column]
            values = frame.loc[frame[f"{sensor}_active"], sensor] if active_only else frame[sensor]
            values = values.dropna()
            if len(values):
                ax.boxplot(values, whis=1.5, showfliers=True)
            else:
                ax.text(.5, .5, "No readings", ha="center", transform=ax.transAxes)
            ax.axhline(ACTIVITY_THRESHOLDS[sensor], color="red", linestyle="--", label="Positive activity threshold")
            ax.set_title(f"{sensor}: {'active only' if active_only else 'all bottom-window rows'} (n={len(values)})")
            ax.set_ylabel("V" if sensor == "TVOLT" else "mA")
            ax.set_xticks([])
            ax.grid(axis="y", alpha=.2)
    fig.suptitle(f"Stage {stage}: distributions — box-plot fences do not define shots")
    fig.tight_layout(rect=(0, 0, 1, .95))
    directory = OUTPUT / "plots"
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / f"stage_{stage}_boxplots.png", dpi=130)
    plt.close(fig)


def plot_activity(frame: pd.DataFrame, stage: int, bottom: dict, zoom=False) -> Path:
    """Plot both channels; optionally zoom to flagged activity with 5% padding.

    Both sensors share bounds from the union of their active readings, so their
    plots remain comparable. Change only axis limits, retaining inactive rows
    between pulses and the original candidate flags/counts.
    """
    cache = ROOT / ".cache/matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    flagged = frame.loc[frame.TVOLT_active | frame.TCURR_active]
    zoom_bounds = None
    if zoom and not flagged.empty:
        depth_min, depth_max = flagged.ADPTH.min(), flagged.ADPTH.max()
        depth_pad = max((depth_max - depth_min) * .05, 1.0)
        time_start, time_end = flagged.time_utc.min(), flagged.time_utc.max()
        time_pad = pd.Timedelta(seconds=max((time_end - time_start).total_seconds() * .05, 1.0))
        zoom_bounds = (depth_min - depth_pad, depth_max + depth_pad,
                       time_start - time_pad, time_end + time_pad)
    colors = {"downwards": "#2265bc", "upwards": "#e07c16",
              "stationary": "#a32a86", "unknown": "#333333"}
    for column, sensor in enumerate(["TVOLT", "TCURR"]):
        time_ax, depth_ax = axes[0, column], axes[1, column]
        if frame.empty:
            for ax in [time_ax, depth_ax]:
                ax.text(.5, .5, f"No readings in bottom {bottom['window_ft']:,.0f} ft\n"
                        f"Stage maximum: {bottom['bottom_depth_ft']:,.1f} ft", ha="center",
                        va="center", transform=ax.transAxes)
        else:
            # Filtered-out rows/gaps must not be bridged by artificial curves.
            breaks = (frame.index.to_series().diff().ne(1)
                      | frame.time_utc.diff().dt.total_seconds().gt(2)
                      | frame.device_id.ne(frame.device_id.shift()))
            breaks.iloc[0] = False
            curve = frame[sensor].mask(breaks)
            time_ax.plot(frame.time_utc, curve, color="#bbbbbb", lw=.7)
            depth_ax.plot(curve, frame.ADPTH, color="#bbbbbb", lw=.7)
            for direction, color in colors.items():
                active = frame[frame.movement.eq(direction) & frame[f"{sensor}_active"]]
                if active.empty:
                    continue
                label = f"{direction}: {len(active)} active rows"
                time_ax.scatter(active.time_utc, active[sensor], s=8, color=color, label=label)
                depth_ax.scatter(active[sensor], active.ADPTH, s=8, color=color)
            if frame[f"{sensor}_active"].any():
                time_ax.legend(fontsize=8)
            time_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz="UTC"))
        unit = "V" if sensor == "TVOLT" else "mA"
        time_ax.set(title=f"{sensor}: electrical activity", xlabel="Time (UTC)", ylabel=unit)
        depth_ax.set(xlabel=f"{sensor} ({unit})", ylabel="Measured depth (ft)")
        depth_ax.invert_yaxis()
        if zoom_bounds is not None:
            # Reversed depth limits keep increasing measured depth downward.
            depth_ax.set_ylim(zoom_bounds[1], zoom_bounds[0])
            time_ax.set_xlim(zoom_bounds[2], zoom_bounds[3])
        for ax in [time_ax, depth_ax]:
            ax.grid(alpha=.2)
    if zoom_bounds is not None:
        title = f"Stage {stage} | activity zoom | flagged depths {depth_min:,.1f}–{depth_max:,.1f} ft"
    elif zoom:
        title = f"Stage {stage} | no flagged activity to zoom into"
    else:
        title = f"Stage {stage} | {bottom['depth_cutoff_ft']:,.1f}–{bottom['bottom_depth_ft']:,.1f} ft | bottom {bottom['window_ft']:,.0f} ft"
    fig.suptitle(title)
    fig.text(.5, .012, "Electrical activity candidates, not confirmed shots. Direction uses neighboring depths; flat within 0.1 ft = stationary. "
             "Rows are not shots; one episode spans multiple rows.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .95))
    (OUTPUT / "plots").mkdir(parents=True, exist_ok=True)
    suffix = "_zoom" if zoom else ""
    path = OUTPUT / "plots" / f"stage_{stage}_activity{suffix}.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def current_threshold_rows(frame: pd.DataFrame, bottom: dict,
                           threshold_ma=SHOT_CURRENT_THRESHOLD_MA) -> pd.DataFrame:
    """Mark current-only pulses BEFORE selecting depth; preserve original features.

    A new pulse follows a below-threshold/missing reading, a telemetry gap >2s,
    or a device change. Equal timestamps retain their frame_seq ordering.
    """
    result = frame.copy()
    active = result.TCURR.ge(threshold_ma)
    boundary = (result.time_utc.diff().dt.total_seconds().gt(MAX_EPISODE_GAP_SECONDS)
                | result.device_id.ne(result.device_id.shift()))
    starts = active & (~active.shift(fill_value=False) | boundary)
    result["current_threshold_mA"] = threshold_ma
    result["current_at_least_threshold"] = active
    result["current_pulse_id"] = starts.cumsum().where(active).astype("Int64")
    return filter_depth(result, bottom)


def current_threshold_analysis(annotated: dict, bottoms: dict,
                               threshold_ma=SHOT_CURRENT_THRESHOLD_MA) -> pd.DataFrame:
    """Save threshold-selected rows, distinct pulses and first/last pulse starts."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    destination = OUTPUT / f"current_{threshold_ma:g}mA"
    destination.mkdir(parents=True, exist_ok=True)
    summaries = []
    for stage, full in annotated.items():
        deep = current_threshold_rows(full, bottoms[stage], threshold_ma)
        selected = deep[deep.current_at_least_threshold].copy()
        selected.assign(stage=stage).to_csv(destination / f"stage_{stage}_readings.csv", index=False)
        pulses = []
        for pulse_id, group in selected.groupby("current_pulse_id"):
            first, last = group.iloc[0], group.iloc[-1]
            pulses.append({
                "stage": stage, "pulse_id": int(pulse_id), "threshold_mA": threshold_ma,
                "start_utc": first.time_utc, "end_utc": last.time_utc,
                "start_depth_ft": first.ADPTH, "end_depth_ft": last.ADPTH,
                "qualifying_rows": len(group), "peak_current_mA": group.TCURR.max(),
                "peak_voltage_V": group.TVOLT.max(), "direction_at_start": first.movement,
                "movement_states": ",".join(group.movement.unique()),
                "observed_duration_s": (last.time_utc - first.time_utc).total_seconds(),
            })
        events = pd.DataFrame(pulses, columns=["stage", "pulse_id", "threshold_mA", "start_utc",
            "end_utc", "start_depth_ft", "end_depth_ft", "qualifying_rows", "peak_current_mA",
            "peak_voltage_V", "direction_at_start", "movement_states", "observed_duration_s"])
        events.to_csv(destination / f"stage_{stage}_pulses.csv", index=False)
        record = {"stage": stage, "threshold_mA": threshold_ma, "assumed_shots": len(events),
                  "qualifying_rows": len(selected),
                  "unique_readings": len(selected.drop_duplicates(["device_id", "time_utc", "frame_seq"])),
                  "depth_cutoff_ft": bottoms[stage]["depth_cutoff_ft"],
                  "bottom_depth_ft": bottoms[stage]["bottom_depth_ft"]}
        for name in ["downwards", "upwards", "stationary", "unknown"]:
            record[f"{name}_pulse_starts"] = int(events.direction_at_start.eq(name).sum())
        for prefix in ["first", "last"]:
            event = events.iloc[0 if prefix == "first" else -1] if not events.empty else None
            record[f"{prefix}_shot_start_utc"] = event.start_utc if event is not None else None
            record[f"{prefix}_shot_depth_ft"] = event.start_depth_ft if event is not None else None
        record["last_above_threshold_utc"] = selected.time_utc.iloc[-1] if len(selected) else None
        summaries.append(record)

        fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
        breaks = (deep.index.to_series().diff().ne(1)
                  | deep.time_utc.diff().dt.total_seconds().gt(MAX_EPISODE_GAP_SECONDS)
                  | deep.device_id.ne(deep.device_id.shift()))
        if len(breaks):
            breaks.iloc[0] = False
        axes[0].plot(deep.time_utc, deep.TCURR.mask(breaks), lw=.7, color="#999999")
        axes[0].scatter(selected.time_utc, selected.TCURR, s=12, color="#d76416", label=f">= {threshold_ma:g} mA")
        axes[0].axhline(threshold_ma, color="red", ls="--", label="Threshold")
        axes[0].set_ylabel("Current (mA)")
        axes[0].legend()
        axes[1].plot(deep.time_utc, deep.ADPTH.mask(breaks), lw=.7, color="#999999")
        axes[1].scatter(selected.time_utc, selected.ADPTH, s=12, color="#d76416")
        axes[1].invert_yaxis()
        axes[1].set(ylabel="Measured depth (ft)", xlabel="Time (UTC)")
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz="UTC"))
        if len(selected):
            padding = pd.Timedelta(seconds=max((selected.time_utc.max()-selected.time_utc.min()).total_seconds()*.05, 1))
            axes[1].set_xlim(selected.time_utc.min()-padding, selected.time_utc.max()+padding)
        for ax in axes:
            ax.grid(alpha=.2)
        fig.suptitle(f"Stage {stage}: {len(events)} assumed shots from contiguous TCURR >= {threshold_ma:g} mA pulses")
        fig.tight_layout(rect=(0, 0, 1, .95))
        fig.savefig(destination / f"stage_{stage}_threshold.png", dpi=130)
        plt.close(fig)

    summary = pd.DataFrame(summaries)
    summary.to_csv(destination / "shot_summary.csv", index=False)
    lines = [f"Rule: TCURR ≥ {threshold_ma:g} mA; one contiguous qualifying pulse = one assumed shot. "
             "Bottom 3,000-ft window per stage; no voltage or IQR requirement.", "",
             "| Stage | Assumed shots | Downward | Upward | Stationary | Unknown | Unique readings |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in summary.itertuples():
        lines.append(f"| {r.stage} | {r.assumed_shots} | {r.downwards_pulse_starts} | {r.upwards_pulse_starts} | "
                     f"{r.stationary_pulse_starts} | {r.unknown_pulse_starts} | {r.unique_readings} |")
    lines.extend(["", "| Stage | First pulse start (UTC) | Depth (ft) | Last pulse start (UTC) | Depth (ft) |",
                  "| --- | --- | --- | --- | --- |"])
    for r in summary.itertuples():
        lines.append(f"| {r.stage} | {r.first_shot_start_utc} | {r.first_shot_depth_ft} | "
                     f"{r.last_shot_start_utc} | {r.last_shot_depth_ft} |")
    lines.extend(["", "Below-threshold dips and gaps longer than two seconds split pulses. "
                  "Direction is measured at pulse start. These counts depend on the chosen rule; no firing labels validate them."])
    (destination / "report.md").write_text("\n".join(lines) + "\n")
    return summary


def write_spike_report(annotated: dict, bottoms: dict) -> Path:
    """Report each channel independently; count contiguous >threshold episodes.

    Attribute each episode once, using movement at its first flagged reading
    inside the selected depth band. Do not merge voltage/current detections.
    """
    counts, timings = [], []
    example = None
    for stage, frame in annotated.items():
        deep = filter_depth(frame, bottoms[stage])
        for sensor in ["TVOLT", "TCURR"]:
            flagged = deep.loc[deep[f"{sensor}_active"]].sort_values(
                ["time_utc", "frame_seq"], kind="stable")
            starts = flagged.drop_duplicates(f"{sensor}_episode", keep="first")
            counts.append([stage, sensor, len(starts),
                           *[int(starts.movement.eq(name).sum()) for name in
                             ["downwards", "upwards", "stationary", "unknown"]]])
            if flagged.empty:
                timings.append([stage, sensor, "—", "—", "—", "—"])
            else:
                first, last = flagged.iloc[0], flagged.iloc[-1]
                timings.append([stage, sensor, first.time_utc.isoformat(timespec="milliseconds"),
                                f"{first.ADPTH:.1f}", last.time_utc.isoformat(timespec="milliseconds"),
                                f"{last.ADPTH:.1f}"])
        both = deep[deep.BOTH_active]
        if example is None and not both.empty:
            first = both.iloc[0]
            episode = both[both.BOTH_episode.eq(first.BOTH_episode)]
            example = (stage, first, episode.TVOLT.max(), episode.TCURR.max())

    def table(headers, rows):
        return "\n".join(["| " + " | ".join(headers) + " |",
                          "| " + " | ".join(["---"] * len(headers)) + " |",
                          *["| " + " | ".join(map(str, row)) + " |" for row in rows]])

    text = table(["Stage", "Channel", "Spikes (nonzero episodes)", "Downward starts",
                  "Upward starts", "Stationary starts", "Unclear starts"], counts)
    text += "\n\n" + table(["Stage", "Channel", "First flagged time (UTC)", "Depth (ft)",
                            "Last flagged time (UTC)", "Depth (ft)"], timings)
    if example:
        stage, first, voltage, current = example
        text += (f"\n\nCandidate pattern: voltage and current depart from zero together. "
                 f"Example: stage {stage}, {first.time_utc.isoformat(timespec='milliseconds')}, "
                 f"{first.ADPTH:.1f} ft; that episode peaks at {voltage:.1f} V and {current:.1f} mA. "
                 "Electrical spikes are candidates, not confirmed shots.\n\n"
                 f"![Stage {stage}: voltage/current activity zoom](plots/stage_{stage}_activity_zoom.png)\n")
    path = OUTPUT / "spike_report.md"
    path.write_text(text + "\n")
    pd.DataFrame(counts, columns=["stage", "channel", "spike_episodes", "downward_starts",
                                 "upward_starts", "stationary_starts", "unclear_starts"]).to_csv(
        OUTPUT / "separate_channel_spike_counts.csv", index=False)
    pd.DataFrame(timings, columns=["stage", "channel", "first_flagged_utc", "first_depth_ft",
                                  "last_flagged_utc", "last_depth_ft"]).to_csv(
        OUTPUT / "separate_channel_first_last.csv", index=False)
    return path


if __name__ == "__main__":
    # 1. Load each CSV separately. These variables are pandas DataFrames.
    load36 = load_stage(36)
    load37 = load_stage(37)
    load38 = load_stage(38)
    load39 = load_stage(39)
    load40 = load_stage(40)

    for stage, frame in zip(range(36, 41), [load36, load37, load38, load39, load40]):
        print(f"Stage {stage}: {len(frame):,} rows, {len(frame.columns)} columns")

    # 2. Label electrical activity and split each complete stage by movement.
    stages = dict(zip(range(36, 41), [load36, load37, load38, load39, load40]))
    full_dataset_iqr_summary = analyze_full_stage_outliers(stages)
    bottoms = {stage: infer_bottom(frame) for stage, frame in stages.items()}
    annotated = {stage: mark_electrical_activity(infer_depth_movement(frame, bottoms[stage]))
                 for stage, frame in stages.items()}
    current_shot_summary = current_threshold_analysis(annotated, bottoms)
    directions = {stage: split_directions(frame) for stage, frame in annotated.items()}
    downwards_state36, downwards_state37, downwards_state38, downwards_state39, downwards_state40 = (
        directions[stage]["downwards"] for stage in range(36, 41)
    )
    upwards_state36, upwards_state37, upwards_state38, upwards_state39, upwards_state40 = (
        directions[stage]["upwards"] for stage in range(36, 41)
    )
    stationary_state36, stationary_state37, stationary_state38, stationary_state39, stationary_state40 = (
        directions[stage]["stationary"] for stage in range(36, 41)
    )

    # 3. Filter every direction to the bottom 3,000 ft of its COMPLETE stage.
    # Example: deep_frames[36]["upwards"] is the filtered upwards DataFrame.
    deep_frames = {stage: {name: filter_depth(frame, bottoms[stage]) for name, frame in groups.items()}
                   for stage, groups in directions.items()}

    # 4. Count/visualize electrical anomalies relative to panel-off zero.
    # Do not call these confirmed shots until the firing pattern is validated.
    summaries, events, thresholds, first_last = [], [], [], []
    for stage, frame in annotated.items():
        assert sum(len(part) for part in directions[stage].values()) == len(frame)
        bottom = bottoms[stage]
        deep = filter_depth(frame, bottom)
        summaries.append(count_activity(deep, stage, "all", bottom))
        for name, part in deep_frames[stage].items():
            summaries.append(count_activity(part, stage, name, bottom))
        episodes = candidate_episode_table(deep, stage)
        events.append(episodes)
        thresholds.append(threshold_report(deep, stage, bottom))
        first_last.append(first_last_candidates(episodes, stage, bottom))
        export_stage_results(stage, frame, deep, bottom, episodes)
        path = plot_activity(deep, stage, bottom)
        plot_activity(deep, stage, bottom, zoom=True)
        plot_boxplots(deep, stage)
        print(f"Stage {stage}: {len(deep):,} rows in {bottom['depth_cutoff_ft']:,.1f}–"
              f"{bottom['bottom_depth_ft']:,.1f} ft; turnaround supported: {bottom['turnaround_supported']}; plot: {path}", flush=True)
    summary = pd.DataFrame(summaries)
    candidate_events = pd.concat(events, ignore_index=True)
    anomaly_thresholds = pd.concat(thresholds, ignore_index=True)
    first_last_summary = pd.DataFrame(first_last)
    summary.to_csv(OUTPUT / "activity_summary.csv", index=False)
    candidate_events.to_csv(OUTPUT / "candidate_episodes.csv", index=False)
    anomaly_thresholds.to_csv(OUTPUT / "anomaly_thresholds.csv", index=False)
    first_last_summary.to_csv(OUTPUT / "first_last_candidates.csv", index=False)
    pd.DataFrame([{"stage": stage, **bottom} for stage, bottom in bottoms.items()]).to_csv(
        OUTPUT / "bottom_summary.csv", index=False)
    print(summary[summary.direction.eq("all")].to_string(index=False))
    for sensor in ["TVOLT", "TCURR", "BOTH"]:
        totals = summary[summary.direction.eq("all")]
        print(f"{sensor}: {totals[f'{sensor}_active_rows'].gt(0).sum()}/5 stages have activity in the depth band")
    print("All depth windows come from each stage's observed maximum. Electrical episodes are not confirmed shots.")
    print(f"Earlier nonzero-activity comparison: {write_spike_report(annotated, bottoms)}")
    print(f"CURRENT SHOT RULE: TCURR >= {SHOT_CURRENT_THRESHOLD_MA:g} mA; contiguous pulses")
    print(current_shot_summary.to_string(index=False))
    print(f"Current-threshold report: {OUTPUT / f'current_{SHOT_CURRENT_THRESHOLD_MA:g}mA' / 'report.md'}")
    print(f"CSV files and PNG plots saved in: {OUTPUT}")
