# DCM Connectivity Export Feature

## Overview

When running `spmx fmri --dcm` with `analysis_level=participant`, the DCM module now automatically extracts and exports the endogenous connectivity matrix from DCM estimation results.

## Output Files

For each DCM estimation, two files are created in `OUTPUT_DIR/sub-SUB/[ses-SES/]func/`:

### 1. Connectivity Matrix (.npy)
- **Filename pattern**: `sub-SUB[_ses-SES]_[task-TASK][_space-SPACE]_desc-endogeneous_connectivity.npy`
- **Content**: The estimated A matrix (Ep.A) from DCM results
- **Format**: NumPy binary format (.npy)
- **Shape**: [N_regions × N_regions] where N_regions is the number of ROIs

### 2. Metadata Sidecar (.json)
- **Filename**: Same as .npy file but with .json extension
- **Content**: 
  - `ROINames`: List of region names
  - `ROICoordinates`: Coordinates of each ROI in MNI space
  - `MatrixDescription`: Explanation of matrix directionality and interpretation
  - `DCMFile`: Path to the original DCM_*.mat file

## Matrix Interpretation

The connectivity matrix A contains estimated **directed connectivity parameters**:
- **Rows** = FROM regions
- **Columns** = TO regions
- **A[i,j]** = directed connection strength FROM region i TO region j

**Important**: The interpretation depends on the DCM model and analysis:
- **Resting-state CSD analysis**: A contains intrinsic connectivity parameters
- **Task-based analysis**: A contains task-modulated connectivity if applicable

## Implementation Details

### Dependencies
- `scipy`: For loading MATLAB .mat files using `scipy.io.loadmat`
- `numpy`: For matrix operations and saving
- `json`: For metadata serialization

### Processing Flow
1. After DCM estimation completes, `_extract_and_save_connectivity()` is called
2. The function loads `DCM_<model>.mat` from the SPM working directory
3. Extracts `Ep.A` from the MATLAB structure
4. Validates matrix shape (must be 2D)
5. Saves as .npy with BIDS-compliant naming
6. Creates JSON sidecar with ROI metadata

### BIDS Naming Convention
The output follows BIDS naming conventions:
- Includes subject, session (if present), task, space, and description labels
- Task and space are extracted from command-line arguments if provided
- Example: `sub-001_task-rest_space-MNI152_desc-endogeneous_connectivity.npy`

## Usage Example

```bash
# Extract connectivity for resting-state data in native space
spmx fmri /data/fmriprep /data/derivatives participant --dcm \
    --model resting-state-full \
    --config dcm_config.yaml

# Extract connectivity for task data in MNI space
spmx fmri /data/fmriprep /data/derivatives participant --dcm \
    --model my_model \
    --task mytask \
    --space MNI152 \
    --config dcm_config.yaml
```

## Configuration

The seeds (ROIs) used in DCM are defined in the config file under `fmri.voi.seeds`:

```yaml
fmri:
  voi:
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
```

These seed definitions are automatically included in the exported JSON sidecar.

## Reading the Exported Data

### Python
```python
import numpy as np
import json

# Load connectivity matrix
A = np.load('sub-001_task-rest_desc-endogeneous_connectivity.npy')

# Load metadata
with open('sub-001_task-rest_desc-endogeneous_connectivity.json') as f:
    metadata = json.load(f)

roi_names = metadata['ROINames']  # ['PCC', 'mPFC', 'LIPL', ...]
roi_coords = metadata['ROICoordinates']
print(f"Matrix shape: {A.shape}")
print(f"ROI names: {roi_names}")
```

### MATLAB
```matlab
% Note: This is the .npy file exported from Python DCM results
A = readmatrix('sub-001_task-rest_desc-endogeneous_connectivity.npy', 'FileType', 'text');
% Or load via scipy if in Python environment
metadata = jsondecode(fileread('sub-001_task-rest_desc-endogeneous_connectivity.json'));
```

## Notes

- Connectivity export only occurs for **participant-level analysis** (group-level analysis export is future work)
- The A matrix contains **estimated parameters** and should be interpreted in context of the DCM model specification
- For model comparison, consider using the F (free energy) values in the original DCM_*.mat file
- Recommended post-processing includes visualization and statistical analysis appropriate to your research question
