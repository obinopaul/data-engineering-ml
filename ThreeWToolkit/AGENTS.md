# ThreeWToolkit Package Guide

## Scope and usage

This is the local copy of Petrobras ThreeWToolkit 3.2.1. Prefer composing its public APIs in [the starter notebook](../interview_starter.ipynb). Requirements live in [../pyproject.toml](../pyproject.toml); use the `main/.venv` kernel. This guide describes the copied source, not older tutorial APIs.

Most components use `SomeConfig(...).build()`. Dataset transformations follow `processor.fit(train_dataset)` and `processor.transform(dataset)`; transformed events are computed lazily. Clustering configurations instead go into constructors such as `DistanceComputer(DistanceMatrixConfig(...))`.

## Data contracts

```python
from ThreeWToolkit.core import BaseDataset, DatasetOutputs

# One event / uninterrupted sequence:
event = DatasetOutputs(
    signal=numeric_dataframe,  # rows=time steps; columns=sensors/features
    label=aligned_series,      # same row count/index; None for unlabeled data
    metadata={"event_id": "...", "event_class": 0, "event_type": "real"},
)
```

`BaseDataset` requires `__len__` and `__getitem__ -> DatasetOutputs`; iteration is provided. The notebook's `FrameDataset` adapts arbitrary tables to this contract. Keep signals numeric for toolkit feature extraction. Sort each event by time, preserve units, and never window across different events. After windowing, labels must align to feature rows.

Trainers return `TrainingResult(model, history, train_dataset_size, val_dataset_size, metadata)`. Predictions are `PredictionResult(y_true, y_pred, metadata)`, imported from `core.base_trainer`. Assessment returns `AssessmentOutput` with `metrics`, `true_values`, `predictions`, and training history.

## Directory and import map

All import paths below start with `ThreeWToolkit.`. Listed symbols are examples of the current exports; inspect each package's `__init__.py` before adding others.

| Directory/module | Public imports and responsibility | Inputs and outputs |
|---|---|---|
| `assessment/` | `ModelAssessment`, `ModelAssessmentConfig`, `AssessmentVisualization`, `AssessmentVisualizationConfig` | `evaluate(training_results=..., predictions=...)` returns assessment; visualization accepts true/predicted arrays for confusion matrices. |
| `clustering/` | `InstanceQualityFilter`, `TimeSeriesResampler`, `TimeSeriesScaler`, `DistanceComputer`, `HierarchicalClusterer`, `DivisiveRanker`, `MultivariateConsensus`, `compute_dba_centroid` | Quality/scaling/resampling take lists of 1-D arrays; distances produce pairwise matrices; hierarchy produces linkage and threshold-based groups. Track `kept_indices_` after filtering. |
| `core/` | `BaseDataset`, `DatasetOutputs`, `BasePreprocessing`, `BaseFeatureExtractor`, `BaseModels`, `BaseTrainer`, `BaseTransform`, `BasePipeline`, assessment/visualization bases, corresponding base configs | Extension interfaces and structured outputs. `base_clustering.py` holds clustering configs; `enums.py` holds task, distance, linkage, and other enums. |
| `data_visualization/` | `DataVisualization`, `PlotSeries`, `PlotMultipleSeries`, `CorrelationHeatmap`, `PlotFFT`, `SeasonalDecompositionPlot`, `WaveletSpectrogramPlot`, `ThreeWChart` | Series/DataFrames → plots. The facade returns `(figure, axes)`; `ThreeWChart` is the 3W Parquet/Plotly viewer. |
| `data_visualization/clustering_plots.py` | Exported `DataQualityHeatmap`, `DendrogramPlot`, `ClusterSizeCurvePlot`, `SelectionHeatmapPlot`, `ClusteringOverlayPlot`, `RankedDistancePlot` | Clustering-specific matrices, series, and results → diagnostic plots. `plot_utils.py` provides subplot helpers. |
| `dataset/` | `ParquetDatasetConfig`, `ParquetDataset`, `load_csv`, `TransformConfig`, `TransformDataset`, `SubsetDataset`, `TransformedDataset` | 3W files → events; CSV helper → DataFrame; transform/subset wrappers operate on `BaseDataset`. |
| `feature_extraction/` | `WindowingConfig`, `StatisticalConfig`, `EWStatisticalConfig`, `WaveletConfig`, `SequentialFeatureAdapterConfig`, `ConcatFeatureAdapterConfig` and their implementations | Event signals → windows → numeric feature tables. Sequential adapters chain steps; concatenation combines feature families from the same windows. |
| `metrics/` | `accuracy_score`, `balanced_accuracy_score`, `precision_score`, `recall_score`, `f1_score`, `average_precision_score`, `roc_auc_score`, `matthews_corrcoef`, `explained_variance_score` | Ground truth and predictions/scores → metrics. Probability metrics need suitable scores, not hard labels. |
| `models/` | `MLP`, `MLPConfig`, `SklearnModels`, `SklearnModelsConfig` | Model definitions/wrappers. PyTorch extension types `TorchModels`, `TorchModelsConfig` are in `models.torch_models`, not package-level exports. |
| `preprocessing/` | `CleanSignalsConfig`, `ImputeMissingConfig`, `NormalizeConfig`, `RenameColumnsConfig`, `FillLabelsConfig`, `RemapClassConfig`, `SequentialPreprocessingAdapterConfig` and implementations | Fit statistics on a training dataset; transform individual `DatasetOutputs` via `TransformConfig`. |
| `reports/` | `ReportGeneration`; `html/` and `latex/` assets | Model, predictions, metrics, title, train/test lengths, and plot settings → HTML/LaTeX reports. Optional for interviews; PDF compilation needs external tooling. |
| `trainer/` | `SklearnTrainerConfig`, `SklearnTrainer`, `TorchTrainerConfig`, `TorchTrainer` | `train(train_dataset, val_dataset=None)`; `predict(dataset)`. Input datasets must already be transformed. |
| `utils/` | `TrainTestSplitter`, `KFoldSplitter`, `ModelRecorder`, `get_figshare_data`, `get_config_dataset_ini`, `load_config_in_dataset_ini` | Splits, model persistence, explicit downloading, and data-dictionary reading. `general_utils.py`, `trainer_logger.py`, `template_manager.py` are internal helpers. |
| `pipeline.py` | `Pipeline`, `PipelineConfig` | Configuration-driven orchestration with dataset configs, transform config, trainer config, and optional assessment. Prefer explicit notebook stages while learning. |
| `constants.py`, `logging_config.py` | Paths and logging initialization | Importing some modules creates logs under `main/output/`. Configure assessment output explicitly. |

## Configuration reference

| Configuration / operation | Main parameters and behavior |
|---|---|
| `ParquetDatasetConfig` | Required `path`; optional `event_type=["real", "simulated", "drawn"]`, `target_class`, `columns`, `target_column="class"`, `split="list"`, `file_list`. Intended for the full 3W layout. |
| `load_csv` | Required `file_path`, `column_names: list[str]`, `date_column: list[str]`, `parse_dates: bool`. For SQL/Excel/arbitrary Parquet use pandas, then adapt the DataFrame. |
| `TransformConfig` | `pre_processing=...`, `feature_extraction=...`; each accepts a configuration, not a built instance. |
| `CleanSignalsConfig` | `missing_column_threshold=0.6`, `average_iqr_threshold=3`, `std_iqr_threshold=3`, `absolute_std_threshold=1e-6`, `exclude_features`. Learns suspicious signal ranges and columns to drop. |
| `ImputeMissingConfig` | `strategy`: `constant` (default, `fill_value=0`), `mean`, `ffill`, `bfill`, `interpolate`; interpolation also needs `interpolate_method`. Mean uses training statistics; temporal fills act per event. |
| `NormalizeConfig` | `norm="l2"` (`l1`, `max`, numeric norms also supported), `exclude_features`, `eps`. Call `fit(training_dataset)` first: centers columns using the training mean and scales by training Lp dispersion plus epsilon. L2 is population-standard-deviation scaling, not per-row unit-vector normalization. |
| Label/column transforms | `RenameColumnsConfig(columns_map={...})`; `FillLabelsConfig(fill_method="nearest", fill_value=...)`; `RemapClassConfig(class_map=None)` learns a mapping. Do not invent missing ground truth; unseen test labels raise errors. |
| `WindowingConfig` | `window_size=128`, `overlap=0`, `label_strategy="last"` or `"mode"`, `window="boxcar"`, `pad_start=True`, `pad_last_window=False`, `pad_value=0`. Consider disabling start padding for physical interpretation. |
| Feature configurations | `StatisticalConfig(features=["mean", "std", "min", "max"])`; `EWStatisticalConfig(window_size=128, decay=0.95)`; `WaveletConfig(wavelet="haar", level=7, full=False)`. Match wavelet level to available window length; current validation requires level > 1. |
| Adapters | `SequentialPreprocessingAdapterConfig(steps=[...])`, `SequentialFeatureAdapterConfig(steps=[...])`, `ConcatFeatureAdapterConfig(steps=[...])`. Put windowing before statistical/wavelet extraction. |
| `SklearnModelsConfig` | Required `model_type` (estimator class), `model_params={...}`. Example: `RandomForestClassifier` with tree count, depth, seed. |
| `MLPConfig` | Required `hidden_sizes=(32, 16)` and inherited `output_size`; `activation_function=torch.nn.ReLU()`. Input size is inferred with lazy modules. |
| Trainer configs | Required `config_model`; both support `seed`, `use_class_weights`, `class_weight_strategy`. Sklearn: `n_jobs`, `verbose`. Torch: `epochs`, `batch_size`, `learning_rate`, `optimizer` class, `criterion` class, `device`, `deterministic`. |
| Assessment configs | `metrics`, `task_type`, `export_results`, `generate_report`, `output_dir`; visualization uses `class_names`. Available config metrics: accuracy, balanced_accuracy, precision, recall, f1, average_precision, explained_variance. Use direct metric functions for other scores. |
| Splitters | `TrainTestSplitter(size_training=0.8, size_test=0.2, shuffle=True, random_state=..., stratify_by=[...])`; proportions must sum to one. `KFoldSplitter(num_splits=5, ...)`. Stratification reads event metadata; these are not well-group-aware or chronological CV automatically. |
| Clustering configs | Import from `core.base_clustering`: `InstanceQualityConfig(max_nan_ratio, max_frozen_ratio, frozen_threshold)`, `ResamplingConfig(step_size, step_method)`, `TimeSeriesScalingConfig(with_mean, with_std)`, `DistanceMatrixConfig(metric, n_jobs, return_condensed)`, `HierarchicalClusteringConfig(linkage_method, default_threshold)`, `DivisiveClusteringConfig()`, `MultivariateConsensusConfig(min_threshold, max_threshold, threshold_step)`. |

## Integration constraints

- `ParquetDataset` checks the full 3W dataset structure and may download automatically when incomplete. `force_download=True` deletes its target first. Use the notebook's generic loaders for interview files; downloads are never an implicit setup step.
- `constants.DATASET_INI_2_0_0` still uses the upstream layout and points outside `main` after this copy. Supply an explicit dictionary path if needed. Do not assume copied toolkit code includes the data or workshop scripts.
- Avoid `from ThreeWToolkit.core import *`: its `__all__` mentions several mixins that are not imported there. Use explicit symbols. Older `ModelTrainer`, `TrainerConfig`, and preprocessing `Windowing` imports in v2 notebooks do not match this copy.
- Split before fitting cleaning/imputation and before creating overlapping windows. Group repeated events from the same well when the task requires unseen-well evaluation. Per-event normalization/interpolation may use future observations; review this for online prediction.
- The packaged examples emphasize classification. Generic tabular regression/categorical preprocessing is a separate sklearn path in the starter. LSTM workshop code lives in the reference project's `resources/`, not this package.
- Use `ModelRecorder.save_model(model, filename)` and `load_model(filename)` for model wrappers; also retain preprocessing, feature order, and label mapping for inference. Load only trusted serialized artifacts.
- `SklearnTrainer` sets integer `verbose` on wrapped estimators. For sklearn `Pipeline`, call `trainer.model.set_params(verbose=False)` after building: current sklearn requires a boolean. Its training history stores estimator scores, not losses. Toolkit assessment F1 uses weighted averaging; label that separately from binary positive-class F1.
- Preserve upstream code and license; keep exercise adapters separate. Validate edited imports and run a small end-to-end case rather than assuming a successful import proves training works.
