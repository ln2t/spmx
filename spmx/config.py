"""Configuration loader for spmx.

Loads a YAML config file and merges with defaults. CLI arguments take
precedence over config file values, which take precedence over defaults.
"""

import os
import shutil
from pathlib import Path

import yaml

from spmx import defaults


def load_config(config_path=None, matlab_path=None, spm_path=None):
    """Load configuration from YAML file, merged with defaults.

    Parameters
    ----------
    config_path : Path or None
        Path to YAML config file. If None, use defaults only.
    matlab_path : Path or None
        CLI override for MATLAB executable path.
    spm_path : Path or None
        CLI override for SPM installation path.

    Returns
    -------
    dict
        Merged configuration dictionary.
    """
    cfg = {}
    if config_path is not None:
        config_path = Path(config_path)
        if not config_path.is_file():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh) or {}

    # Resolve MATLAB path
    if matlab_path is not None:
        cfg["matlab_path"] = str(matlab_path)
    elif "matlab_path" not in cfg:
        found = shutil.which("matlab")
        if found:
            cfg["matlab_path"] = found
        else:
            cfg["matlab_path"] = "matlab"  # hope it's on PATH at runtime

    # Resolve SPM path
    if spm_path is not None:
        cfg["spm_path"] = str(spm_path)
    elif "spm_path" not in cfg:
        matlab_root = os.environ.get("MATLABPATH", "")
        if matlab_root:
            cfg["spm_path"] = str(Path(matlab_root) / "toolboxes" / "spm")
        else:
            cfg["spm_path"] = ""

    # Merge fmri.fit defaults
    fmri_cfg = cfg.setdefault("fmri", {})
    fit_cfg = fmri_cfg.setdefault("fit", {})
    for key, val in defaults.FMRI_FIT.items():
        fit_cfg.setdefault(key, val)

    # Merge fmri.voi defaults
    voi_cfg = fmri_cfg.setdefault("voi", {})
    voi_cfg.setdefault("radius", defaults.FMRI_VOI["radius"])

    # Merge fmri.dcm defaults
    dcm_cfg = fmri_cfg.setdefault("dcm", {})
    dcm_cfg.setdefault("radius", defaults.FMRI_VOI["radius"])
    dcm_opts = dcm_cfg.setdefault("options", {})
    # options may be a list of dicts (from YAML) or a dict
    if isinstance(dcm_opts, list):
        merged = {}
        for item in dcm_opts:
            if isinstance(item, dict):
                merged.update(item)
        dcm_cfg["options"] = merged
        dcm_opts = dcm_cfg["options"]
    for key, val in defaults.FMRI_DCM["options"].items():
        dcm_opts.setdefault(key, val)
    dcm_cfg.setdefault("default_delay", defaults.FMRI_DCM["default_delay"])

    return cfg


def get_fit_param(config, key):
    """Get a parameter from the fmri.fit section of the config."""
    return config.get("fmri", {}).get("fit", {}).get(key, defaults.FMRI_FIT.get(key))


def get_dcm_option(config, key):
    """Get a DCM option value."""
    return (
        config.get("fmri", {})
        .get("dcm", {})
        .get("options", {})
        .get(key, defaults.FMRI_DCM["options"].get(key))
    )


def get_dcm_param(config, key):
    """Get a DCM parameter value (top-level, not in options)."""
    return (
        config.get("fmri", {})
        .get("dcm", {})
        .get(key, defaults.FMRI_DCM.get(key))
    )
