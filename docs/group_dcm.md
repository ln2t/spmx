# Group-Level DCM Analysis (PEB)

## Overview

Group-level DCM analysis in spmx uses SPM's Parametric Empirical Bayes (PEB) method to characterize group-level effects and covariates on Dynamic Causal Models. This allows you to:

- Test group-level effects on connectivity parameters
- Examine relationships between connectivity and participant covariates (age, clinical scores, etc.)
- Implement categorical group comparisons (patient vs. control)
- Account for continuous variables (age, IQ) in connectivity models

## Prerequisites

1. **Participant-level DCM analysis must be completed first**
   - Run `--fit` to estimate subject-level GLM models
   - Run `--voi` to extract VOI timeseries from seed regions
   - Run `--dcm` to estimate participant-level DCM models

2. **Participants file** (typically `participants.tsv` from your BIDS dataset)
   - Must contain `participant_id` column
   - May contain additional columns for covariates: age, sex, group, IQ, etc.
   - Tab-separated values format

## Quick Start

### 1. Run Participant-Level Analysis

```bash
spmx fmri /data/fmriprep /data/derivatives participant \
    --fit --voi --dcm \
    --model resting-state-full \
    --config config_examples/group_dcm_example.yaml
```

### 2. Run Group-Level DCM Analysis

```bash
spmx fmri /data/fmriprep /data/derivatives group \
    --dcm \
    --model resting-state-full \
    --participants-file /data/participants.tsv \
    --regressors age group IQ \
    --categorical-regressors group \
    --group-name PEB_analysis \
    --config config_examples/group_dcm_example.yaml
```

## Command-Line Options

### Required Arguments
- `analysis_level`: Must be `group` for group-level analysis
- `--dcm`: Must be specified (group analysis only works with DCM currently)
- `--model`: DCM model name(s) used in participant-level analysis (e.g., `resting-state-full`)
  - Can be specified via CLI argument (`--model resting-state-full`) or in config file (`fmri.dcm.model`)
  - CLI argument takes precedence if both are specified
- `--participants-file PATH`: Path to participants.tsv file

### Optional Arguments
- `--regressors COL [COL ...]`: Column names from participants file to use as covariates
  - Example: `--regressors age group IQ`
  - If not specified: interprets model for all subjects (no covariates)

- `--categorical-regressors COL [COL ...]`: Which regressors are categorical (uses dummy coding)
  - Example: `--categorical-regressors group sex`
  - Default: all regressors treated as continuous
  - Categorical variables use reference-coded dummy variables (first level is reference)

- `--group-name NAME`: Name for the group analysis output
  - Default: `PEB_analysis`
  - Used for output directory and MATLAB variable names

## Configuration File

The `group_dcm_example.yaml` file provides templates for:
- DCM model name (can optionally be specified here instead of --model CLI flag)
- VOI seed specifications
- DCM model options (estimation parameters)
- Analysis type (CSD for resting-state, timeseries for task)

Example:
```yaml
fmri:
  voi:
    seeds:
      - name: PCC
        coord: [0, -52, 26]
      - name: mPFC
        coord: [0, 52, -2]
      - name: LIPL
        coord: [-42, -58, 52]
  
  dcm:
    model: resting-state-full      # Optional: can also use --model CLI argument
    seeds: [PCC, mPFC, LIPL]
    analysis: csd  # 'csd' for resting-state, 'timeseries' for task
```

Note: If `model` is specified both in the config file and via `--model` CLI argument, the CLI argument takes precedence.

## Participants File Format

The participants.tsv file should have this structure:

```
participant_id    age    sex    group    IQ
sub-001           25     M      control  112
sub-002           28     F      patient  108
sub-003           26     M      control  115
sub-004           31     F      patient  105
```

Requirements:
- **participant_id**: Must match subject directories (e.g., sub-001, sub-002)
  - **Validation**: All subjects with DCM files MUST be listed in this file
  - **Note**: Not all participants in the file need to have DCM files (only those with DCM will be included in analysis)
- **Other columns**: Can have any name; use --regressors to specify which to include
- **Missing values**: Represented as NaN; continuous variables will use mean imputation
- **Format**: Tab-separated values (.tsv)

## Regressors

### Continuous Regressors

Continuous variables (age, IQ, etc.) are mean-centered and included directly in the design matrix.

```bash
--regressors age IQ education_years
```

If any values are missing (NaN), they are imputed with the column mean.

### Categorical Regressors

Categorical variables (group, sex, etc.) are dummy-coded using the first level as reference.

```bash
--categorical-regressors group sex
```

Example with group variable {control, patient, other}:
- Column 1: Intercept
- Column 2: 1 if patient, 0 otherwise → group_patient
- Column 3: 1 if other, 0 otherwise → group_other

The reference level (control) is implicit in the intercept.

## Output

Group-level analysis creates MATLAB .mat files and TSV text files:

### MATLAB Files (for advanced analysis)

```
OUTPUT_DIR/group/SPM/
├── xPEB_[model_name].mat           # Main PEB results structure (full xPEB)
├── PEB_[model_name].mat            # PEB structure only (extracted from xPEB.PEB)
├── GCM_[model_name].mat            # Group DCM structure (participant DCMs in xPEB.DCM)
├── peb_[model_name].log            # Processing log with detailed logging
└── peb_[model_name].m              # MATLAB script (for debugging)
```

### TSV Files (human-readable, no MATLAB required)

```
OUTPUT_DIR/group/SPM/
├── xPEB_[model_name]_parameter_estimates.tsv       # PEB.Ep  — group-level parameter estimates (Np × nc)
├── xPEB_[model_name]_posterior_probabilities.tsv   # PEB.Pp  — P(param ≠ 0) (Np × nc)
├── xPEB_[model_name]_covariance_matrix.tsv         # PEB.Cp  — estimation covariance ((Np×nc) × (Np×nc))
├── xPEB_[model_name]_random_effects_variance.tsv   # PEB.Ce  — between-subject variance (Np × Np)
├── xPEB_[model_name]_precision_component_001.tsv   # PEB.M.Q{1}  — 1st covariance basis matrix (Np × Np)
├── xPEB_[model_name]_precision_component_002.tsv   # PEB.M.Q{2}  — 2nd covariance basis matrix (optional)
├── xPEB_[model_name]_group_effects.tsv             # PEB.Eh  — log-precision hyperparameter weights (1-D)
└── xPEB_[model_name]_metadata.json                 # Summary of analysis dimensions and variable mapping
```

### Output File Contents

#### MATLAB Files

The `xPEB_[model_name].mat` file contains the complete `xPEB` structure:
- **xPEB.Pp**: Posterior probabilities for group-level parameters
- **xPEB.PEB**: Main PEB structure (also saved separately as PEB_[model_name].mat)
- **xPEB.DCM**: Participant-level DCM structures (also saved separately as GCM_[model_name].mat)
- Additional fields for GUI visualization and results review

#### TSV Files (For spreadsheet analysis, no MATLAB needed)

All TSV files use a **matrix layout**: rows are DCM parameters, columns are design-matrix
covariates (one column per regressor).  This mirrors the display in `spm_dcm_peb_review`.

---

##### Parameter label convention

Each row label identifies a directed connection in `source→target` notation, where
`source` is the region driving `target`.

In SPM's DCM the A-matrix entry `A(i,j)` encodes the influence of region **j** (source,
column) on region **i** (target, row).  Parameters are vectorised by SPM in **MATLAB
column-major order**, so the source index cycles *slowly* and the target index cycles
*fast*:

| DCM A index | SPM A(i,j) | Label      |
|-------------|-----------|------------|
| 1           | A(1,1)    | mPFC→mPFC  |
| 2           | A(2,1)    | mPFC→LIPL  |
| 3           | A(3,1)    | mPFC→RIPL  |
| 4           | A(4,1)    | mPFC→PCC   |
| 5           | A(1,2)    | LIPL→mPFC  |
| …           | …         | …          |
| 15          | A(3,4)    | PCC→RIPL   |
| 16          | A(4,4)    | PCC→PCC    |

> **Important:** ROI names are taken in the **original order as entered when defining
> the first-level DCMs** — SPM does not sort them alphabetically.

For PEB with *Np* DCM parameters and *K* design-matrix columns (covariates), the flat
PEB vector of length *Np*×*K* is structured as:

* Indices 1 … *Np*   → all DCM params for covariate 1 (e.g. Commonalities)
* Indices *Np*+1 … 2*Np* → all DCM params for covariate 2 (e.g. group_patient)
* …

The TSV matrix re-assembles this: **rows** = DCM parameters (in A-matrix column-major
order), **columns** = covariates.

---

**parameter_estimates.tsv** — `PEB.Ep`: group-level parameter estimates (Np × K matrix)

```
parameter    Commonalities   group_patient
mPFC→mPFC    0.500           0.145
mPFC→LIPL    0.342          -0.088
mPFC→RIPL    0.189           0.032
mPFC→PCC     0.128          -0.201
LIPL→mPFC    0.098           0.065
...
PCC→PCC      0.445           0.112
```

- **SPM variable:** `xPEB.PEB.Ep`
- Rows: DCM A-matrix parameters in SPM's column-major order (source cycles slowly,
  target cycles fast)
- Columns: one per design-matrix covariate (names from `PEB.Xnames`)
- Values: posterior expected values of the group-level parameters
- **Quality check:** large absolute values (>> 1 Hz) may indicate a poor model fit or
  outlier subjects

**posterior_probabilities.tsv** — `PEB.Pp`: posterior probability that each parameter ≠ 0 (Np × K matrix)

```
parameter    Commonalities   group_patient
mPFC→mPFC    0.98            0.72
mPFC→LIPL    0.88            0.31
mPFC→RIPL    0.64            0.55
...
PCC→PCC      0.95            0.41
```

- **SPM variable:** `xPEB.Pp` (stored per-effect; computed as `Pp = Φ(|Ep| / √diag(Cp))`)
- Same row/column structure as `parameter_estimates.tsv`
- Values: posterior probability that the parameter is non-zero (range 0–1)
- **Threshold:** `Pp > 0.95` is the conventional criterion (approximately p < 0.05 two-tailed)
- **Quality check:** if all probabilities cluster near 0.5 the model may be unidentifiable

**covariance_matrix.tsv** — `PEB.Cp`: posterior covariance of group-level estimates ((Np×K) × (Np×K) square matrix)

Row and column labels encode both the covariate and the DCM parameter, e.g.
`Commonalities_mPFC→LIPL`.

- **SPM variable:** `xPEB.PEB.Cp`
- **What it represents:** estimation *uncertainty* of the group-level mean `Ep` — NOT
  between-subject variability (that is `Ce`, see below)
- Diagonal `Cp(k,k)`: variance of the group mean for parameter `k`; `√Cp(k,k)` is the
  posterior standard deviation used to compute `Pp`
- Off-diagonal: posterior covariance between pairs of group-level parameters
- **Quality check:** very large diagonal values indicate poorly constrained estimates;
  strong off-diagonal correlations signal parameter redundancy

**random_effects_variance.tsv** — `PEB.Ce`: between-subject random-effects variance (Np × Np symmetric matrix)

```
parameter    mPFC→mPFC   mPFC→LIPL   ...   PCC→PCC
mPFC→mPFC    0.0412      0.0021      ...   0.0008
mPFC→LIPL    0.0021      0.0289      ...   0.0003
...
PCC→PCC      0.0008      0.0003      ...   0.0334
```

- **SPM variable:** `xPEB.PEB.Ce`
- **What it represents:** how much individual subjects deviate from the group mean for
  each DCM parameter — the *between-subject variance*, not the estimation uncertainty
- Rows and columns both correspond to the Np DCM parameters (same order as
  `parameter_estimates.tsv` rows); the matrix is symmetric
- Diagonal `Ce(k,k)`: variance of the population distribution for parameter `k`; its
  square root is the between-subject standard deviation
- Off-diagonal: covariance of individual differences between pairs of parameters
- **Quality check:**
  - `Ce` >> `Cp` (diagonal) for a parameter → most variability is between subjects,
    not estimation noise; the group mean `Ep` is well-estimated but subjects differ a lot
  - `Ce` ≈ 0 for a parameter → little between-subject variability; the PEB intercept
    essentially captures all subjects equally
  - Compare to `Cp` (from `covariance_matrix.tsv`) to assess signal-to-noise at the
    group level

**group_effects.tsv** — `PEB.Eh`/`PEB.Eg`: log-precision hyperparameter weights (1-D vector)

```
component   group_effect
0           0.342
1           0.215
...
```

- **SPM variable:** `xPEB.PEB.Eh` (called `Eg` in some SPM versions; the code tries both)
- **What it represents:** the posterior expectation of the log-precision weights `h`
  that scale the between-subject covariance components `Q_i` in the model
  `Ce = Σ_i exp(h_i) Q_i`
- One entry per covariance component (not per DCM parameter)
- **Quality check:** very negative values (exp(h) ≈ 0) indicate that a covariance
  component was effectively switched off by the estimation — the corresponding
  between-subject variability was not supported by the data

**precision_component_NNN.tsv** — `PEB.M.Q{k}`: k-th covariance basis matrix (Np × Np)

One file per component, zero-padded index (e.g. `_precision_component_001.tsv`,
`_precision_component_002.tsv`, …).  In default SPM PEB there is typically one
component.

```
parameter    mPFC→mPFC   mPFC→LIPL   ...   PCC→PCC
mPFC→mPFC    1.0         0.0         ...   0.0
mPFC→LIPL    0.0         1.0         ...   0.0
...
PCC→PCC      0.0         0.0         ...   1.0
```

- **SPM variable:** `xPEB.PEB.M.Q{k}` (cell array element)
- **What it represents:** the *k*-th structural basis matrix for between-subject
  random effects.  Sometimes called a **precision component** because it enters as a
  basis set in the ReML precision estimation inside `spm_PEB.m`.
- The full between-subject covariance is the weighted sum:
  `Ce = Σ_k exp(Eh_k) × Q_k`
  so Q defines **which parameters can co-vary** and `Eh` controls **how much**.
- Rows and columns correspond to DCM parameters (same order as `parameter_estimates.tsv`);
  the matrix is symmetric.
- In default SPM PEB, `Q{1}` is an identity-like matrix (equal prior variance for all
  parameters); additional components can introduce parameter-specific or
  block-structured covariation.
- **Quality check:**
  - If `Q{k}` ≈ identity and `exp(Eh_k)` is small → uniform but weak between-subject
    variance; parameters are tightly grouped around the group mean
  - If `Ce` (from `random_effects_variance.tsv`) differs substantially from
    `exp(Eh_1) × Q{1}`, additional components are contributing — check all component
    files

**metadata.json** — Summary information (JSON)

```json
{
  "num_parameters": 16,
  "num_covariates": 2,
  "num_rois": 4,
  "roi_list": ["mPFC", "LIPL", "RIPL", "PCC"],
  "covariate_names": ["Commonalities", "group_patient"],
  "parameter_names": ["mPFC→mPFC", "mPFC→LIPL", ...],
  "outputs": {
    "parameter_estimates":     "PEB.Ep  — posterior mean of group-level parameters (np × nc)",
    "posterior_probabilities": "PEB.Pp  — P(param ≠ 0) = Φ(|Ep|/√diag(Cp))  (np × nc)",
    "covariance_matrix":       "PEB.Cp  — posterior covariance of group-level estimates ((np×nc) × (np×nc))",
    "random_effects_variance": "PEB.Ce  — between-subject random-effects variance (np × np)",
    "group_effects":           "PEB.Eh/Eg  — log-precision hyperparameter weights (1-D)"
  }
}
```

---

## Quick Start: Using TSV Files (No MATLAB Required)

If you don't have MATLAB access, the **TSV files** provide all essential results in spreadsheet-friendly format.

Both `parameter_estimates.tsv` and `posterior_probabilities.tsv` are **matrices**:
the `parameter` column is the row index, and each additional column is one covariate.

### Loading TSV Files

**Python:**
```python
import pandas as pd

# Both files: rows = DCM parameters, columns = covariates
params = pd.read_csv('xPEB_[model_name]_parameter_estimates.tsv', sep='\t', index_col='parameter')
pp     = pd.read_csv('xPEB_[model_name]_posterior_probabilities.tsv', sep='\t', index_col='parameter')

print(params)
# parameter      Commonalities  group_patient
# mPFC→mPFC          0.500          0.145
# mPFC→LIPL          0.342         -0.088
# ...

# Find parameters significant for the intercept (Commonalities)
sig = pp[pp['Commonalities'] > 0.95]
print(f"Significant (intercept): {sig.index.tolist()}")
```

**R:**
```r
# Both files: rows = DCM parameters, columns = covariates
params <- read.delim('xPEB_[model_name]_parameter_estimates.tsv', row.names = 1)
pp     <- read.delim('xPEB_[model_name]_posterior_probabilities.tsv', row.names = 1)

head(params)
#            Commonalities group_patient
# mPFC.mPFC         0.500         0.145
# mPFC.LIPL         0.342        -0.088

# Significant connections for Commonalities covariate
sig <- rownames(pp)[pp$Commonalities > 0.95]
print(sig)
```

**Spreadsheet (Excel/Google Sheets):**
1. Open file directly — first column is the parameter label, remaining columns are covariates.
2. Apply conditional formatting to the probability columns (highlight > 0.95).
3. No special software needed!

### Common TSV-Based Analyses

**Identify significant connectivity (all covariates):**
```python
pp = pd.read_csv('xPEB_[model_name]_posterior_probabilities.tsv', sep='\t', index_col='parameter')
# Any covariate exceeding threshold
sig_mask = (pp > 0.95).any(axis=1)
print(f"Parameters significant in ≥1 covariate: {pp.index[sig_mask].tolist()}")
```

**Create publication table:**
```python
params = pd.read_csv('xPEB_[model_name]_parameter_estimates.tsv', sep='\t', index_col='parameter')
pp     = pd.read_csv('xPEB_[model_name]_posterior_probabilities.tsv', sep='\t', index_col='parameter')

# Stack to long format for a combined table
ep_long = params.stack().rename('estimate')
pp_long = pp.stack().rename('posterior_probability')
result  = pd.concat([ep_long, pp_long], axis=1).reset_index()
result.columns = ['parameter', 'covariate', 'estimate', 'posterior_probability']
result['p_approx'] = 1 - result['posterior_probability']
result.to_csv('results_table.csv', index=False)
print(result)
```

**Plot parameter estimates for one covariate:**
```python
import matplotlib.pyplot as plt

params = pd.read_csv('xPEB_[model_name]_parameter_estimates.tsv', sep='\t', index_col='parameter')
pp     = pd.read_csv('xPEB_[model_name]_posterior_probabilities.tsv', sep='\t', index_col='parameter')

cov = 'Commonalities'  # choose a column
colors = ['crimson' if p > 0.95 else 'steelblue' for p in pp[cov]]
fig, ax = plt.subplots(figsize=(12, 6))
ax.barh(params.index, params[cov], color=colors)
ax.set_xlabel('Parameter Estimate')
ax.set_title(f'Group-Level Connectivity — {cov}')
plt.tight_layout()
plt.savefig('connectivity_estimates.png', dpi=300)
```

---

## SPM Reference: Accessing MATLAB Files

### xPEB.mat - Complete Results Structure

**What it is:** Master results file containing all group-level analysis output plus metadata.

**MATLAB structure:**
```matlab
load('xPEB_[model_name].mat')  % Loads variable: xPEB

% Access main results:
xPEB.PEB                % PEB model structure (see below)
xPEB.Pp                 % Posterior probabilities (Np×1 vector)
xPEB.DCM                % Cell array of participant DCMs {Np,1}
xPEB.corr               % Parameter correlation matrix (Np×Np)

% Access metadata:
xPEB.region_names       % VOI region labels (cell array)
xPEB.input_names        % Input/task names (cell array)
```

**SPM Reference:** This structure is created and used by SPM's `spm_dcm_peb` function during PEB estimation. The xPEB structure is SPM's standard container for group-level DCM results with visualization support.

**When to use:** Load this file when you need the complete analysis results, including correlation matrices and metadata for visualization, or when you want to review results in SPM's DCM review GUI.

---

### PEB.mat - Parametric Empirical Bayes Structure

**What it is:** The core PEB model estimation results, extracted from xPEB.PEB.

**MATLAB structure:**
```matlab
load('PEB_[model_name].mat')   % Loads variable: PEB

% Main results:
PEB.Ep                  % Group-level parameter estimates (Np×Nc matrix)
                        %   - Rows: DCM parameters
                        %   - Cols: Design matrix columns (intercept + regressors)
PEB.Cp                  % Parameter covariance matrix (Np×Np×Nc tensor)
                        %   - Posterior covariance at each design level
PEB.Pp                  % Posterior probabilities (Np×1 vector)
                        %   - Probability that parameter > 0
                        %   - Computed as: Pp = 1 - spm_Ncdf(0, abs(Ep), diag(Cp))

% Design matrix:
PEB.M.X                 % Group-level design matrix (Ns×Nc)
                        %   - Rows: Subjects
                        %   - Cols: Covariates (intercept + regressors)
PEB.Xnames              % Column labels for design matrix
PEB.Pnames              % Parameter names (Np×1 cell array)
                        %   - Format: 'A(i,j)', 'B(i,j,k)', 'C(i,j)', etc.

% Variance components:
PEB.Ce                  % Between-subject random-effects variance (Np×Np)
                        %   → random_effects_variance.tsv
                        %   - Diagonal: population variance for each DCM parameter
                        %   - Off-diagonal: covariance of individual differences
                        %   - Compare with diag(Cp) to assess group-level SNR
PEB.Eh                  % Log-precision hyperparameter weights (posterior expectation)
                        %   → group_effects.tsv
                        %   - Scales the between-subject covariance components Q_i
                        %   - Ce = Σ_i exp(Eh_i) * Q_i
PEB.Ch                  % Covariance of precision hyperparameters
PEB.M.Q                 % Cell array of covariance basis matrices {Q_1, ..., Q_k} (each Np×Np)
                        %   → precision_component_NNN.tsv (one file per component)
                        %   - Defines the structural shape of between-subject covariance
                        %   - Ce = Σ_k exp(Eh_k) * Q_k
                        %   - Default SPM PEB: Q{1} is identity-like (uniform variance)
                        %   - Sometimes called 'precision components' (basis of ReML prior)

% Estimation info:
PEB.H                   % Design matrix for precision estimation
PEB.K                   % Partition matrix (for BMA, if applicable)
```

**SPM Reference:** PEB structure is the output of `spm_dcm_peb.m` and is the standard PEB format in SPM. All statistical inference is based on this structure.

**When to use:** Load this file when you need to perform your own statistical analyses, extract specific parameters, or further post-hoc analyses. This is the minimal file needed for parameter extraction and hypothesis testing.

---

### GCM.mat - Group DCM Structure

**What it is:** Collection of participant-level DCM structures, organized as a cell array.

**MATLAB structure:**
```matlab
load('GCM_[model_name].mat')   % Loads variable: GCM

% GCM structure:
GCM                     % {Ns,1} cell array of DCM structures
                        %   - GCM{1} = DCM for subject 1
                        %   - GCM{2} = DCM for subject 2, etc.

% Each GCM{n} contains:
GCM{n}.M.pE             % Prior parameter estimates (structure)
GCM{n}.M.pC             % Prior parameter covariance (sparse matrix)
GCM{n}.Ep               % Posterior parameter estimates (structure)
GCM{n}.Cp               % Posterior parameter covariance (sparse matrix)
GCM{n}.Pp               % Posterior probabilities (vector)

GCM{n}.xY               % BOLD timeseries data
GCM{n}.xY(i).name       % Name of i-th region
GCM{n}.xY(i).u          % Timeseries data vector

GCM{n}.U                % Input matrix (for task-based DCM)
GCM{n}.Y                % Data structure
GCM{n}.Y.name           % Dataset name/label

% Connectivity matrices (in structure form):
GCM{n}.Ep.A             % Intrinsic connectivity matrix (Nr×Nr)
GCM{n}.Ep.B             % Modulatory connectivity (Nr×Nr×Nmod)
GCM{n}.Ep.C             % Driving input connectivity (Nr×Ninput)

GCM{n}.Cp               % Covariance of parameters (sparse, Nr²×Nr²)
```

**SPM Reference:** This is a standard GCM (Group Connectivity Modeling) structure used by SPM's batch DCM functions. Each element is a normal DCM structure as produced by `spm_dcm_estimate.m`.

**When to use:** Load this file to access participant-level DCM results (e.g., individual connectivity parameters), perform sub-group comparisons, or extract data for external modeling.

---

### Loading and Analyzing Results

**Load all three files:**
```matlab
% Complete analysis
load('xPEB_[model_name].mat');   % Get xPEB (all results + metadata)
load('PEB_[model_name].mat');    % Get PEB (core statistics)
load('GCM_[model_name].mat');    % Get GCM (participant DCMs)

% Now all three variables are in workspace
```

**Extract group-level parameter estimates:**
```matlab
% Get posterior means for first regressor (intercept):
param_means = PEB.Ep(:, 1);

% Get posterior variance:
param_var = diag(PEB.Cp(:,:,1));

% Get posterior probabilities (already computed):
param_pp = PEB.Pp;  % Or xPEB.Pp
```

**Find significant parameters (at threshold Pp > 0.95):**
```matlab
threshold = 0.95;
sig_params = find(PEB.Pp > threshold);
for i = sig_params'
    fprintf('Parameter %d (%s): Ep=%.4f, Pp=%.4f\n', ...
        i, PEB.Pnames{i}, PEB.Ep(i,1), PEB.Pp(i));
end
```

**Access individual subject's connectivity:**
```matlab
subject_idx = 1;
A_matrix = GCM{subject_idx}.Ep.A;    % Intrinsic connectivity
disp(A_matrix);
```

---

### Understanding Key Statistical Fields

**Posterior Probability (Pp):**
- Computed during estimation: `Pp = 1 - spm_Ncdf(T=0, abs(Ep), sqrt(diag(Cp)))`
- Ranges from 0 to 1
- Interpretation: Probability that parameter is positive (one-sided test)
- Threshold for "significant": typically Pp > 0.95 (equivalent to p < 0.05)

**Posterior Covariance (Cp):**
- Square (Np×Np) matrix of parameter covariances
- Diagonal contains parameter variances
- Larger values indicate less certainty
- Used in thresholding and visualization

**Parameter Estimates (Ep):**
- Group-level effect size for each parameter
- Ep(:,1) = intercept (mean effect across subjects)
- Ep(:,k) = effect of k-th regressor
- Units: same as individual DCM parameter units (log-odds for connectivity)

---

### SPM Functions for Further Analysis

Common SPM functions that work with these structures:

```matlab
% Review results in SPM GUI (uses xPEB):
spm_dcm_peb_review(xPEB);

% Bayesian Model Reduction (uses PEB):
[BMA, BMC] = spm_dcm_peb_bmc(PEB);

% Extract region connectivity from GCM:
A = GCM{1}.Ep.A;  % Individual connectivity matrix

% Visualize group effects:
spm_plot_ci(PEB.Ep(:,1), diag(PEB.Cp(:,:,1)));
```

---

### Common Workflows

**Scenario 1: Extract group connectivity and compare to null**
```matlab
load('PEB_[model_name].mat');
% Connectivity parameters might be rows 1-12 (for 4 regions: 4×4-1 = 15 params minus diagonal)
A_params = 1:12;
significant_A = PEB.Pp(A_params) > 0.95;
group_A = reshape(PEB.Ep(A_params, 1), 4, 3);
```

**Scenario 2: Correlate DCM parameter with age**
```matlab
load('PEB_[model_name].mat');
% Note: Age should be a regressor in the design matrix
% Find which column represents age (check PEB.Xnames)
age_col = find(strcmp(PEB.Xnames, 'age'));
if ~isempty(age_col)
    age_effects = PEB.Ep(:, age_col);
    age_pp = diag(PEB.Cp(:,:,age_col)) > 0.95;
end
```

**Scenario 3: Extract participant-level parameters for mediation analysis**
```matlab
load('GCM_[model_name].mat');
% Extract a specific connection (e.g., A(1,2)) for all subjects
A_12 = zeros(length(GCM), 1);
for i = 1:length(GCM)
    A_12(i) = GCM{i}.Ep.A(1, 2);
end
```



## Advanced Notes

### Analysis Type Selection

- **CSD (resting-state)**: Use `analysis: csd` in config or default behavior
  - Only models A matrix (intrinsic connectivity)
  - Appropriate for resting-state DCM

- **Timeseries (task-based)**: Use `analysis: timeseries`
  - Models A, B, and C matrices
  - Appropriate for task-based DCM with modulation

### Prior Settings

Default SPM priors are used:
```
ratio = 16           # Between-group vs. within-group variance ratio
expectation = 0      # Expected group effect (centered)
variance = 0.0625    # Prior variance on group parameters
```

These can be modified in the MATLAB code generated for advanced use cases.

## Troubleshooting

### "ERROR: X DCM subjects not found in participants file"
- You have DCM files for subjects that are NOT listed in participants.tsv
- Solution: Add all subjects with DCM files to participants.tsv
- Note: The reverse is OK - having participants in the file without DCM files is fine; they'll just be skipped

### "No DCM files found for model X"
- Verify participant-level --dcm analysis completed successfully
- Check that model name matches exactly (case-sensitive)
- Ensure DCM output files are in expected location: `sub-XXX/[ses-YYY/]func/SPM/DCM_[model].mat`

### "Missing columns in participants file"
- Verify column names in participants.tsv match --regressors argument
- Check for typos (case-sensitive)
- Ensure file is tab-separated, not comma-separated

### Missing values in covariates
- Detected automatically and handled with mean imputation (for continuous variables)
- Check processing log for imputation messages
- Consider removing participants with critical missing data

## References

For more information about PEB in SPM:
- Friston et al. (2015). "Parametric empirical Bayes" in SPM12
- Documentation: <https://www.fil.ion.ucl.ac.uk/spm/doc/>

For DCM framework:
- Friston et al. (2003). "Dynamic causal modelling" NeuroImage 19:1273-1302
