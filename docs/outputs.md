# Output File Mapping & BIDS Compliance

This document details what files are produced by each pipeline stage and how they are named.

## Fit Stage Outputs

### Model Specification & Estimation

SPM produces the following outputs during model specification and estimation:

| SPM File | Description | BIDS Name | Purpose |
|----------|-------------|-----------|---------|
| `SPM.mat` | Model specification and results | `SPM.mat` | Core SPM file containing all model details |
| `beta_0001.nii` | Beta map for intercept/constant | `*_desc-prefit_beta_001.nii.gz` | Baseline/intercept estimate |
| `beta_000X.nii` | Beta maps for regressors | `*_desc-prefit_beta_00X.nii.gz` | Parameter estimates for conditions/confounds |
| `ResMS.nii` | Residual mean squares | `*_desc-prefit_resms.nii.gz` | Model residuals (variance estimate) |
| `mask.nii` | Brain mask (automatic) | Not renamed | Used for VOI extraction; kept in sourcedata |

### Contrast Maps (if --contrast specified)

| SPM File | Description | BIDS Name | Purpose |
|----------|-------------|-----------|---------|
| `con_000X.nii` | Contrast maps | `*_desc-prefitcon_con_00X.nii.gz` | Statistical maps for condition comparisons |
| `spmT_000X.nii` | T-statistic maps | `*_desc-prefitcon_t_00X.nii.gz` | T-statistics for contrasts |
| `spmF_000X.nii` | F-statistic maps (if multi-contrast) | `*_desc-prefitcon_f_00X.nii.gz` | F-statistics (multiple contrasts) |

### Reports

| SPM File | Description | BIDS Name | Purpose |
|----------|-------------|-----------|---------|
| `*.pdf` | Statistical report | `*_desc-prefit_report.pdf` | Summary of model results |
| `*.csv` | Results table | `*_desc-prefit_results.csv` | Tabular results for spreadsheet import |

## VOI Stage Outputs

### Volume of Interest Files

VOI extraction produces `.mat` files from SPM, which are renamed and accompanied by JSON sidecars:

| SPM File | Description | BIDS Name | Purpose |
|----------|-------------|-----------|---------|
| `VOI_SEEDNAME_1.mat` | VOI timeseries | `*_desc-voi-seedname_timeseries.mat` | BOLD signal averaged in ROI; input for DCM |

Example:
```
VOI_PCC_1.mat → sub-001_ses-01_task-rest_space-MNI_desc-voi-pcc_timeseries.mat
VOI_mPFC_1.mat → sub-001_ses-01_task-rest_space-MNI_desc-voi-mpfc_timeseries.mat
```

## Group / PEB Stage Outputs

Group-level analysis uses SPM's Parametric Empirical Bayes (PEB) to estimate
connectivity parameters at the population level.

### MATLAB Files

| File | SPM Origin | Description |
|------|-----------|-------------|
| `xPEB_[model].mat` | `spm_dcm_peb` | Full PEB results structure (`xPEB`) |
| `PEB_[model].mat` | extracted | Core PEB model only (`xPEB.PEB`) |
| `GCM_[model].mat` | extracted | All participant DCMs (`xPEB.DCM`) |

### TSV Files (no MATLAB required)

All TSV files use the **same row ordering**: DCM A-matrix parameters in
SPM column-major order — source region cycles slowly, target cycles fast
(e.g. for ROIs `[mPFC, LIPL, RIPL, PCC]`: mPFC→mPFC, mPFC→LIPL, …, PCC→PCC).

| File | SPM variable | Shape | Description |
|------|-------------|-------|-------------|
| `xPEB_[model]_parameter_estimates.tsv` | `PEB.Ep` | Np × K | Posterior mean of group-level parameters; rows = DCM params, columns = covariates |
| `xPEB_[model]_posterior_probabilities.tsv` | `PEB.Pp` | Np × K | P(param ≠ 0) = Φ(\|Ep\| / √diag(Cp)); threshold Pp > 0.95 ≈ p < 0.05 |
| `xPEB_[model]_covariance_matrix.tsv` | `PEB.Cp` | (Np×K)² | Posterior covariance of group-level estimates; diagonal = estimation variance of group mean |
| `xPEB_[model]_random_effects_variance.tsv` | `PEB.Ce` | Np × Np | Between-subject random-effects covariance; diagonal = population variance per parameter |
| `xPEB_[model]_precision_component_NNN.tsv` | `PEB.M.Q{k}` | Np × Np | k-th covariance basis matrix; `Ce = Σ exp(Eh_k) × Q_k` (one file per component) |
| `xPEB_[model]_group_effects.tsv` | `PEB.Eh` | 1-D | Log-precision weights for covariance components |
| `xPEB_[model]_metadata.json` | — | — | Analysis dimensions, variable mapping, ROI list |

where **Np** = number of DCM parameters, **K** = number of design-matrix columns
(covariates), **NNN** = zero-padded component index.

#### The precision basis matrices (`PEB.M.Q`)

In SPM's PEB the between-subject covariance is parameterised as a weighted sum:

$$C_e = \sum_k \exp(h_k) \cdot Q_k$$

- `Q_k` (`precision_component_NNN.tsv`) defines **which parameters can co-vary**
  and the relative scale between them — the structural shape of between-subject
  variability.  Rows and columns index the same Np DCM parameters.
- `Eh_k` (`group_effects.tsv`) controls **how much** each basis contributes
  (estimated log-precision weight).
- `Ce` (`random_effects_variance.tsv`) is the resulting covariance, combining all
  components according to the equation above.

In default SPM PEB, `M.Q` contains **one** component: an identity-like matrix
(equal and uncorrelated prior variance for every parameter).  Additional components
are added when specific covariance structure is imposed (e.g. block-diagonal priors).

**Quality checks:**
- `exp(Eh_k) ≈ 0` → that component was suppressed; between-subject variability for
  its parameters was not supported by the data
- `diag(Ce) >> diag(Cp)` for a parameter → subjects vary a lot but the group mean
  is still well-estimated
- `diag(Ce) ≈ diag(Cp)` → estimation uncertainty dominates; more subjects needed

### Example Group Output Structure

```
OUTPUT_DIR/group/SPM/
├── xPEB_full.mat
├── PEB_full.mat
├── GCM_full.mat
├── xPEB_full_parameter_estimates.tsv
├── xPEB_full_posterior_probabilities.tsv
├── xPEB_full_covariance_matrix.tsv
├── xPEB_full_random_effects_variance.tsv
├── xPEB_full_precision_component_001.tsv
├── xPEB_full_group_effects.tsv
└── xPEB_full_metadata.json
```

---

## DCM Stage Outputs

### Estimated DCM Models

| SPM File | Description | BIDS Name | Purpose |
|----------|-------------|-----------|---------|
| `DCM_MODELNAME.mat` | Estimated DCM model | `*_model-MODELNAME_dcm.mat` | Connectivity parameters and fit statistics |

Example:
```
DCM_full.mat → sub-001_ses-01_task-rest_space-MNI_model-full_dcm.mat
DCM_full_nested.mat → sub-001_ses-01_task-rest_space-MNI_model-full_nested_dcm.mat
```

## JSON Sidecars

Every data file (`.nii.gz`, `.mat`) has an accompanying `.json` sidecar file with metadata.

### Fit Beta Maps Sidecar

```json
{
  "RepetitionTime": 2.0,
  "EchoTime": 0.035,
  "ProcessingType": "fit",
  "SPMVersion": "12.7890",
  "BetaIndex": 1,
  "BetaName": "condition_face",
  "Description": "Parameter estimate for face condition; beta_0001 from SPM"
}
```

### Contrast Maps Sidecar

```json
{
  "RepetitionTime": 2.0,
  "EchoTime": 0.035,
  "ProcessingType": "fit",
  "ContrastIndex": 1,
  "ContrastName": "face - house",
  "ContrastDefinition": "[1 -1 0 0 ... 0]",
  "ContrastType": "T",
  "Description": "T-statistic map for contrast 'face - house'"
}
```

### VOI Timeseries Sidecar

```json
{
  "ProcessingType": "voi",
  "ROIMask": "sphere ∩ brain_mask",
  "ROIName": "PCC",
  "ROICenterXYZ": [0, -52, 18],
  "ROIRadiusMM": 5.0,
  "Template": "MNI152NLin2009cAsym",
  "Description": "BOLD timeseries from Posterior Cingulate Cortex (PCC)"
}
```

### DCM Model Sidecar

```json
{
  "ProcessingType": "dcm",
  "ModelName": "full",
  "NumROIs": 4,
  "ROINames": ["PCC", "mPFC", "LIPL", "RIPL"],
  "DataType": "CSD",
  "Description": "Estimated DCM model with all A-matrix connections"
}
```

## Example Output Directory Structure

```
OUTPUT_DIR/
├── dataset_description.json
├── logs/
│   ├── pipeline.log
│   └── sub-001/
│       └── ses-01/
│           ├── fit.log
│           ├── voi.log
│           ├── dcm.log
│           └── matlab_scripts/
│               ├── 01_fmri_spec.m
│               ├── 02_fmri_est.m
│               ├── 03_con.m
│               ├── 04_voi_pcc.m
│               └── 05_dcm_full.m
├── sourcedata/
│   └── sub-001/
│       └── ses-01/
│           └── func/
│               ├── sub-001_ses-01_task-rest_space-MNI_desc-preproc_bold.nii
│               └── mask.nii
└── sub-001/
    └── ses-01/
        └── func/
            ├── SPM.mat
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_bold.nii.gz
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_bold.json
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_beta_001.nii.gz
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_beta_001.json
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_beta_002.nii.gz
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_beta_002.json
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_resms.nii.gz
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_resms.json
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefitcon_con_001.nii.gz
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefitcon_con_001.json
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefitcon_t_001.nii.gz
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefitcon_t_001.json
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_report.pdf
            ├── sub-001_ses-01_task-rest_space-MNI_desc-prefit_results.csv
            ├── sub-001_ses-01_task-rest_space-MNI_desc-voi-pcc_timeseries.mat
            ├── sub-001_ses-01_task-rest_space-MNI_desc-voi-pcc_timeseries.json
            ├── sub-001_ses-01_task-rest_space-MNI_desc-voi-mpfc_timeseries.mat
            ├── sub-001_ses-01_task-rest_space-MNI_desc-voi-mpfc_timeseries.json
            ├── sub-001_ses-01_task-rest_space-MNI_model-full_dcm.mat
            └── sub-001_ses-01_task-rest_space-MNI_model-full_dcm.json
```

## dataset_description.json

Created automatically when pipeline starts in the output directory. Identifies the output folder as a valid BIDS derivative dataset:

```json
{
  "Name": "spmx fmri",
  "BIDSVersion": "1.9.0",
  "DatasetType": "derivatives",
  "GeneratedBy": [
    {
      "Name": "spmx",
      "Version": "0.1.0",
      "CodeURL": "https://gitlab.ulb.be/ln2t/spmx",
      "Description": "First-level fMRI GLM fitting with VOI and DCM"
    }
  ],
  "License": "CC0",
  "Authors": [
    {
      "Name": "spmx Contributors"
    }
  ]
}
```

## File Format Details

### NIFTI Compression

- **Input format**: `.nii.gz` (gzip compressed)
- **Output format**: `.nii.gz` (gzip compressed, BIDS standard)
- **SPM temporary**: `.nii` (uncompressed, in sourcedata folder)

### VOI and DCM Files

- **Format**: MATLAB `.mat` files
- **Structure**: Saved SPM structures (VOI, DCM)
- **Compatibility**: Can be opened in MATLAB or Python (scipy.io.loadmat)

### SPM.mat

- **Format**: MATLAB `.mat` file
- **Contains**: Complete model specification, design matrix, parameter estimates
- **Purpose**: Required for subsequent VOI and DCM stages
- **Keep**: Essential for reproducibility; do not delete

## Using Output Files

### Load VOI Timeseries in MATLAB

```matlab
voi_file = 'sub-001_ses-01_task-rest_space-MNI_desc-voi-pcc_timeseries.mat';
load(voi_file);
timeseries = VOI.u;  % Extract timeseries
```

### Load VOI Timeseries in Python

```python
import scipy.io
import json

# Load MATLAB file
voi_file = 'sub-001_ses-01_task-rest_space-MNI_desc-voi-pcc_timeseries.mat'
voi_data = scipy.io.loadmat(voi_file)
timeseries = voi_data['VOI'][0][0]['u']

# Load metadata
with open(voi_file.replace('.mat', '.json')) as f:
    metadata = json.load(f)
    roi_name = metadata['ROIName']
```

### Load DCM Model Results

```python
import scipy.io

dcm_file = 'sub-001_ses-01_task-rest_space-MNI_model-full_dcm.mat'
dcm_data = scipy.io.loadmat(dcm_file)

# Access DCM parameters
A_matrix = dcm_data['DCM'][0][0]['Ep'][0][0]['A']  # Endogenous connections
B_matrix = dcm_data['DCM'][0][0]['Ep'][0][0]['B']  # Bilinear modulations
```

### Load Beta Maps

```python
import nibabel as nib

beta_file = 'sub-001_ses-01_task-rest_space-MNI_desc-prefit_beta_001.nii.gz'
img = nib.load(beta_file)
data = img.get_fdata()
affine = img.affine
```

## BIDS Validation

Validate outputs against BIDS standard:

```bash
bids-validator /data/derivatives/spm/
```

The validator checks for:
- Proper naming conventions
- Required JSON sidecars
- Valid metadata fields
- dataset_description.json presence
