# MATLAB Templates & Script Generation

This document describes how `spmx` generates MATLAB scripts that drive SPM processing.

## Overview

The tool does not interact directly with the SPM GUI. Instead, it:

1. **Generates MATLAB scripts dynamically** based on user configuration and data
2. **Creates SPM batch specifications** using the `matlabbatch` system
3. **Runs the scripts in MATLAB** via command-line
4. **Captures results** and renames them to BIDS conventions

## Design Philosophy

The approach minimizes MATLAB usage by:
- Using Python for all logic, data handling, and configuration
- Calling MATLAB only for SPM-specific operations
- Generating reproducible, human-readable MATLAB scripts
- Storing scripts in logs for inspection and debugging

## SPM Batch System

SPM uses a batch processing system (`matlabbatch`). Each batch is a cell array of structures containing processing specifications. The general structure is:

```matlab
% Add SPM to path
addpath(genpath('/path/to/spm12'));

% Define batch jobs
matlabbatch{1}.spm.module.submodule.parameter = value;
matlabbatch{2}.spm.module.submodule.parameter = value;

% Execute batch
spm_jobman('run', matlabbatch);
```

## Template Files

The tool includes template files for each processing stage:

### fmri_fit.m

Specifies and estimates first-level GLM with optional contrasts.

**Key sections:**

```matlab
% === MODEL SPECIFICATION ===
matlabbatch{1}.spm.stats.fmri_spec.timing.units = 'secs';
matlabbatch{1}.spm.stats.fmri_spec.timing.RT = TR_VALUE;
matlabbatch{1}.spm.stats.fmri_spec.timing.fmri_t = 16;    % Microtime bins
matlabbatch{1}.spm.stats.fmri_spec.timing.fmri_t0 = 8;    % Reference bin

% Session data (scans, conditions, regressors)
matlabbatch{1}.spm.stats.fmri_spec.sess.scans = scan_list;

% Conditions (task events)
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).name = 'condition_name';
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).onset = onset_vector;
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).duration = duration_vector;

% Regressors (confounds)
matlabbatch{1}.spm.stats.fmri_spec.sess.regress(1).name = 'regressor_name';
matlabbatch{1}.spm.stats.fmri_spec.sess.regress(1).val = regressor_timeseries;

% === MODEL ESTIMATION ===
matlabbatch{2}.spm.stats.fmri_est.spmmat = ...;
matlabbatch{2}.spm.stats.fmri_est.write_residuals = 0;
matlabbatch{2}.spm.stats.fmri_est.method.Classical = 1;

% === CONTRASTS ===
matlabbatch{3}.spm.stats.con.spmmat = ...;
matlabbatch{3}.spm.stats.con.consess = {};  % Filled with contrast specifications

% === RESULTS EXPORT ===
matlabbatch{4}.spm.stats.results.spmmat = ...;
matlabbatch{4}.spm.stats.results.export{1}.pdf = true;
matlabbatch{4}.spm.stats.results.export{2}.csv = true;
```

### fmri_voi.m

Extracts BOLD timeseries from seed regions of interest.

**Key sections:**

```matlab
matlabbatch{1}.spm.util.voi.spmmat = path_to_spmmat;
matlabbatch{1}.spm.util.voi.adjust = NaN;
matlabbatch{1}.spm.util.voi.session = session_number;
matlabbatch{1}.spm.util.voi.name = 'VOI_name';

% Define ROI as intersection of sphere and brain mask
matlabbatch{1}.spm.util.voi.roi{1}.sphere.centre = [x, y, z];
matlabbatch{1}.spm.util.voi.roi{1}.sphere.radius = radius_mm;

matlabbatch{1}.spm.util.voi.roi{2}.mask.image = mask_file;
matlabbatch{1}.spm.util.voi.roi{2}.mask.threshold = 0.5;

% Expression: intersection of sphere and mask
matlabbatch{1}.spm.util.voi.expression = 'i1&i2';
```

### fmri_dcm_estimate.m

Specifies and estimates Dynamical Causal Models.

**Key sections:**

```matlab
% Load SPM.mat and VOI files
SPM = load(spm_file);
VOI1 = load(voi_file_1);
VOI2 = load(voi_file_2);
% ... etc

% Create DCM structure
DCM.a = A_matrix;              % Endogenous connections
DCM.b = B_matrix;              % Bilinear modulations
DCM.c = C_vector;              % Exogenous connections

DCM.xY = [VOI1.xY; VOI2.xY];   % VOI timeseries data
DCM.Y.dt = SPM.xY.RT;          % Repetition time
DCM.Y.X0 = SPM.xX.xKXs.X(...); % Confounds and constants

DCM.v = n_volumes;
DCM.n = n_vois;
DCM.TE = echo_time;
DCM.delays = delay_vector;

% DCM estimation options
DCM.options.nonlinear = 0;     % Non-linear coupling
DCM.options.two_state = 0;     % Two-state HRF model
DCM.options.stochastic = 0;    % Stochastic dynamics
DCM.options.centre = 0;        % Centre priors
DCM.options.induced = 1;       % CSD (induced) or timeseries

% Run estimation
matlabbatch{1}.spm.dcm.estimate.dcms.model.dcmmat = dcm_file;
spm_jobman('run', matlabbatch);
```

## Script Generation Workflow

### 1. Data Collection (Python)

```python
# Gather parameters from:
# - BIDS metadata (TR, TE, image dimensions)
# - User config file (model parameters)
# - Task events file (condition definitions)
# - Confounds file (regressor timeseries)

tr = load_json_metadata(bold_json)['RepetitionTime']
n_volumes = get_nifti_n_volumes(bold_nifti)
conditions = parse_events_file(events_tsv)
confounds = parse_confounds_file(confounds_tsv)
```

### 2. Template Instantiation (Python)

```python
# Load template and fill placeholders
template = load_template('fmri_fit.m')

# Replace placeholders (marked as ???)
script = template.replace('???TR_VALUE???', str(tr))
script = script.replace('???N_VOLUMES???', str(n_volumes))
# ... etc
```

### 3. Script Execution (Python + MATLAB)

```matlab
% Generated script for subject-01, session-01

% System setup
spm_home = '/opt/spm12';
addpath(genpath(spm_home));

% === SESSION SETUP ===
output_dir = '/data/derivatives/spm/sub-001/ses-01/func';
spm_directory = output_dir;

% === MODEL SPECIFICATION ===
matlabbatch{1}.spm.stats.fmri_spec.dir = {output_dir};
matlabbatch{1}.spm.stats.fmri_spec.timing.units = 'secs';
matlabbatch{1}.spm.stats.fmri_spec.timing.RT = 2.0;
matlabbatch{1}.spm.stats.fmri_spec.timing.fmri_t = 16;
matlabbatch{1}.spm.stats.fmri_spec.timing.fmri_t0 = 8;

% Scan list (preprocessed images)
matlabbatch{1}.spm.stats.fmri_spec.sess.scans = {
  '/data/derivatives/spm/sourcedata/sub-001/ses-01/func/sub-001_ses-01_task-rest_space-MNI_desc-preproc_bold.nii';
};

% (repeated for all volumes)

% === CONDITIONS ===
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).name = 'face';
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).onset = [5.2, 12.3, 25.1];
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).duration = [2.0, 2.0, 2.0];
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).tmod = 0;
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).orth = 1;

matlabbatch{1}.spm.stats.fmri_spec.sess.cond(2).name = 'house';
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(2).onset = [8.2, 18.3, 30.1];
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(2).duration = [2.0, 2.0, 2.0];
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(2).tmod = 0;
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(2).orth = 1;

% === CONFOUNDS ===
matlabbatch{1}.spm.stats.fmri_spec.sess.regress(1).name = 'trans_x';
matlabbatch{1}.spm.stats.fmri_spec.sess.regress(1).val = [0.01, 0.02, -0.01, ...];

% ... (repeat for other confounds)

% === ESTIMATION ===
matlabbatch{2}.spm.stats.fmri_est.spmmat(1) = cfg_dep(...);
matlabbatch{2}.spm.stats.fmri_est.write_residuals = 0;
matlabbatch{2}.spm.stats.fmri_est.method.Classical = 1;

% === RUN ===
spm_jobman('run', matlabbatch);
```

### 4. Output Processing (Python)

```python
# SPM creates/modifies files in the output directory:
# - SPM.mat (model specification and results)
# - beta_000X.nii (parameter estimate images)
# - con_000X.nii (contrast images)
# - Reports (PDF, CSV)

# spmx then:
# 1. Renames files to BIDS conventions
# 2. Compresses NIFTI files
# 3. Generates JSON sidecars
# 4. Creates dataset_description.json
```

## Data Handling

### Uncompressed NIFTI Files

SPM requires uncompressed NIFTI files. The workflow handles this as follows:

1. **Input data** is in compressed format (`.nii.gz`)
2. **Create `<output_dir>/sourcedata/`** with participant/session structure
3. **Decompress BIDS files** into sourcedata
4. **Pass to SPM** via batch system
5. **SPM modifies files** in sourcedata or output directory
6. **Rename results** to BIDS format in final output location
7. **Optionally clean** with `--clean-spm-files`

## File Naming

### BIDS Compliance

All outputs are renamed according to BIDS conventions:

```
<output_dir>/sub-<label>/[ses-<label>/]func/
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_desc-prefit_bold.nii.gz
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_desc-prefit_bold.json
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_desc-prefit_beta_001.nii.gz
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_desc-prefit_beta_001.json
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_desc-prefitcon_con_001.nii.gz
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_desc-prefitcon_con_001.json
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_desc-voi-pcc_timeseries.mat
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_desc-voi-pcc_timeseries.json
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_model-full_dcm.mat
├── sub-<label>[_ses-<label>]_task-<label>_space-<label>_model-full_dcm.json
└── SPM.mat
```

### JSON Sidecars

Every output data file has a corresponding JSON sidecar with metadata:

```json
{
  "RepetitionTime": 2.0,
  "EchoTime": 0.04,
  "SPMVersion": "12.7890",
  "ProcessingType": "fit|voi|dcm",
  "Model": "full",
  "ConditionName": "face",
  "ContrastDefinition": "face - house",
  "VOIName": "PCC",
  "VOIRadiusMM": 5.0
}
```

## Debugging

To inspect generated MATLAB scripts:

```bash
spmx fmri /input /output --fit --debug --config config.yaml
```

This creates:
```
OUTPUT_DIR/
└── logs/
    └── sub-001/
        └── ses-01/
            └── matlab_scripts/
                ├── 01_fmri_spec.m
                ├── 02_fmri_est.m
                └── 03_con.m
```

View the generated scripts to understand exactly what SPM is doing:

```bash
cat OUTPUT_DIR/logs/sub-001/ses-01/matlab_scripts/01_fmri_spec.m
```

## Template Modification

To modify template behavior:

1. Edit template file in `spmx/templates/fmri_*.m`
2. Ensure all dynamic values are clearly marked (e.g., `???PLACEHOLDER???`)
3. Use comments to explain fixed vs. dynamic parts
4. Test with `--debug` flag to verify generated scripts
5. Submit PR with explanation of changes

## Performance Considerations

- **Script generation**: Negligible (milliseconds)
- **MATLAB startup**: 5-15 seconds per run (unavoidable)
- **SPM processing**: Varies by dataset size and model complexity
  - Fit: 2-5 minutes per subject
  - VOI: <1 minute per subject
  - DCM: 5-30 minutes per model per subject

Use multi-level parallelization:
- Process different subjects in parallel (outside spmx)
- Process different sessions in parallel
- Request appropriate MATLAB licenses for your setup
