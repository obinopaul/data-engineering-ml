"""Load stages 36–40 with ThreeWToolkit and save depth/time plots.

Run from main: .venv/bin/python plot_stage_data.py
Open .cache/shot_count_case/index.html in a browser to review every plot.
"""

from pathlib import Path
import csv
import sys

import matplotlib
matplotlib.use("Agg")  # Save plots without needing Jupyter or a GUI backend.
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ThreeWToolkit.dataset import load_csv
from ThreeWToolkit.data_visualization import PlotSeries

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/shot_count_case/data"
OUT = ROOT / ".cache/shot_count_case"
SENSORS = {
    "ADPTH": "Measured depth (ft)",
    "LTEN": "Line tension (lbs)",
    "LSPD": "Line speed (ft/min)",
    "TVOLT": "Panel voltage (V)",
    "TCURR": "Line current (mA)",
    "CCL": "Collar locator (relative)",
}


def load_stage(stage):
    path = DATA / f"stage_{stage}.csv"
    with path.open(newline="") as stream:
        columns = next(csv.reader(stream))
    frame = load_csv(str(path), columns, ["time_utc"], True)
    frame["time_utc"] = pd.to_datetime(frame.time_utc, utc=True, errors="raise")
    for column in ["frame_seq", *SENSORS]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    # Preserve readings sharing a timestamp; frame_seq supplies their order.
    return frame.sort_values(["time_utc", "frame_seq"], kind="stable").reset_index(drop=True)


def plot_stage(stage, frame):
    # Break lines across >2-second gaps and device changes rather than implying
    # continuous measurements. Leave the source frame and CSV untouched.
    breaks = (frame.time_utc.diff().dt.total_seconds().gt(2)
              | frame.device_id.ne(frame.device_id.shift()))
    breaks.iloc[0] = False
    signals = frame[list(SENSORS)].astype(float).replace([np.inf, -np.inf], np.nan)
    plotted = signals.copy()
    plotted.loc[breaks, :] = np.nan

    # Reuse the earlier study's shared-depth, inverted-y track layout.
    fig, axes = plt.subplots(1, 5, figsize=(16, 9), sharey=True)
    colors = ["#167d9a", "#6254ac", "#d28717", "#bd3b43", "#258958"]
    for ax, sensor, color in zip(axes, list(SENSORS)[1:], colors):
        ax.plot(plotted[sensor], plotted.ADPTH, color=color, linewidth=.55, alpha=.8)
        ax.set_xlabel(SENSORS[sensor])
        ax.set_title(sensor)
        ax.grid(alpha=.25)
    axes[0].invert_yaxis()
    axes[0].set_ylabel("Measured depth along well (ft) — increases downward")
    fig.suptitle(f"Stage {stage}: wireline sensor tracks | {len(frame):,} readings")
    fig.text(.5, .015, "Full run in acquisition order: downhole and return passes overlap. "
             "Measured depth is not vertical depth; negative values represent surface readings.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .035, 1, .96))
    fig.savefig(OUT / f"stage_{stage}_depth.png", dpi=140)
    plt.close(fig)

    # Use the toolkit's actual time-series plotting API for all six channels.
    fig, axes = plt.subplots(6, 1, figsize=(15, 12), sharex=True)
    for ax, (sensor, label) in zip(axes, SENSORS.items()):
        series = pd.Series(plotted[sensor].to_numpy(), index=frame.time_utc)
        PlotSeries(series, title=sensor, xlabel="", ylabel=label,
                   linewidth=.6, color="#167d9a").plot(ax=ax)
    axes[0].invert_yaxis()
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M", tz="UTC"))
    axes[-1].set_xlabel("Time (UTC)")
    fig.suptitle(f"Stage {stage}: chronological telemetry — full-resolution data")
    fig.tight_layout(rect=(0, 0, 1, .97))
    fig.savefig(OUT / f"stage_{stage}_time.png", dpi=140)
    plt.close(fig)
    return int(breaks.sum())


def main():
    print(f"Python environment: {sys.executable}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []
    for stage in range(36, 41):
        frame = load_stage(stage)
        breaks = plot_stage(stage, frame)
        summary.append({
            "stage": stage, "rows": len(frame),
            "start_utc": frame.time_utc.min(), "end_utc": frame.time_utc.max(),
            "min_depth_ft": frame.ADPTH.min(), "max_depth_ft": frame.ADPTH.max(),
            "missing_sensor_values": int(frame[list(SENSORS)].isna().sum().sum()),
            "duplicate_time_frame_device": int(frame.duplicated(["time_utc", "frame_seq", "device_id"]).sum()),
            "plot_breaks": breaks,
        })
        print(f"Stage {stage}: loaded {len(frame):,} rows; saved depth and time plots.", flush=True)
    table = pd.DataFrame(summary)
    table.to_csv(OUT / "stage_summary.csv", index=False)
    parts = ["<!doctype html><html><head><meta charset='utf-8'><title>Stage 36–40 wireline plots</title>",
             "<style>body{font-family:system-ui;margin:24px;max-width:1600px}img{width:100%}"
             "table{border-collapse:collapse;font-size:12px}td,th{padding:7px;border:1px solid #ddd}</style></head><body>",
             "<h1>Stages 36–40: wireline sensor plots</h1>",
             "<p>Loaded with ThreeWToolkit in main/.venv. Source files are unchanged. "
             "No smoothing, downsampling, imputation, or shot detection has been applied. "
             "Depth tracks combine outbound and return passes; time plots preserve their sequence. "
             "Lines break across gaps longer than two seconds or changes in device.</p>",
             table.to_html(index=False)]
    for stage in range(36, 41):
        parts.extend([f"<h2>Stage {stage}</h2>",
                      f"<img src='stage_{stage}_depth.png' alt='Stage {stage} depth tracks'>",
                      f"<img src='stage_{stage}_time.png' alt='Stage {stage} time series'>"])
    (OUT / "index.html").write_text("\n".join(parts) + "</body></html>")
    print(table.to_string(index=False))
    print(f"Open plots: {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
