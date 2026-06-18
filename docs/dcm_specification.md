# DCM Specification & Structure

This document describes how Dynamical Causal Models are specified and estimated in `spmx`.

## DCM Overview

Dynamical Causal Modeling (DCM) estimates the effective connectivity (directed causal connections) between brain regions based on fMRI timeseries data. Unlike correlation-based connectivity, DCM models the biophysical mechanisms driving the observed BOLD signal.

## DCM Structure

A DCM specification consists of three connectivity matrices:

### A Matrix (Endogenous Connections)

Defines intrinsic connections between regions - how each region's activity depends on other regions' activity.

**Matrix dimensions**: N×N (where N = number of regions)

**Values**: 0 (connection fixed at zero) or 1 (connection to be estimated)

**Example (3-region model connecting PCC → mPFC → LIPL):**

```
A = [
     0  0  1   % PCC sends signal from LIPL
     1  0  1   % mPFC receives from PCC and LIPL
     0  0  0   % LIPL sends only to mPFC
]

Interpretation:
- A(1,3) = 1: LIPL → PCC connection (enabled)
- A(2,1) = 1: PCC → mPFC connection (enabled)
- A(2,3) = 1: LIPL → mPFC connection (enabled)
- All others = 0: no connection
```

### B Matrix (Bilinear Modulations)

Defines how external inputs or experimental conditions modulate connections. For resting-state DCM, typically all zeros.

**Matrix dimensions**: N×N

**Values**: 0 (no modulation) or 1 (modulation to be estimated)

**For resting-state**:
```yaml
B: [[0, 0, 0], [0, 0, 0], [0, 0, 0]]  # All zeros
```

**For task-based (future)**:
```yaml
B: [[0, 0, 0], [1, 0, 0], [0, 0, 0]]  # Input modulates mPFC
```

### C Vector (Exogenous Inputs)

Defines external inputs to each region. For resting-state, typically sparse (e.g., only to one "hub" region).

**Vector dimensions**: N (where N = number of regions)

**Values**: 0 (no input) or 1 (input from outside system)

**Example (3-region model with PCC as hub):**

```
C = [1, 0, 0]  # Input only to PCC (acting as hub)
```

## Pre-defined Models

### full

All A-matrix connections enabled; no B or C modulation.

```yaml
- name: "full"
  A: [[1, 1], [1, 1]]
  B: [[0, 0], [0, 0]]
  C: [1, 0]
  Description: "All reciprocal connections; one hub input"
```

Used for exploratory connectivity analysis when network structure is unknown.

**Interpretation**: Allows bidirectional connections between all regions.

### resting-state-full

Specific for resting-state networks (DMN, salience network, etc.). All A=1 (bidirectional), but no B or C modulation.

```yaml
- name: "resting-state-full"
  A: [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]]
  B: [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
  C: [0, 0, 0, 0]
  Description: "Full reciprocal connectivity for resting-state"
```

**Note**: If `--task rest` is used with `--model full`, a warning is raised suggesting `resting-state-full` instead.

## Custom Models

Define custom models in config file:

```yaml
fmri:
  dcm:
    models:
      - name: "dmn-hierarchy"
        A: [
          [0, 1, 0, 0],   # PCC receives from mPFC
          [1, 0, 1, 0],   # mPFC bidirectional with PCC and LIPL
          [0, 1, 0, 1],   # LIPL receives from mPFC and RIPL
          [0, 0, 1, 0]    # RIPL receives from LIPL
        ]
        B: [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        C: [1, 0, 0, 0]
        description: "Hierarchical Default Mode Network"
```

## DCM Estimation Options

### Delays

VOI-specific delays in seconds (typically HRF latency for each region):

```yaml
fmri:
  dcm:
    delays:
      PCC: 1.5    # Posterior Cingulate with 1.5s delay
      mPFC: 1.5   # Medial Prefrontal with 1.5s delay
      LIPL: 1.5   # Left IPL with 1.5s delay
      RIPL: 1.5   # Right IPL with 1.5s delay
```

**Default**: 1.5 seconds for any VOI not specified

**Typical range**: 1.5-2.0 seconds (standard cortical HRF delay)

### Options Structure

```yaml
fmri:
  dcm:
    options:
      nonlinear: 0    # [0|1] Include non-linear coupling
      two_state: 0    # [0|1] Two-state hemodynamic model
      stochastic: 0   # [0|1] Stochastic dynamics
      centre: 0       # [0|1] Centre priors
      induced: 1      # [0|1] 1=Spectral (resting-state); 0=Timeseries (task)
```

#### Option Details

- **nonlinear=1**: Includes quadratic terms in state equations (computationally expensive; rarely used)
- **two_state=1**: Two-state blood-oxygenation model (vs. one-state default; more realistic but slower)
- **stochastic=1**: Stochastic (random) dynamics (vs. deterministic; captures fluctuations)
- **centre=1**: Uses centre priors (default: mean-field priors; not recommended unless specific reason)
- **induced=1**: Cross-Spectral Density (CSD) analysis type - **required for resting-state**
  - induced=1: Good for resting-state (no experimental input)
  - induced=0: Timeseries analysis type for task-based DCM

**Default settings** (as in `defaults.py`):

```python
FMRI_DCM = {
    "options": {
        "nonlinear": 0,
        "two_state": 0,
        "stochastic": 0,
        "centre": 0,
        "induced": 1,       # Resting-state
    },
}
```

## DCM Structure Fields

When built internally, the DCM MATLAB structure contains:

```matlab
DCM.a = A_matrix;           % Endogenous connections
DCM.b = B_matrix;           % Bilinear modulations
DCM.c = C_vector;           % Exogenous inputs

% Data and constraints
DCM.xY = VOI_data;          % VOI timeseries structures
DCM.Y.dt = TR;              % Repetition time
DCM.Y.X0 = design_matrix;   % Confounds and regressors
DCM.Y.y = timeseries_matrix;% Observed BOLD data

% Model specifications
DCM.v = n_volumes;         % Number of volumes
DCM.n = n_regions;         % Number of regions/VOIs
DCM.TE = echo_time;        % Echo time for BOLD model

% Delays and estimation
DCM.delays = delay_vector; % VOI-specific delays
DCM.options = estimation_options;  % Estimation options

% Parameter posteriors (after estimation)
DCM.Ep.A = estimated_A;    % Estimated connection parameters
DCM.Ep.B = estimated_B;
DCM.Ep.C = estimated_C;
```

## Estimation Process

### 1. Model Configuration

```python
# User specifies model in config or CLI
model_spec = {
    'name': 'full',
    'A': [[1, 1], [1, 1]],
    'B': [[0, 0], [0, 0]],
    'C': [1, 0]
}
```

### 2. DCM Structure Creation

```python
# Build DCM structure with user model + data
DCM.a = model_spec['A']      # User's A matrix
DCM.b = model_spec['B']      # User's B matrix
DCM.c = model_spec['C']      # User's C vector

# Load VOI timeseries
voi1 = load_mat(voi_file_1)
voi2 = load_mat(voi_file_2)
DCM.xY = [voi1.xY, voi2.xY]

# Load SPM results for constraints
spm = load_mat('SPM.mat')
DCM.Y.X0 = spm.xX.xKXs.X([:, [spm.xX.iB, spm.xX.iG]])
DCM.Y.dt = spm.xY.RT
```

### 3. SPM Estimation

```matlab
% MATLAB: Run DCM estimation via matlabbatch
matlabbatch{1}.spm.dcm.estimate.dcms.model.dcmmat = 'DCM_full.mat';
spm_jobman('run', matlabbatch);
```

DCM iteratively estimates parameters using Bayesian optimization (Variational Bayes).

### 4. Output

Estimated parameters in `DCM.Ep`:

```
DCM.Ep.A    % Estimated endogenous connections (N×N matrix)
DCM.Ep.B    % Estimated bilinear modulations (N×N matrix)
DCM.Ep.C    % Estimated exogenous inputs (N vector)
DCM.Ce.A    % Covariances (uncertainty) for A
DCM.Ce.B    % Covariances for B
DCM.Ce.C    % Covariances for C
```

## Resting-State DCM Considerations

### Why Resting-State is Simpler

- **No experimental design**: No task structure or events to model
- **No exogenous input**: B and C matrices typically all zeros (or fixed)
- **Spectral analysis**: DCM uses cross-spectral density (induced=1) rather than timeseries
- **Longer scans needed**: Minimum ~5 minutes recommended (vs. 30-60 min typical for task-based)

### Default Config for Resting-State

```yaml
fmri:
  dcm:
    models:
      - name: "resting-state-full"
        A: [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]]
        B: [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        C: [0, 0, 0, 0]
    
    options:
      nonlinear: 0
      two_state: 0
      stochastic: 0
      centre: 0
      induced: 1         # Critical: CSD analysis for resting-state
    
    delays:
      PCC: 1.5
      mPFC: 1.5
      LIPL: 1.5
      RIPL: 1.5
```

## Task-Based DCM (Future)

Not currently implemented. When available:

- B matrix will specify which connections are modulated by task inputs
- C vector will specify which regions receive external inputs
- Additional event specification will be required

## Output Interpretation

### Posterior Parameter Estimates

After estimation, `DCM.Ep` contains the mean posterior parameter values:

```
A[i,j] > 0  → region j drives region i
A[i,j] < 0  → inhibitory connection
|A[i,j]|    → connection strength
```

### Model Selection

When estimating multiple models:

```
DCM.F         % Free energy (model evidence)
p = exp(DCM.F)  % Posterior probability of model
```

Models with higher F provide better evidence and are preferred.

## Limitations & Warnings

### Task-Based DCM

```
spmx fmri /input /output --dcm --task rest --model full

WARNING: Using 'full' model with resting-state task.
         Consider using 'resting-state-full' instead.
```

The tool detects this common mistake and warns users.

### Model Assumptions

DCM assumes:
- Linear neuronal dynamics
- Linear state-to-BOLD mapping
- White noise measurement error
- Stationary fMRI signal

See SPM/DCM literature for detailed assumptions and limitations.

## References

- [SPM DCM Tutorial](https://www.fil.ion.ucl.ac.uk/spm/doc/)
- Friston KJ, et al. (2003). Dynamic causal modelling. NeuroImage, 19(4), 1273-1302.
- Stephan KE, et al. (2015). Computational approaches to neuroscience. Current Biology, 25(2), R69-R77.
