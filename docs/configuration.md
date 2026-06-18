# Configuration Guide

Comprehensive reference for configuring `spmx` via YAML configuration files.

## Configuration File Structure

Configuration files must be valid YAML (`.yaml` or `.yml`) with the following top-level structure:

```yaml
# MATLAB and SPM paths
matlab_path: /path/to/matlab
spm_path: /path/to/spm12

# Module-specific configurations
fmri:
  fit:
    # ... fit parameters ...
  voi:
    # ... voi parameters ...
  dcm:
    # ... dcm parameters ...

pet:
  # PET module (placeholder)
```

## Priority Order

Settings are applied in this order (later overrides earlier):

1. **Built-in defaults** (in `defaults.py`)
2. **Configuration file** (if provided with `--config`)
3. **Command-line arguments** (if provided)

## Top-Level Settings

### matlab_path

**Required once (config or CLI)**

Path to MATLAB executable.

```yaml
matlab_path: /opt/matlab/R2023b/bin/matlab
```

**Also available via CLI:**
```bash
spmx fmri /input /output --fit --matlab-path /opt/matlab/R2023b/bin/matlab
```

**Default behavior:** Search PATH environment variable

### spm_path

**Optional**

Path to SPM installation directory.

```yaml
spm_path: /opt/spm12
```

**Also available via CLI:**
```bash
spmx fmri /input /output --fit --spm-path /opt/spm12
```

**Default behavior:** `$MATLABPATH/toolboxes/spm`

## fMRI Module Configuration

### fit Section

First-level GLM specification and estimation parameters.

#### fmri_t

**Microtime resolution**: Number of time bins per TR (repetition time).

```yaml
fmri:
  fit:
    fmri_t: 16
```

- **Type**: Integer
- **Default**: 16 (SPM standard)
- **Typical range**: 8-32
- **Purpose**: Higher values increase temporal resolution of hemodynamic model
- **Recommendation**: Keep at 16 unless you have specific reasons to change

#### fmri_t0

**Microtime onset**: Reference time bin within the TR.

```yaml
fmri:
  fit:
    fmri_t0: 8
```

- **Type**: Integer
- **Default**: 8 (middle of TR)
- **Formula**: fmri_t0 should be approximately fmri_t/2
- **Typical value**: 8 (for fmri_t=16)
- **Purpose**: Shifts reference point of neuronal activity relative to BOLD signal

#### hpf

**High-pass filter**: Cutoff frequency in seconds.

```yaml
fmri:
  fit:
    hpf: 128
```

- **Type**: Float
- **Default**: 128 seconds
- **Typical range**: 100-200 seconds (resting-state)
- **Typical range**: 50-128 seconds (task-based)
- **Effect**: Removes slow drifts and scanner artifacts
- **128s ≈**: 2.1 minutes (common for resting-state)
- **Recommendation**: Standard value; adjust lower for faster task designs

#### cond_tmod

**Condition temporal modulation**: Enable temporal derivatives of regressors.

```yaml
fmri:
  fit:
    cond_tmod: 0
```

- **Type**: Integer (0 or 1)
- **Default**: 0 (no temporal modulation)
- **0**: No temporal derivatives
- **1**: Include first temporal derivative of each condition
- **Purpose**: Models timing variability in condition onsets
- **When to use**: Task designs with variable timing; rarely used for resting-state

#### cond_orth

**Condition orthogonalization**: Orthogonalize modulation within conditions.

```yaml
fmri:
  fit:
    cond_orth: 1
```

- **Type**: Integer (0 or 1)
- **Default**: 1 (yes, recommended)
- **Recommendation**: Keep at 1 to avoid multicollinearity

#### write_residuals

**Write residual images**: Save residual maps after estimation.

```yaml
fmri:
  fit:
    write_residuals: 0
```

- **Type**: Integer (0 or 1)
- **Default**: 0 (don't write)
- **Disk implications**: Each residual map ~50MB; can be substantial for large datasets
- **When to use**: Quality assurance; model diagnostics
- **Recommendation**: Keep at 0 unless needed for troubleshooting

#### regressors

**Confound regressor names**: Columns to extract from confounds_timeseries.tsv.

```yaml
fmri:
  fit:
    regressors:
      - trans_x
      - trans_y
      - trans_z
      - rot_x
      - rot_y
      - rot_z
      - csf
      - white_matter
```

- **Type**: List of strings
- **Default**: None (no confounds)
- **Source**: From `*_desc-confounds_timeseries.tsv` in input dataset
- **Note**: Column names must exactly match confounds header
- **Motion parameters**: Typically trans_x, trans_y, trans_z, rot_x, rot_y, rot_z
- **Signal**: Typically csf, white_matter (nuisance signals)
- **Frame displacement**: framewise_displacement (if calculated by fMRIPrep)

**Verify available confounds:**
```bash
head -1 sub-001_task-rest_desc-confounds_timeseries.tsv | tr '\t' '\n'
```

**Common regressor sets:**

```yaml
# Minimal (motion only)
regressors:
  - trans_x
  - trans_y
  - trans_z
  - rot_x
  - rot_y
  - rot_z

# Standard (motion + signal nuisance)
regressors:
  - trans_x
  - trans_y
  - trans_z
  - rot_x
  - rot_y
  - rot_z
  - csf
  - white_matter

# Aggressive (motion + nuisance + derivatives)
regressors:
  - trans_x
  - trans_y
  - trans_z
  - rot_x
  - rot_y
  - rot_z
  - trans_x_derivative1
  - trans_y_derivative1
  - trans_z_derivative1
  - rot_x_derivative1
  - rot_y_derivative1
  - rot_z_derivative1
  - csf
  - white_matter
  - csf_derivative1
  - white_matter_derivative1
```

#### conditions (via CLI)

**Task conditions to include as regressors** (not in config file; CLI only).

```bash
spmx fmri /input /output --fit --condition face house
```

- **Type**: Space-separated list
- **Source**: From `trial_type` column in task events file
- **File**: `*_task-TASK_events.tsv`
- **Example trial_types**: face, house, tool, body, animal (depends on task)

**Usage:**
- Automatically creates condition regressors from event timings
- Pulls onset and duration from events.tsv

#### events_file (via CLI)

**Path to events.tsv file** (not in config file; CLI only).

```bash
spmx fmri /input /output --fit \
  --events-file ~/data/events/sub-001_task-gas_events.tsv \
  --condition gas
```

- **Type**: Path to TSV file
- **Default**: Automatically discovered via BIDS layout
- **When to use**: Events file cannot be automatically discovered, or you want to use events from a custom location
- **Format**: Standard BIDS events format with at minimum `onset`, `duration`, and `trial_type` columns
- **Discovery priority**:
  1. **Explicit path** — If `--events-file` is provided, use it directly
  2. **BIDS layout search** — Search INPUT_DIR using BIDS entity filters (subject, session, task)
  3. **Root-level fallback** — Look in `INPUT_DIR/sub-{subject}[/ses-{session}]/func/` for matching file
- **Required when**: `--condition` is specified and pipeline cannot auto-discover the file

**Example use cases:**
- Events file stored outside standard BIDS structure
- Same events used for multiple subjects or sessions
- Custom preprocessing workflow with relocated events files

#### confound (via CLI)

**Confound regressor names** from confounds file (CLI alternative to config).

```bash
spmx fmri /input /output --fit \
  --confound trans_x trans_y rot_x rot_y csf white_matter
```

- **Type**: Space-separated list of column names
- **Source**: `*_desc-confounds_timeseries.tsv` in input dataset
- **Note**: Columns must exactly match the confounds file header
- **Priority**: CLI argument overrides config file setting
- **Default**: No confounds (empty list)

#### contrasts (via CLI)

**Contrast definitions** (not in config file; CLI only).

```bash
spmx fmri /input /output --fit \
  --condition face house \
  --contrast "face - house" "face + house" "0.5*face"
```

- **Type**: Space-separated list of expressions
- **Syntax**: Condition names with +, -, and scalar multipliers
- **Format Examples**:
  - `"face - house"` — T-contrast comparing face and house
  - `"face + house"` — Overall effect of face and house
  - `"0.5*face"` — Scalar downweighting
  - `"face - 0.5*house"` — Mixed weights
- **Optional**: If not specified, GLM is fit but no contrasts are computed

### voi Section

Volume of Interest (ROI) extraction parameters.

#### radius

**Default VOI sphere radius** in millimeters.

```yaml
fmri:
  voi:
    radius: 8
```

- **Type**: Float
- **Default**: 8 mm
- **Typical range**: 4-12 mm
- **Notes**: Can be overridden per-seed
- **Interpretation**: Larger radius captures more voxels; smaller is more specific

#### seeds

**List of regions of interest** in MNI coordinates.

```yaml
fmri:
  voi:
    seeds:
      - name: "PCC"
        x: 0
        y: -52
        z: 18
        radius: 5    # Optional; overrides default

      - name: "mPFC"
        x: 0
        y: 52
        z: 0
        # No radius specified → uses default (8 mm)

      - name: "LIPL"
        x: -45
        y: -70
        z: 35
```

**Fields:**
- **name** (required): ROI identifier; will appear in output filenames
- **x** (required): MNI x coordinate in mm; positive = right hemisphere
- **y** (required): MNI y coordinate in mm; positive = anterior
- **z** (required): MNI z coordinate in mm; positive = superior
- **radius** (optional): Sphere radius in mm; overrides global default

**Coordinates**: Standard MNI 2009c asymmetric template

**Naming**: Use short, uppercase codes; examples:
- PCC = Posterior Cingulate Cortex
- mPFC = Medial Prefrontal Cortex
- dmPFC = Dorsal mPFC
- vmPFC = Ventral mPFC
- LIPL = Left Inferior Parietal Lobule
- RIPL = Right IPL
- LAG = Left Angular Gyrus
- RAG = Right Angular Gyrus

### dcm Section

Dynamical Causal Modeling parameters.

#### delays

**VOI-specific delays** in seconds (typically HRF latency).

```yaml
fmri:
  dcm:
    delays:
      PCC: 1.5
      mPFC: 1.6
      LIPL: 1.5
      RIPL: 1.5
```

- **Type**: Dictionary (name → float)
- **Default**: 1.5 seconds for any VOI not specified
- **Typical range**: 1.5-2.0 seconds
- **Interpretation**: Delay between neural and BOLD signal
- **Keys must match**: VOI names defined in voi.seeds section

#### models

**Pre-defined or custom DCM models** to estimate.

```yaml
fmri:
  dcm:
    models:
      - name: "full"
        description: "All connections enabled"
        A: [[1, 1], [1, 1]]
        B: [[0, 0], [0, 0]]
        C: [1, 0]

      - name: "hierarchical"
        description: "PCC→mPFC→LIPL hierarchy"
        A: [
          [0, 1, 0, 0],
          [1, 0, 1, 0],
          [0, 1, 0, 1],
          [0, 0, 1, 0]
        ]
        B: [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        C: [1, 0, 0, 0]
```

**Fields:**
- **name** (required): Model identifier; appears in output filenames
- **description** (optional): Human-readable model description
- **A** (required): N×N matrix of endogenous connections (0 or 1)
- **B** (required): N×N matrix of bilinear modulations (0 or 1)
- **C** (required): N vector of exogenous inputs (0 or 1)

**Pre-defined models** (use by name in --model CLI flag):
- `full` — All A=1; no B or C modulation
- `resting-state-full` — Optimized for resting-state; all A=1, B=0, C=0

#### options

**Estimation options** for DCM inference.

```yaml
fmri:
  dcm:
    options:
      nonlinear: 0
      two_state: 0
      stochastic: 0
      centre: 0
      induced: 1
```

- **nonlinear** (0 or 1; default: 0) — Include nonlinear coupling terms
- **two_state** (0 or 1; default: 0) — Two-state hemodynamic model
- **stochastic** (0 or 1; default: 0) — Stochastic dynamics
- **centre** (0 or 1; default: 0) — Centre priors (non-standard)
- **induced** (0 or 1; default: 1) — Induced (CSD) for resting-state; timeseries for task

**Recommendation for resting-state**: Use defaults as shown above

## Configuration Examples

### Minimal Resting-State

```yaml
matlab_path: /opt/matlab/R2023b/bin/matlab
spm_path: /opt/spm12

fmri:
  fit:
    hpf: 128
    regressors:
      - trans_x
      - trans_y
      - trans_z
      - rot_x
      - rot_y
      - rot_z

  voi:
    radius: 8
    seeds:
      - name: "PCC"
        x: 0
        y: -52
        z: 18
```

### Complete DCM Workflow

```yaml
matlab_path: /opt/matlab/R2023b/bin/matlab
spm_path: /opt/spm12

fmri:
  fit:
    fmri_t: 16
    fmri_t0: 8
    hpf: 128
    cond_tmod: 0
    cond_orth: 1
    write_residuals: 0
    regressors:
      - trans_x
      - trans_y
      - trans_z
      - rot_x
      - rot_y
      - rot_z
      - csf
      - white_matter

  voi:
    radius: 8
    seeds:
      - name: "PCC"
        x: 0
        y: -52
        z: 18
        radius: 5
      - name: "mPFC"
        x: 0
        y: 52
        z: 0
        radius: 6
      - name: "LIPL"
        x: -45
        y: -70
        z: 35
      - name: "RIPL"
        x: 45
        y: -70
        z: 35

  dcm:
    delays:
      PCC: 1.5
      mPFC: 1.5
      LIPL: 1.5
      RIPL: 1.5
    
    models:
      - name: "full"
        A: [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]]
        B: [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        C: [1, 0, 0, 0]
    
    options:
      nonlinear: 0
      two_state: 0
      stochastic: 0
      centre: 0
      induced: 1
```

### Task-Based fMRI

```yaml
matlab_path: /opt/matlab/R2023b/bin/matlab
spm_path: /opt/spm12

fmri:
  fit:
    hpf: 100
    cond_tmod: 0
    cond_orth: 1
    regressors:
      - trans_x
      - trans_y
      - trans_z
      - rot_x
      - rot_y
      - rot_z
      - csf
      - white_matter
```

Then use CLI for task-specific options:

```bash
spmx fmri /input /output --fit \
  --config config.yaml \
  --condition face house \
  --confound trans_x trans_y trans_z rot_x rot_y rot_z csf white_matter \
  --contrast "face - house" "face + house"
```

## Validation

### Check Configuration Syntax

```bash
# Python YAML validation
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# If no error, configuration is valid YAML
```

### Check Against Schema

`spmx` validates configuration at runtime. Errors will be reported:

```
ERROR: Invalid configuration: fmri.fit.hpf must be a positive number
ERROR: Invalid configuration: fmri.dcm.models[0].A must be NxN matrix
ERROR: Invalid configuration: fmri.voi.seed 'PCC' referenced in delays but not defined
```

## Tips & Best Practices

1. **Start with examples**: Use provided config examples and modify
2. **Comment liberally**: YAML supports `# comments`
3. **Validate early**: Run simple fit before complex DCM workflows
4. **Check your data**: Verify confound names match exactly (e.g., `trans_x` vs `trans_X`)
5. **Use git**: Version control your configs for reproducibility
6. **Document decisions**: Add comments explaining why you chose certain parameters

## Related Documentation

- [Usage Guide](../README.md#usage-guide)
- [Examples](../config_examples/)
- [DCM Specification](dcm_specification.md)
- [Troubleshooting](../README.md#troubleshooting)
