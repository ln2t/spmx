"""fMRI DCM (Dynamic Causal Modeling) submodule.

Handles specification and estimation of participant-level DCM models.
Currently focused on resting-state DCM (CSD analysis type).

Workflow:
1. Build DCM structure in MATLAB from config + input data
2. Save DCM.mat
3. Run SPM DCM estimation via matlabbatch
4. Extract and save connectivity matrices (participant level)
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from spmx.bids_utils import (
    build_bids_filename,
    load_json_metadata,
    update_processing_status,
    write_json_sidecar,
)
from spmx.config import get_dcm_option, get_dcm_param
from spmx.defaults import FMRI_DCM, PREDEFINED_DCM_MODELS
from spmx.logging_setup import get_file_handler
from spmx.matlab_runner import generate_matlab_script, run_matlab_script
from spmx.spm_utils import (
    setup_log_dir,
)


def run_dcm(args, config, logger):
    """Run DCM specification and estimation.

    Parameters
    ----------
    args : argparse.Namespace
    config : dict
    logger : logging.Logger
    """
    output_dir = Path(args.output_dir).resolve()

    # Get all VOI seeds
    voi_cfg = config.get("fmri", {}).get("voi", {})
    all_voi_seeds = voi_cfg.get("seeds", [])
    if not all_voi_seeds:
        logger.error("No seeds defined in config (fmri.voi.seeds).")
        sys.exit(1)

    # Check if DCM specifies a subset of seeds
    dcm_cfg = config.get("fmri", {}).get("dcm", {})
    dcm_seed_names = dcm_cfg.get("seeds", [])

    if dcm_seed_names:
        # Filter to only the seeds specified in DCM config
        dcm_seed_names_set = set(dcm_seed_names)
        seeds = [s for s in all_voi_seeds if s["name"] in dcm_seed_names_set]
        if not seeds:
            logger.error(
                "No seeds in fmri.dcm.seeds matched any seeds in fmri.voi.seeds."
            )
            sys.exit(1)
        logger.info(
            "Using %d seeds from fmri.dcm.seeds (subset of %d fmri.voi.seeds)",
            len(seeds), len(all_voi_seeds)
        )
    else:
        # Use all VOI seeds
        seeds = all_voi_seeds
        logger.info("Using all %d seeds from fmri.voi.seeds", len(seeds))

    n_seeds = len(seeds)
    seed_names = [s["name"] for s in seeds]

    # Collect models to estimate
    models = _collect_models(args, config, seed_names, n_seeds, logger)
    if not models:
        logger.error("No DCM models specified (use --model or config file).")
        sys.exit(1)

    logger.info("DCM models to estimate: %s", [m["name"] for m in models])

    # Discover subjects from output directory structure
    if getattr(args, "participant_label", None):
        subjects = list(args.participant_label)
    else:
        subjects = sorted([
            d.name.replace("sub-", "")
            for d in output_dir.glob("sub-*")
            if d.is_dir()
        ])

    if not subjects:
        logger.error("No subjects found in %s", output_dir)
        sys.exit(1)

    for subject in subjects:
        sub_dir = output_dir / f"sub-{subject}"
        if getattr(args, "session", None):
            sessions = list(args.session)
        else:
            sessions = sorted([
                d.name.replace("ses-", "")
                for d in sub_dir.glob("ses-*")
                if d.is_dir()
            ])
        if not sessions:
            sessions = [None]

        for session in sessions:
            for model in models:
                _run_dcm_single(
                    subject, session, model, seeds,
                    output_dir, args, config, logger,
                )


def _collect_models(args, config, seed_names, n_seeds, logger):
    """Collect DCM model definitions from CLI and/or config.

    Returns
    -------
    list of dict
        Each dict has keys: name, A, B, C.
    """
    models = []

    # From config file
    dcm_cfg = config.get("fmri", {}).get("dcm", {})
    config_models = dcm_cfg.get("models", [])
    for m in config_models:
        models.append({
            "name": m["name"],
            "A": np.array(m["A"], dtype=int),
            "B": np.array(m["B"], dtype=int),
            "C": np.array(m["C"], dtype=int),
        })

    # From --model CLI option and/or config file fmri.dcm.model (predefined name)
    cli_models = getattr(args, "model", None) or []
    config_model_name = dcm_cfg.get("model")
    if config_model_name and not cli_models:
        cli_models = [config_model_name]
    tasks = getattr(args, "task", None) or []

    for model_name in cli_models:
        if model_name == "full":
            is_resting_state = "restingstate" in tasks or "rest" in tasks
            if is_resting_state:
                logger.error(
                    "The 'full' model requires task-based (non-resting-state) data. "
                    "For resting-state DCM, use 'resting-state-full' instead. "
                    "Or use non-resting-state task names (e.g., --task mytask)."
                )
                sys.exit(1)
            models.append({
                "name": "full",
                "A": np.ones((n_seeds, n_seeds), dtype=int),
                "B": np.ones((n_seeds, n_seeds), dtype=int),
                "C": np.ones(n_seeds, dtype=int),
                "is_task_based": True,
            })
        elif model_name == "resting-state-full":
            models.append({
                "name": "resting-state-full",
                "A": np.ones((n_seeds, n_seeds), dtype=int),
                "B": np.zeros((n_seeds, n_seeds), dtype=int),
                "C": np.zeros(n_seeds, dtype=int),
            })
        else:
            logger.error("Unknown pre-defined model: %s", model_name)
            sys.exit(1)

    return models


def _run_dcm_single(subject, session, model, seeds,
                    output_dir, args, config, logger):
    """Run DCM for one subject/session/model."""
    sess_str = f"sub-{subject}" + (f"/ses-{session}" if session else "")
    model_name = model["name"]
    is_task_based = model.get("is_task_based", False)
    model_type = "task-based" if is_task_based else "resting-state"
    logger.info("DCM: %s, model=%s (%s)", sess_str, model_name, model_type)

    log_dir = setup_log_dir(output_dir, subject, session)
    fh = get_file_handler(log_dir / f"dcm_{model_name}.log")
    logger.addHandler(fh)

    try:
        _dcm_core(
            subject, session, model, seeds,
            output_dir, args, config, logger,
        )
        # Mark subject/session as completed dcm stage (task-agnostic)
        update_processing_status(output_dir, subject, session, "dcm", task=None)
    finally:
        logger.removeHandler(fh)
        fh.close()


def _dcm_core(subject, session, model, seeds,
              output_dir, args, config, logger):
    """Core DCM logic: build DCM struct, save, then estimate."""
    entities = {"sub": subject}
    if session:
        entities["ses"] = session
    entities["model"] = model["name"]

    dcm_cfg = config.get("fmri", {}).get("dcm", {})
    seed_names = [s["name"] for s in seeds]
    n_seeds = len(seeds)

    # Find SPM.mat in the SPM subfolder
    spm_func_dir = output_dir / f"sub-{subject}"
    if session:
        spm_func_dir = spm_func_dir / f"ses-{session}"
    spm_func_dir = spm_func_dir / "func"
    
    spm_dir = spm_func_dir / "SPM"

    spm_mat_path = spm_dir / "SPM.mat"
    if not spm_mat_path.exists():
        logger.error("  SPM.mat not found at %s. Run --fit first.", spm_mat_path)
        return
    logger.info("  SPM.mat: %s", spm_mat_path)

    # Find VOI files directly in the SPM working directory
    voi_paths = {}
    for seed in seeds:
        voi_candidates = list(spm_dir.glob(f"VOI_{seed['name']}*.mat"))
        if not voi_candidates:
            logger.error("  VOI file not found for seed %s. Run --voi first.", seed["name"])
            return
        voi_paths[seed["name"]] = voi_candidates[0]
        logger.info("  VOI for %s: %s", seed["name"], voi_candidates[0])

    # Find EchoTime from multiple sources:
    # 1. BIDS-named SPM.mat JSON sidecar (from first-level processing)
    # 2. Config file (fmri.dcm.EchoTime)
    # 3. Default value (0.04) if not found in either source
    spm_jsons = sorted(spm_dir.glob("*_SPMmat.json"))
    spm_meta = load_json_metadata(spm_jsons[0]) if spm_jsons else {}
    echo_time = spm_meta.get("EchoTime")
    
    if echo_time is None:
        # Try to get from config
        config_echo_time = dcm_cfg.get("EchoTime")
        if config_echo_time is not None:
            echo_time = config_echo_time
            logger.info("  EchoTime not found in SPM.mat sidecar. Using value from config: %.4f", echo_time)
        else:
            # Fall back to default with warning
            echo_time = FMRI_DCM["EchoTime"]
            logger.warning(
                "  EchoTime not found in SPM.mat sidecar or config file (fmri.dcm.EchoTime). "
                "Using default value: %.4f. "
                "Consider adding 'EchoTime' to your config file under 'fmri.dcm' for accurate DCM results.",
                echo_time
            )

    # Build delays vector
    delays_cfg = dcm_cfg.get("delays", [])
    default_delay = dcm_cfg.get("default_delay", FMRI_DCM["default_delay"])
    delays = []
    delays_map = {}
    if isinstance(delays_cfg, list):
        for item in delays_cfg:
            if isinstance(item, dict):
                delays_map.update(item)
    for sn in seed_names:
        delays.append(delays_map.get(sn, default_delay))

    # Determine analysis type EARLY (before dcm_options) to set consistent options
    # - For task-based "full" model: default to 'timeseries' (task DCM)
    # - For resting-state models: default to 'csd' (resting-state DCM)
    # - Allow override via config fmri.dcm.analysis
    is_task_based = model.get("is_task_based", False)
    if dcm_cfg.get("analysis"):
        # User explicitly specified analysis type in config
        analysis_type = dcm_cfg.get("analysis")
    elif is_task_based:
        # Task-based models use timeseries analysis
        analysis_type = "timeseries"
    else:
        # Resting-state models use CSD analysis
        analysis_type = "csd"
    
    logger.info("  Analysis type: %s", analysis_type)

    # DCM options
    # NOTE: induced option must match analysis type:
    # - induced=0: timeseries (task-based DCM)
    # - induced=1: CSD/induced (resting-state DCM)
    # IMPORTANT: Always auto-set induced from analysis_type, unless explicitly overridden in config
    # The induced flag in dcm_cfg.options might be a default - we only respect it if it was
    # explicitly set by the user (we can't distinguish, so we prefer analysis_type auto-detect)
    dcm_options = {
        "nonlinear": get_dcm_option(config, "nonlinear"),
        "two_state": get_dcm_option(config, "two_state"),
        "stochastic": get_dcm_option(config, "stochastic"),
        "centre": get_dcm_option(config, "centre"),
    }
    
    # For induced: ALWAYS auto-set based on analysis_type to ensure consistency
    # If user REALLY wants to override, they should explicitly set both:
    # - fmri.dcm.analysis: "timeseries"
    # - fmri.dcm.options.induced: 1  (only if they know what they're doing)
    dcm_options["induced"] = 0 if analysis_type == "timeseries" else 1
    logger.info("  Set induced=%d (auto-detected from analysis_type=%s)", dcm_options["induced"], analysis_type)
    
    # Only log if user explicitly tried to set a conflicting value in config
    config_induced = dcm_cfg.get("options", {}).get("induced")
    if config_induced is not None and config_induced != dcm_options["induced"]:
        logger.warning(
            "  Config specifies fmri.dcm.options.induced=%d but analysis_type=%s requires induced=%d. "
            "Using auto-detected value %d. To override, ensure both fmri.dcm.analysis and fmri.dcm.options.induced are consistent.",
            config_induced, analysis_type, dcm_options["induced"], dcm_options["induced"]
        )

    # Log directory
    log_dir = setup_log_dir(output_dir, subject, session)

    # Build MATLAB code to create DCM struct and save it
    dcm_mat_name = f"DCM_{model['name']}.mat"
    dcm_mat_path = spm_dir / dcm_mat_name

    pre_code = _build_dcm_struct_matlab(
        spm_mat_path=spm_mat_path,
        voi_paths=voi_paths,
        seed_names=seed_names,
        model=model,
        delays=delays,
        echo_time=echo_time,
        dcm_options=dcm_options,
        n_seeds=n_seeds,
        save_path=dcm_mat_path,
        spm_dir=spm_dir,
        logger=logger,
    )

    # Load the estimation template
    template_dir = Path(__file__).parent.parent / "templates"
    est_template = (template_dir / "fmri_dcm_estimate.m").read_text()
    est_code = est_template.replace("%%DCM_MAT_PATH%%", str(dcm_mat_path))
    est_code = est_code.replace("%%OUTPUT_DIR%%", str(spm_dir))
    est_code = est_code.replace("%%MODEL_NAME%%", model["name"])
    
    # NOTE: analysis_type already determined earlier (before dcm_options)
    # to ensure DCM.options.induced matches the matlabbatch analysis type
    est_code = est_code.replace("%%ANALYSIS_TYPE%%", f"'{analysis_type}'")

    script = generate_matlab_script(
        spm_path=config.get("spm_path", ""),
        matlabbatch_code=est_code,
        pre_code=pre_code,
        clean_path=config.get("clean_matlab_path", False),
        logger=logger,
    )

    logger.info("  Launching MATLAB for DCM estimation...")
    run_matlab_script(
        script,
        matlab_path=config.get("matlab_path", "matlab"),
        work_dir=spm_dir,
        logger=logger,
        log_script_path=log_dir / f"dcm_{model['name']}.m",
        single_comp_thread=config.get("single_comp_thread", False),
        clean_path=config.get("clean_matlab_path", False),
    )
    logger.info("  MATLAB completed.")

    # DCM output (DCM_<model>.mat) is left in the SPM subfolder with its original name
    if dcm_mat_path.exists():
        logger.info("  DCM output created: %s", dcm_mat_path)
        
        # Extract and save connectivity matrices (participant level only)
        if getattr(args, "analysis_level", None) == "participant":
            _extract_and_save_connectivity(
                subject, session, dcm_mat_path, seeds, output_dir, args, logger
            )
    else:
        logger.warning("  DCM output file not found after estimation.")


def _extract_and_save_connectivity(subject, session, dcm_mat_path, seeds, output_dir, args, logger):
    """Extract endogenous connectivity matrix from DCM results and save as BIDS files.
    
    Extracts Ep.A (estimated endogenous connectivity) from DCM_*.mat file and saves:
    1. .npy file with the connectivity matrix
    2. .json sidecar with ROI metadata
    
    Parameters
    ----------
    subject : str
        Subject label (without 'sub-' prefix)
    session : str or None
        Session label (without 'ses-' prefix)
    dcm_mat_path : Path
        Path to DCM_*.mat file
    seeds : list of dict
        List of seed definitions from config (each with name, x, y, z, etc.)
    output_dir : Path
        OUTPUT_DIR root
    args : argparse.Namespace
        Command-line arguments
    logger : logging.Logger
    """
    try:
        # Load DCM results
        dcm_data = loadmat(str(dcm_mat_path), squeeze_me=False)
        
        # Extract Ep.A (estimated parameters for connectivity)
        if 'Ep' not in dcm_data:
            logger.warning("  Ep not found in DCM results. Skipping connectivity export.")
            return
        
        ep_data = dcm_data['Ep']
        A_matrix = None
        
        # scipy.io.loadmat creates structured arrays for MATLAB structures.
        # The Ep variable is typically a 1x1 structured array with named fields.
        try:
            if isinstance(ep_data, np.ndarray):
                if ep_data.dtype.names and 'A' in ep_data.dtype.names:
                    # ep_data is a structured array with an 'A' field
                    # Extract it - handle both 1D and multi-dimensional structured arrays
                    A_field = ep_data['A']
                    if A_field.size == 1 and isinstance(A_field.flat[0], np.ndarray):
                        A_matrix = A_field.flat[0]
                    else:
                        A_matrix = A_field
                else:
                    # Try accessing as object array (1x1 array containing a dict-like object)
                    if ep_data.size == 1:
                        ep_struct = ep_data.flat[0]
                        if isinstance(ep_struct, tuple) and len(ep_struct) > 0:
                            # ep_struct is a tuple of values, check for A matrix
                            # For structured arrays, ep_struct[0] is typically A if it's the first field
                            if isinstance(ep_struct[0], np.ndarray):
                                A_matrix = ep_struct[0]
                        elif isinstance(ep_struct, dict):
                            A_matrix = ep_struct.get('A')
        except (IndexError, KeyError, AttributeError, TypeError):
            pass
        
        if A_matrix is None:
            logger.warning("  Could not extract A matrix from Ep in DCM results. Skipping connectivity export.")
            return
        
        # Ensure it's a 2D numpy array and extract from object arrays if needed
        if isinstance(A_matrix, np.ndarray) and A_matrix.dtype == np.object_:
            # A_matrix might be a 0-D object array
            if A_matrix.size == 1:
                A_matrix = A_matrix.item()
        
        A_matrix = np.asarray(A_matrix).squeeze()
        
        # Validate shape
        if A_matrix.ndim < 2:
            logger.warning("  Extracted A matrix has unexpected shape: %s. Expected 2D matrix.", A_matrix.shape)
            return
        
        # For safety, take only the first 2D slice if higher dimensional
        if A_matrix.ndim > 2:
            logger.warning("  A matrix has %d dimensions, using first 2D slice", A_matrix.ndim)
            A_matrix = A_matrix[0, :, :]
        
        # Build output path and filename
        spm_func_dir = output_dir / f"sub-{subject}"
        if session:
            spm_func_dir = spm_func_dir / f"ses-{session}"
        spm_func_dir = spm_func_dir / "func"
        spm_func_dir.mkdir(parents=True, exist_ok=True)
        
        # Build BIDS filename with entities
        entities = {"sub": subject}
        if session:
            entities["ses"] = session
        
        # Add task if available from args
        task = getattr(args, "task", None)
        if task:
            if isinstance(task, list):
                entities["task"] = task[0]
            else:
                entities["task"] = task
        
        # Add space if available from args
        space = getattr(args, "space", None)
        if space:
            if isinstance(space, list):
                entities["space"] = space[0]
            else:
                entities["space"] = space
        
        # Create filename with desc-endogeneous_connectivity
        filename = build_bids_filename(entities, "connectivity", ".npy", description="endogeneous")
        npy_path = spm_func_dir / filename
        
        # Save connectivity matrix as numpy file
        np.save(str(npy_path), A_matrix)
        logger.info("  Connectivity matrix (Ep.A) saved: %s (shape=%s)", npy_path, A_matrix.shape)
        
        # Create JSON sidecar with metadata
        roi_names = [s["name"] for s in seeds]
        roi_coords = [[s.get("x", 0), s.get("y", 0), s.get("z", 0)] for s in seeds]
        
        metadata = {
            "ROINames": roi_names,
            "ROICoordinates": {
                roi_names[i]: {
                    "MNI": roi_coords[i]
                } for i in range(len(roi_names))
            },
            "MatrixDescription": {
                "DirectionalityConvention": "row=FROM, column=TO",
                "Interpretation": "Each element A[i,j] represents the directed connection FROM region i TO region j",
                "Note": "The A matrix contains endogenous (intrinsic) directed connectivity parameters estimated by DCM"
            },
            "DCMFile": str(dcm_mat_path),
        }
        
        json_path = npy_path.with_suffix(".json")
        with open(json_path, "w") as fh:
            json.dump(metadata, fh, indent=2)
        logger.info("  Connectivity metadata saved: %s", json_path)
        
    except Exception as e:
        logger.warning("  Failed to extract connectivity matrix: %s", str(e))


def _extract_task_regressors(spm_mat_path, logger):
    """Extract task regressor names and attempt to identify task columns from SPM.mat.
    
    SPM.xX structure typically contains:
    - SPM.xX.X: design matrix [nvols x nregressors]
    - SPM.xX.Xnames: cell array of regressor names
    - SPM.xX.iC: indices of condition regressors (our task regressors)
    - SPM.xX.iH: indices of confound regressors
    - SPM.xX.iG: indices of global nuisance regressors
    
    For "full" model with task-based DCM, we need the task condition regressors.
    
    Parameters
    ----------
    spm_mat_path : Path
        Path to SPM.mat file
    logger : logging.Logger
    
    Returns
    -------
    dict with keys:
        - 'task_column_indices': list of column indices for task regressors
        - 'task_names': list of corresponding regressor names
        - 'description': str describing what was found
    """
    try:
        spm_data = loadmat(str(spm_mat_path), squeeze_me=False)
        
        if 'SPM' not in spm_data:
            logger.warning("  SPM.mat does not contain 'SPM' variable. Cannot extract task regressors.")
            return {'task_column_indices': [], 'task_names': [], 'description': 'SPM structure not found'}
        
        spm = spm_data['SPM']
        
        # Handle numpy structured array (SPM is typically 1x1 structured array)
        if isinstance(spm, np.ndarray) and spm.dtype.names:
            # It's a structured array
            if spm.size == 1:
                spm_dict = {name: spm[name].item() if spm[name].size == 1 else spm[name]
                           for name in spm.dtype.names}
            else:
                logger.warning("  SPM variable has unexpected shape (not 1x1 structured array)")
                return {'task_column_indices': [], 'task_names': [], 'description': 'SPM shape unexpected'}
        else:
            logger.warning("  SPM variable format not recognized as structured array")
            return {'task_column_indices': [], 'task_names': [], 'description': 'SPM format not recognized'}
        
        # Access xX structure
        if 'xX' not in spm_dict:
            logger.warning("  SPM.xX not found in SPM.mat")
            return {'task_column_indices': [], 'task_names': [], 'description': 'SPM.xX not found'}
        
        xX = spm_dict['xX']
        
        # Extract Xnames (regressor names)
        task_names = []
        if isinstance(xX, np.ndarray) and xX.dtype.names and 'Xnames' in xX.dtype.names:
            xnames_raw = xX['Xnames'].item() if xX.size == 1 else xX['Xnames']
            if isinstance(xnames_raw, np.ndarray):
                # Cell array of strings - convert
                for name in xnames_raw.flat:
                    if isinstance(name, np.ndarray):
                        # String stored as array
                        name_str = ''.join(chr(c) for c in name if isinstance(c, (int, np.integer)) and 0 < c < 127)
                    else:
                        name_str = str(name)
                    task_names.append(name_str)
        
        # Try to get iC (condition indices) which should point to task regressors
        task_indices = []
        if isinstance(xX, np.ndarray) and xX.dtype.names and 'iC' in xX.dtype.names:
            iC_raw = xX['iC'].item() if xX.size == 1 else xX['iC']
            if isinstance(iC_raw, np.ndarray):
                task_indices = [int(i) - 1 for i in iC_raw.flat]  # Convert 1-indexed to 0-indexed
        
        if not task_indices and task_names:
            # Fallback: assume all names except known confounds are task regressors
            # Exclude: motion params, polynomial drift, intercept
            exclude_patterns = ['motion', 'drift', 'constant', 'intercept', 'csf', 'white_matter']
            task_indices = [i for i, name in enumerate(task_names)
                           if not any(pat.lower() in name.lower() for pat in exclude_patterns)]
        
        logger.info("  Found %d potential task regressors: %s", 
                   len(task_indices), [task_names[i] if i < len(task_names) else f'col{i}' for i in task_indices])
        
        return {
            'task_column_indices': task_indices,
            'task_names': [task_names[i] if i < len(task_names) else f'col{i}' for i in task_indices],
            'description': f'Extracted {len(task_indices)} task regressors from SPM.xX'
        }
        
    except Exception as e:
        logger.warning("  Error extracting task regressors: %s", str(e))
        return {'task_column_indices': [], 'task_names': [], 'description': f'Extraction error: {str(e)}'}


def _build_dcm_struct_matlab(spm_mat_path, voi_paths, seed_names, model,
                             delays, echo_time, dcm_options, n_seeds,
                             save_path, spm_dir=None, logger=None):
    """Generate MATLAB code to construct and save the DCM structure.
    
    For task-based "full" models, extracts task regressors from SPM.xX.
    For resting-state models, uses null input convention.

    Parameters
    ----------
    spm_mat_path : Path
        Path to SPM.mat file
    voi_paths : dict
        Mapping of seed names to VOI file paths
    seed_names : list
        List of seed/ROI names
    model : dict
        Model definition with keys: name, A, B, C, is_task_based (optional)
    delays : list
        Hemodynamic delays for each seed
    echo_time : float
        Echo time in seconds
    dcm_options : dict
        DCM estimation options
    n_seeds : int
        Number of seeds/ROIs
    save_path : Path
        Where to save the DCM.mat file
    spm_dir : Path, optional
        SPM working directory (used for logging)
    logger : logging.Logger, optional
        Logger instance

    Returns
    -------
    str
        MATLAB code (to be placed before the matlabbatch).
    """
    lines = []
    lines.append(f"% Load SPM.mat")
    lines.append(f"load('{spm_mat_path}');")
    lines.append("")

    # Load VOIs
    for idx, sn in enumerate(seed_names):
        vp = voi_paths[sn]
        lines.append(f"VOI_data = load('{vp}');")
        lines.append(f"% Handle both direct xY and wrapped structures")
        lines.append(f"if isfield(VOI_data, 'xY')")
        lines.append(f"  VOI{idx + 1}_xY = VOI_data.xY;")
        lines.append(f"else")
        lines.append(f"  % Try to find the main variable")
        lines.append(f"  fieldnames_voi = fieldnames(VOI_data);")
        lines.append(f"  if numel(fieldnames_voi) > 0")
        lines.append(f"    VOI{idx + 1}_xY = VOI_data.(fieldnames_voi{1});")
        lines.append(f"  else")
        lines.append(f"    error('VOI file does not contain expected structure');")
        lines.append(f"  end")
        lines.append(f"end")
    lines.append("")

    lines.append(f"Nvol = SPM.nscan;")
    lines.append(f"N = {n_seeds};")
    lines.append("")

    # A, B, C, d
    a_str = _numpy_to_matlab_matrix(model["A"])
    b_str = _numpy_to_matlab_matrix(model["B"])
    c_vec = model["C"]
    c_str = "[" + " ".join(str(int(v)) for v in c_vec) + "]"

    lines.append(f"DCM.a = {a_str};")
    lines.append(f"DCM.b = {b_str};")
    lines.append(f"DCM.c = {c_str};")
    lines.append(f"DCM.d = [];")
    lines.append("")

    # xY
    for idx, sn in enumerate(seed_names):
        lines.append(f"DCM.xY({idx + 1}) = VOI{idx + 1}_xY;")
    lines.append("")

    # U (exogeneous inputs)
    is_task_based = model.get("is_task_based", False)
    
    if is_task_based and spm_dir and logger:
        # For task-based DCM: extract task regressors from SPM.xX
        lines.extend([
            "% For task-based DCM: use task regressors as exogenous inputs",
            "% Extract task regressors from SPM.xX design matrix",
            "if isfield(SPM, 'xX') && isfield(SPM.xX, 'iC')",
            "  % iC contains indices of condition (task) regressors",
            "  task_idx = SPM.xX.iC;",
            "  if ~isempty(task_idx)",
            "    % Extract columns corresponding to task conditions",
            "    DCM.U.u = SPM.xX.X(:, task_idx);  % Task regressors as columns",
            "    % Get task regressor names from SPM.xX.Xnames",
            "    if isfield(SPM.xX, 'Xnames')",
            "      task_names = {};",
            "      for i = 1:numel(task_idx)",
            "        if task_idx(i) <= numel(SPM.xX.Xnames)",
            "          task_names{i} = SPM.xX.Xnames{task_idx(i)};",
            "        else",
            "          task_names{i} = sprintf('task_%d', i);",
            "        end",
            "      end",
            "      DCM.U.name = task_names;",
            "    else",
            "      DCM.U.name = cellfun(@(x) sprintf('task_%d', x), num2cell(1:size(DCM.U.u, 2)), 'UniformOutput', false);",
            "    end",
            "  else",
            "    % No task conditions found, fall back to null input",
            "    DCM.U.u = zeros(Nvol, 1);",
            "    DCM.U.name = {'null'};",
            "  end",
            "else",
            "  % SPM.xX not found, fall back to null input",
            "  DCM.U.u = zeros(Nvol, 1);",
            "  DCM.U.name = {'null'};",
            "end",
            "DCM.U.idx = [];             % No input indices (C matrix scales the inputs)",
        ])
    else:
        # For resting-state: use SPM's 'null' input convention
        lines.extend([
            "% For resting-state DCM: use SPM's 'null' input convention",
            "% This creates a dummy input that doesn't modulate anything",
            "DCM.U.u = zeros(Nvol, 1);  % Typical input timeseries (all zeros for null input)",
            "DCM.U.name = {'null'};    % Name this as 'null' input (standard SPM convention)",
            "DCM.U.idx = [];             % No input indices (C matrix is all zeros - not used)",
        ])
    lines.append("")

    # Y - Start building DCM.Y structure
    lines.append(f"DCM.Y.dt = SPM.xY.RT;")
    lines.append(f"% Use confounds extracted during VOI creation (in DCM.xY(1).X0)")
    lines.append(f"if isfield(DCM.xY(1), 'X0') && ~isempty(DCM.xY(1).X0)")
    lines.append(f"  DCM.Y.X0 = DCM.xY(1).X0;")
    lines.append(f"else")
    lines.append(f"  % Fallback: create empty confounds if not available in VOI")
    lines.append(f"  DCM.Y.X0 = [];")
    lines.append(f"end")
    for idx, sn in enumerate(seed_names):
        lines.append(f"y_data = DCM.xY({idx + 1}).u;")
        lines.append(f"% Ensure y_data is a column vector")
        lines.append(f"if iscell(y_data)")
        lines.append(f"  y_data = cell2mat(y_data);")
        lines.append(f"end")
        lines.append(f"if size(y_data, 2) > 1 && size(y_data, 1) == 1")
        lines.append(f"  y_data = y_data';  % Transpose if row vector")
        lines.append(f"end")
        lines.append(f"DCM.Y.y(:, {idx + 1}) = y_data;")
    lines.append(f"DCM.Y.name = {{{_matlab_cell_string_list(seed_names)}}};")
    lines.append(f"% Note: Do NOT set DCM.Y.Q manually - SPM DCM estimation will compute it")
    lines.append(f"% from the residuals. DCM.Y.Q will be auto-generated during spm_dcm_estimate")
    lines.append("")

    # Scalar fields
    lines.append(f"DCM.v = Nvol;")
    lines.append(f"DCM.n = N;")
    lines.append(f"DCM.TE = {echo_time};")
    lines.append("")

    # Delays
    delays_str = "[" + " ".join(str(d) for d in delays) + "]"
    lines.append(f"DCM.delays = {delays_str};")
    lines.append("")

    # Options
    lines.append(f"DCM.options.nonlinear = {dcm_options['nonlinear']};")
    lines.append(f"DCM.options.two_state = {dcm_options['two_state']};")
    lines.append(f"DCM.options.stochastic = {dcm_options['stochastic']};")
    lines.append(f"DCM.options.centre = {dcm_options['centre']};")
    lines.append(f"DCM.options.induced = {dcm_options['induced']};")
    lines.append("")

    # Save
    lines.append(f"save('{save_path}', 'DCM');")


    return "\n".join(lines)


def _numpy_to_matlab_matrix(arr):
    """Convert a 2D numpy array to MATLAB matrix string."""
    arr = np.asarray(arr, dtype=int)
    rows = []
    for row in arr:
        rows.append(" ".join(str(v) for v in row))
    return "[" + "; ".join(rows) + "]"


def _matlab_cell_string_list(names):
    """Convert a list of strings to MATLAB cell array content.

    Returns e.g. "'PCC', 'mPFC', 'LIPL'"
    """
    return ", ".join(f"'{n}'" for n in names)
