<div align="center">

# spmx


**A BIDS-compliant Python wrapper for SPM neuroimaging analysis via MATLAB.**

[What It Does](#what-it-does) | [Key Features](#key-features) | [Installation](#installation) | [Quick Start](#quick-start) | [Workflows](#workflows) | [Usage Guide](#usage-guide) | [Output Format](#output-format) | [Examples](#examples) | [Troubleshooting](#troubleshooting) | [Technical Documentation](#technical-documentation)

</div>

`spmx` automates fMRI statistical analysis workflows using SPM (Statistical Parametric Mapping). It processes preprocessed BIDS datasets and produces analysis-ready outputs in BIDS derivative format, with complete reproducibility through configuration files.

---

## What It Does

`spmx` is a neuroimaging analysis tool that:

1. **Takes preprocessed fMRI data** (e.g., from fMRIPrep) in BIDS format
2. **Applies SPM statistical models** for fMRI analysis through MATLAB
3. **Produces BIDS-compliant outputs** that are ready for group-level analysis or publication

The tool orchestrates fMRI analysis in four main stages:

- **Fit**: Specify and estimate first-level GLM (General Linear Model)
- **VOI**: Extract BOLD timeseries from seed regions of interest  
- **DCM**: Estimate Dynamical Causal Models for connectivity analysis at participant level
- **PEB**: Perform group-level statistical inference on connectivity parameters across participants

The first three stages are applied at the participant level (once per subject), while PEB performs group-level analysis combining results across all subjects/sessions.

---

## Key Features

- **BIDS-first design**: All inputs/outputs follow BIDS standards
- **Reproducible**: Configuration files document all processing decisions
- **Flexible**: Process one participant or entire datasets
- **Safe**: Input data is never modified (read-only)
- **Complete metadata**: JSON sidecars for all outputs
- **Logging**: Detailed logs of all processing steps for debugging

---

## Installation

### Requirements

- Python ≥ 3.9
- MATLAB (any recent version)
- SPM25 or later installed in MATLAB

### Install from source

```bash
git clone https://gitlab.ulb.be/ln2t/spmx
cd spmx
pip install -e .
```

This installs `spmx` as a command-line tool available in your terminal.

---

## Quick Start

### 1. Prepare Your Data

Ensure you have preprocessed fMRI data in BIDS format. Example structure:

```
/data/derivatives/fmriprep/
├── sub-001/
│   ├── ses-01/
│   │   └── func/
│   │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz
│   │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.json
│   │       └── sub-001_ses-01_task-rest_desc-confounds_timeseries.tsv
│   └── ...
└── sub-002/
```

### 2. Create a Configuration File

```yaml
# config.yaml
matlab_path: /opt/matlab/R2023b/bin/matlab
spm_path: /opt/spm12

fmri:
  fit:
    hpf: 128          # High-pass filter (seconds)
    regressors: [trans_x, trans_y, trans_z, rot_x, rot_y, rot_z]
  voi:
    radius: 8         # VOI sphere radius (mm)
    seeds:
      - {name: "PCC", x: 0, y: -52, z: 18}
  dcm:
    model: "full"     # or "resting-state-full"
```

See [Configuration Guide](docs/configuration.md) for detailed options.

### 3. Run the Pipeline

```bash
# Run all three steps
spmx fmri /data/derivatives/fmriprep /data/derivatives/spm participant \
  --fit --voi --dcm --config config.yaml

# Or run individual steps
spmx fmri /data/derivatives/fmriprep /data/derivatives/spm participant --fit
```

---

## Workflows

### Fit: First-Level GLM

Specifies and estimates a general linear model (GLM) for fMRI data. Loads preprocessed BOLD images, applies confounds, and generates parameter estimates and statistical maps.

### VOI: Extract Region Timeseries

Extracts BOLD timeseries from predefined seed regions of interest (ROIs). Requires prior fit stage. Output VOI files serve as input for connectivity analyses.

### DCM: Dynamical Causal Modeling

Estimates network connectivity models using Dynamical Causal Modeling. Requires prior fit and VOI stages. Supports resting-state data with pre-defined or custom model specifications.

### PEB: Group-Level Parametric Empirical Bayes Analysis

Performs group-level statistical inference on DCM connectivity parameters across participants. Supports:
- Testing main group effects (e.g., "Is there significant connectivity?")
- Testing covariate effects (e.g., "Does connectivity scale with age?")
- Comparing groups (e.g., "Do patients differ from controls?")

**Requirements:** Participant-level DCM analysis (via `--fit --voi --dcm`) completed for all subjects.

**Usage:**
```bash
spmx fmri INPUT OUTPUT group --dcm \
  --participants-file participants.tsv \
  --regressors age group IQ \
  --categorical-regressors group \
  --config config.yaml
```

**Output files:**
- **MATLAB files** (for advanced analysis):
  - `xPEB_[model_name].mat` — Complete results with visualization metadata
  - `PEB_[model_name].mat` — Core PEB statistics (parameter estimates, covariance, probabilities)
  - `GCM_[model_name].mat` — Participant-level DCM structures

- **TSV files** (for spreadsheet analysis, no MATLAB required):
  - `xPEB_[model_name]_parameter_estimates.tsv` — Group connectivity parameters with ROI labels
  - `xPEB_[model_name]_posterior_probabilities.tsv` — Statistical significance of each parameter
  - `xPEB_[model_name]_covariance_matrix.tsv` — Parameter uncertainty matrix

- **JSON file** (structured metadata):
  - `xPEB_[model_name]_metadata.json` — Analysis summary (num parameters, ROIs, etc.)

**Quick start with TSV files (no MATLAB):**
Open `*_posterior_probabilities.tsv` and `*_parameter_estimates.tsv` in Excel or import to Python/R for analysis and visualization.

See [Group-Level DCM Analysis](docs/group_dcm.md) for detailed guide and [SPM User Help](docs/group_dcm.md#spm-reference-accessing-matlab-files) for file structure reference.

---

## Usage Guide

### Basic Command

```bash
spmx fmri INPUT_DIR OUTPUT_DIR participant [--fit] [--voi] [--dcm] [--config FILE]
```

**Common options:**
- `--fit`: Run first-level GLM  
- `--voi`: Extract VOI timeseries (requires `--fit`)
- `--dcm`: Estimate DCM models (requires `--fit` and `--voi`)
- `--config FILE`: Path to YAML configuration file
- `--participant-label LABEL [LABEL...]`: Process specific participants
- `--session SESSION [SESSION...]`: Filter by session
- `--task TASK`: Filter by task name
- `--debug`: Enable debug logging

### Configuration Options

Pass options via YAML config file or command-line arguments. CLI arguments override config file values.

Detailed parameter documentation: [Configuration Guide](docs/configuration.md)

### Example Commands

```bash
# Fit GLM for specific participants
spmx fmri /input /output participant --fit --config config.yaml --participant-label 001 002

# Fit GLM with task conditions and custom events file
spmx fmri /input /output participant --fit \
  --events-file /data/custom_events/task_events.tsv \
  --condition face house --contrast "face - house" \
  --config config.yaml

# Run complete pipeline
spmx fmri /input /output participant --fit --voi --dcm --config config.yaml

# Debug a specific stage
spmx fmri /input /output participant --fit --debug --config config.yaml
```

---

## Output Format

### Directory Structure

```
OUTPUT_DIR/
├── dataset_description.json          # BIDS derivative dataset metadata
├── logs/
│   ├── pipeline.log                  # Main pipeline log
│   └── sub-001/
│       ├── ses-01/
│       │   ├── fit.log               # Fit stage logs
│       │   ├── voi.log               # VOI stage logs
│       │   └── dcm.log               # DCM stage logs
│       └── matlab_scripts/           # Generated MATLAB code (debug mode)
├── sourcedata/                       # Temporary uncompressed NIFTI files
│   └── sub-001/ses-01/func/          # (Can be cleaned with --clean-spm-files)
└── sub-001/
    ├── ses-01/
    │   └── func/
    │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_desc-prefitglm_bold.nii.gz
    │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_desc-prefitglm_bold.json
    │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_desc-prefit_beta_001.nii.gz
    │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_desc-prefit_beta_001.json
    │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_desc-voi-pcc_timeseries.mat
    │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_desc-voi-pcc_timeseries.json
    │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_model-full_dcm.mat
    │       ├── sub-001_ses-01_task-rest_space-MNI152NLin2009cAsym_model-full_dcm.json
    │       └── SPM.mat
    └── ...
```


---

## Examples

Example configuration files and workflows available in [config_examples/](config_examples/) and [docs/](docs/).

**Quick examples:**

```bash
# Fit GLM for multiple participants
spmx fmri /data/derivatives/fmriprep /data/derivatives/spm \
  participant --fit --config config.yaml --participant-label 001 002

# Complete workflow: fit → VOI → DCM
spmx fmri /data/derivatives/fmriprep /data/derivatives/spm \
  participant --fit --voi --dcm --config config.yaml

# Debug a specific run
spmx fmri /data/derivatives/fmriprep /data/derivatives/spm \
  participant --fit --debug --config config.yaml
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **MATLAB not found** | Specify path: `--matlab-path /opt/matlab/R2023b/bin/matlab` or in config file |
| **SPM path not found** | Set path: `--spm-path /opt/spm12` or in config file |
| **No subjects found** | Check input follows BIDS structure (see [docs/configuration.md](docs/configuration.md)) |
| **No confounds found** | Verify confound column names exist in `confounds_timeseries.tsv` |
| **VOI extraction fails** | Ensure fit step completed first before running VOI |
| **Debug info needed** | Enable debug logging: `--debug` flag |

**Debug logs location:**
```
OUTPUT_DIR/logs/pipeline.log              # Main log
OUTPUT_DIR/logs/sub-001/ses-01/*.log    # Stage-specific logs
```

---

## Technical Documentation

Detailed documentation available in [docs/](docs/):

- [Configuration Guide](docs/configuration.md) — Complete parameter reference and examples
- [Output File Mapping](docs/outputs.md) — Output file structure and formats
- [Advanced Topics](docs/advanced_topics.md) — Custom models and expert configurations
- [Group-Level DCM Analysis](docs/group_dcm.md) — PEB group-level inference on connectivity with TSV output
- [Quick Start: TSV Files](docs/group_dcm.md#quick-start-using-tsv-files-no-matlab-required) — Easy analysis without MATLAB
- [SPM Reference](docs/group_dcm.md#spm-reference-accessing-matlab-files) — File structure reference for MATLAB workflows
- [DCM Specification](docs/dcm_specification.md) — DCM models and connectivity matrices
- [MATLAB Templates](docs/matlab_templates.md) — SPM script generation details

---

## License

MIT License

## Authors

See [CONTRIBUTORS.md](CONTRIBUTORS.md)

## Citation

If you use `spmx` in your research, please cite:

```bibtex
@software{spmx2024,
  title={ln2t\_spm: BIDS-compliant SPM Processing Wrapper},
  author={ln2t contributors},
  year={2024},
  url={https://gitlab.ulb.be/ln2t/spmx}
}
```

## Support

- **GitHub Issues:** [Report bugs or request features](https://gitlab.ulb.be/ln2t/spmx/issues)
- **Documentation:** See [docs/](docs/) folder
- **Examples:** See [config_examples/](config_examples/) folder

---

## Related Projects

- [fMRIPrep](https://fmriprep.org/) — Preprocessing pipeline to prepare data for spmx
- [SPM](https://www.fil.ion.ucl.ac.uk/spm/) — Statistical Parametric Mapping
- [BIDS](https://bids-standard.github.io/) — Brain Imaging Data Structure standard
