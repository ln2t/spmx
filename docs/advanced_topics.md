# Advanced Topics & Implementation Details

Technical details about how spmx handles BIDS requirements, state management, and special considerations.

## BIDS Compliance Strategy

### The Input/Output Requirement

**Critical BIDS principle**: Input data must never be modified.

- INPUT_DIR contains preprocessed BIDS data (read-only)
- All modifications happen in OUTPUT_DIR
- This allows INPUT_DIR to serve as input to multiple pipelines

### Handling Uncompressed NIFTI Files

SPM requires uncompressed `.nii` files, but BIDS standard requires compressed `.nii.gz` files. The solution:

```
INPUT_DIR (read-only, all .nii.gz)
    ↓
Create sourcedata/ in OUTPUT_DIR
    ↓
Decompress input files into OUTPUT_DIR/sourcedata/
    ↓
SPM processes from sourcedata/
    ↓
Results in OUTPUT_DIR/sub-*/func/
    ↓
Rename outputs to BIDS conventions
    ↓
Compress final outputs (.nii.gz)
    ↓
Optional: Clean sourcedata/ with --clean-spm-files
```

### sourcedata/ Directory Structure

```
OUTPUT_DIR/sourcedata/
└── sub-001/
    └── ses-01/
        └── func/
            ├── sub-001_ses-01_task-rest_space-MNI_desc-preproc_bold.nii
            └── mask.nii
```

**Purpose**: Temporary working directory for uncompressed NIFTI files

**Cleanup**: Can be deleted after successful processing with `--clean-spm-files` flag

**When to keep**: During debugging or if repeating stages

## SPM.mat File Handling

### Location & Naming

The SPM.mat file requires special handling:

1. **Fit stage creates**: SPM.mat in OUTPUT_DIR/sub-*/func/
2. **BIDS compliance**: SPM.mat is kept as-is (exception to BIDS naming)
3. **Why**: Different tools expect consistent variable names inside
4. **Sidecar**: Accompanied by SPM.mat.json with metadata
5. **Persistence**: Required for subsequent VOI and DCM stages

### SPM.mat Contents

The SPM.mat file contains:

```matlab
SPM.stats       % Statistical model information
SPM.xX          % Design matrix and contrasts
SPM.xY          % BOLD data characteristics
SPM.nscan       % Number of volumes per session
SPM.xCon        % Contrast definitions
SPM.beta        % Estimated parameter indices
% ... other fields
```

### Copying Strategy

For subsequent stages (VOI, DCM):

1. SPM.mat from fit stage is in OUTPUT_DIR/sub-*/func/
2. VOI and DCM stages read this file (don't copy)
3. SPM batch system adds dependencies automatically

## Processing Status Tracking

### Optional: Processing Status Records

The tool optionally maintains a processing status file to track what has been completed:

```
OUTPUT_DIR/.processing_status_sub-001_ses-01
```

**Content**: JSON file tracking completed stages
```json
{
  "participant": "001",
  "session": "01",
  "fit": {"status": "completed", "timestamp": "2024-01-15T10:30:45Z"},
  "voi": {"status": "pending", "timestamp": null},
  "dcm": {"status": "pending", "timestamp": null}
}
```

**Purpose**: 
- Resume interrupted workflows
- Skip already-completed stages
- Track pipeline execution history

**Used by**: Tool to determine what stages need to re-run

## Batch Processing Multiple Subjects

### Parallel Processing Strategy

`spmx` processes one subject at a time, but can be parallelized:

```bash
# Process all subjects in parallel (outside spmx)
for sub in 001 002 003 004 005; do
  spmx fmri /input /output --fit \
    --participant-label $sub \
    --config config.yaml &
done
wait
```

**Advantages**:
- Faster overall execution
- Easy to distribute across compute cluster
- SPM remains single-threaded (per design)

**Requirements**:
- Sufficient MATLAB licenses for parallel runs
- Sufficient disk I/O bandwidth
- Shared OUTPUT_DIR (properly synchronized)

### Session Processing

Sessions are processed sequentially within each subject:

```
Subject 001:
  ├─ Session 01 (fit → voi → dcm)
  └─ Session 02 (fit → voi → dcm)
Subject 002:
  ├─ Session 01 (fit → voi → dcm)
  └─ Session 02 (fit → voi → dcm)
```

## BIDS Entity Filters

### Participant Selection

```bash
# All participants (default)
spmx fmri /input /output --fit

# Specific participants
spmx fmri /input /output --fit --participant-label 001 002 003

# Single participant
spmx fmri /input /output --fit --participant-label 001
```

**Implementation**: Uses pybids to discover subjects in input dataset

### Session Selection

```bash
# All sessions (default)
spmx fmri /input /output --fit

# Specific sessions
spmx fmri /input /output --fit --session 01 02

# Single session
spmx fmri /input /output --fit --session 01
```

**Note**: If data has no sessions, session filtering is ignored

### Task Selection

```bash
spmx fmri /input /output --fit --task rest
```

**Use case**: Only process resting-state data from mixed-task dataset

### Space Selection

```bash
spmx fmri /input /output --fit --space MNI152NLin2009cAsym
```

**Use case**: Handle multiple template spaces in input; process only MNI

## Event File Processing (Task-Based)

### Events File Format (BIDS)

Required file: `*_task-TASK_events.tsv`

```tsv
onset	duration	trial_type	response_time
1.2	2.0	face	1.435
3.5	2.0	house	1.523
5.8	2.0	tool	1.687
8.1	2.0	face	1.421
```

**Required columns**: 
- `onset` — stimulus time in seconds
- `duration` — stimulus duration in seconds
- `trial_type` — condition category

**Used by fit stage to**:
1. Build condition regressors from `trial_type` values
2. Extract onsets and durations for each condition
3. Create SPM batch specifications

### Condition Extraction Logic

```python
# User specifies conditions
--condition face house

# Tool:
# 1. Reads events.tsv
events = pd.read_csv('events.tsv', delimiter='\t')

# 2. Filters for specified trial types
face_events = events[events['trial_type'] == 'face']
house_events = events[events['trial_type'] == 'house']

# 3. Extracts onset and duration vectors
face_onsets = face_events['onset'].values
face_durations = face_events['duration'].values

# 4. Creates SPM condition specifications
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).name = 'face'
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).onset = face_onsets
matlabbatch{1}.spm.stats.fmri_spec.sess.cond(1).duration = face_durations
```

## Confounds File Processing

### Confounds File Format (BIDS)

From fMRIPrep processing: `*_desc-confounds_timeseries.tsv`

```tsv
trans_x	trans_y	trans_z	rot_x	rot_y	rot_z	csf	white_matter	...
0.012	-0.005	0.023	0.001	-0.002	0.003	500.12	400.45	...
0.015	-0.004	0.021	0.002	-0.001	0.004	502.34	401.23	...
```

### Confound Selection Logic

```python
# User specifies confounds
--confound trans_x trans_y trans_z rot_x rot_y rot_z csf

# Tool:
# 1. Reads confounds file
confounds = pd.read_csv('confounds_timeseries.tsv', delimiter='\t')

# 2. Extracts specified columns
selected = confounds[['trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z', 'csf']]

# 3. Checks for length match with BOLD volumes
n_volumes = get_nifti_n_volumes(bold_file)
assert len(selected) == n_volumes, "Confound vector length mismatch"

# 4. Creates SPM regressor specifications
matlabbatch{1}.spm.stats.fmri_spec.sess.regress(1).name = 'trans_x'
matlabbatch{1}.spm.stats.fmri_spec.sess.regress(1).val = selected['trans_x'].values
```

## Volume Count Determination

### Getting NIFTI Dimensions

```python
import nibabel as nib

# Load NIFTI file
img = nib.load('bold.nii.gz')
shape = img.shape  # e.g., (100, 100, 50, 400)

# Extract number of volumes (4th dimension)
n_volumes = shape[3]  # 400 volumes
```

### Creating Scan List for SPM

SPM requires full path specification with volume index:

```matlab
matlabbatch{1}.spm.stats.fmri_spec.sess.scans = {
  '/path/to/bold.nii,1'
  '/path/to/bold.nii,2'
  '/path/to/bold.nii,3'
  % ... repeated for all N volumes
  '/path/to/bold.nii,400'
}
```

### Implementation

```python
scans = []
for vol_idx in range(1, n_volumes + 1):
    scan_path = f'{nifti_path},{vol_idx}'
    scans.append(scan_path)

matlabbatch_scan_list = scans
```

## Echo Time (TE) Metadata

### Where TE Comes From

```python
# Fit stage: Read from preprocessed BOLD JSON
bold_json = json.load(open('bold.json'))
te = bold_json['EchoTime']  # e.g., 0.035 seconds

# DCM stage: Must read original parameters (not in SPM.mat)
# Store in JSON sidecar of SPM.mat, or retrieve from original metadata
```

### DCM TE Requirement

```matlab
% DCM requires echo time in seconds
DCM.TE = 0.035  % Echo time in seconds
```

## Default Parameter Selection

### When Defaults Apply

1. **User doesn't specify parameter** in config or CLI
2. **Parameter not in config file**
3. **Not overridden by CLI argument**
4. → **Use value from defaults.py**

### Defaults in Code

```python
# spmx/defaults.py
FMRI_FIT = {
    "fmri_t": 16,
    "fmri_t0": 8,
    "hpf": 128,
    "cond_tmod": 0,
    "cond_orth": 1,
    "write_residuals": 0,
    "regressors": None,
}

FMRI_VOI = {
    "radius": 8,
}

FMRI_DCM = {
    "default_delay": 1.5,
    "EchoTime": 0.04,
    "options": {
        "nonlinear": 0,
        "two_state": 0,
        "stochastic": 0,
        "centre": 0,
        "induced": 1,
    },
}
```

## Logging System

### Log Levels

- **INFO**: Standard operation; pipeline progress
- **DEBUG**: Detailed execution; MATLAB scripts; parameter values (enable with `--debug`)
- **WARNING**: Non-fatal issues; potential problems
- **ERROR**: Fatal issues; pipeline stop

### Log Locations

```
OUTPUT_DIR/
├── logs/
│   ├── pipeline.log          # Main log (all stages)
│   └── sub-001/
│       ├── ses-01/
│       │   ├── fit.log       # Fit stage per subject/session
│       │   ├── voi.log       # VOI stage per subject/session
│       │   ├── dcm.log       # DCM stage per subject/session
│       │   └── matlab_scripts/  # Generated MATLAB code (debug only)
│       │       ├── 01_fmri_spec.m
│       │       ├── 02_fmri_est.m
│       │       ├── 03_con.m
│       │       ├── 04_voi_*.m
│       │       └── 05_dcm_*.m
```

### Enabling Debug Mode

```bash
spmx fmri /input /output --fit --debug --config config.yaml
```

**Effects**:
- Verbose terminal output (DEBUG level)
- Saves MATLAB scripts in logs/
- More detailed error messages
- Slightly slower execution (no performance impact)

## Error Handling & Recovery

### Common Failure Points

1. **MATLAB not found** → Set `--matlab-path`
2. **No subjects found** → Check BIDS structure with BIDS Validator
3. **Confound column missing** → Verify confound names exactly match
4. **Volume count mismatch** → Check confound and events file lengths
5. **VOI extraction fails** → Ensure fit stage completed successfully

### Recovery Strategies

1. **Check logs** in OUTPUT_DIR/logs/
2. **Run with `--debug`** to see MATLAB scripts
3. **Verify input data** with BIDS Validator
4. **Start with simpler setup** (e.g., skip confounds first)
5. **Check disk space** and file permissions

## Performance Tuning

### SPM Processing Times (Approximate)

- **Fit**: 2-5 minutes per subject
- **VOI**: <1 minute per subject
- **DCM**: 5-30 minutes per model per subject

### Optimization Tips

1. **Parallel subjects**: Run different subjects concurrently (outside tool)
2. **Reduce write_residuals**: Keeps write_residuals=0 (default)
3. **Limit confounds**: Include only necessary regressors
4. **Increase fmri_t**: Increases processing time; default (16) is usually fine
5. **Resource allocation**: Ensure sufficient RAM for large datasets

## Related Documentation

- [Configuration Guide](configuration.md)
- [MATLAB Templates](matlab_templates.md)
- [Output File Mapping](outputs.md)
- [DCM Specification](dcm_specification.md)
