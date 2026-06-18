"""Default values for spmx parameters.

All defaults are organized by module and submodule, mirroring the config file
structure. These values are used when not overridden by the user config file.
"""

# ---------------------------------------------------------------------------
# SPM fMRI first-level model specification defaults
# ---------------------------------------------------------------------------
FMRI_FIT = {
    "fmri_t": 16,           # microtime resolution (number of time bins per scan)
    "fmri_t0": 8,           # microtime onset (reference time bin)
    "hpf": 128,             # high-pass filter cutoff in seconds
    "cond_tmod": 0,         # time modulation for conditions (0 = none)
    "cond_orth": 1,         # orthogonalise modulations (1 = yes)
    "write_residuals": 0,   # write residual images (0 = no)
    "regressors": None,     # confound regressor names (None = no regressors by default)
    "smooth": 0,            # Gaussian kernel FWHM in mm (0 = no smoothing)
}

# ---------------------------------------------------------------------------
# SPM fMRI VOI defaults
# ---------------------------------------------------------------------------
FMRI_VOI = {
    "radius": 8,  # default sphere radius in mm
}

# ---------------------------------------------------------------------------
# SPM fMRI DCM defaults
# ---------------------------------------------------------------------------
FMRI_DCM = {
    "default_delay": 1.5,  # default VOI delay in seconds
    "EchoTime": 0.04,      # default EchoTime in seconds if not found elsewhere
    "options": {
        "nonlinear": 0,
        "two_state": 0,
        "stochastic": 0,
        "centre": 0,
        "induced": 1,       # 1 = CSD (resting-state), 0 = timeseries (task)
    },
}

# ---------------------------------------------------------------------------
# Pre-defined DCM models
# ---------------------------------------------------------------------------
PREDEFINED_DCM_MODELS = {
    "full": {
        "description": "All parameters set to 1 in A, B and C.",
    },
    "resting-state-full": {
        "description": "All A set to 1, all B and C set to 0.",
    },
}
