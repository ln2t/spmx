"""fMRI first-level GLM fitting submodule.

Handles:
1. Model specification (SPM fmri_spec)
2. Model estimation (SPM fmri_est)
3. Contrast computation (SPM con) — optional
4. Results report generation

All SPM outputs are renamed to BIDS conventions with JSON sidecars.
"""

import glob
import json
import re
import sys
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd

from spmx.bids_utils import (
    build_bids_filename,
    build_output_path,
    compress_nifti,
    decompress_nifti,
    get_layout,
    get_nifti_n_volumes,
    load_json_metadata,
    resolve_sessions,
    resolve_subjects,
    resolve_tasks,
    resolve_spaces,
    update_processing_status,
    write_json_sidecar,
)
from spmx.config import get_fit_param
from spmx.logging_setup import get_file_handler
from spmx.matlab_runner import generate_matlab_script, run_matlab_script
from spmx.spm_utils import (
    setup_log_dir,
    setup_sourcedata,
)


def run_fit(args, config, logger):
    """Run fMRI first-level GLM fitting.

    Parameters
    ----------
    args : argparse.Namespace
    config : dict
    logger : logging.Logger
    """
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    layout = get_layout(input_dir, derivatives=True)

    subjects = resolve_subjects(layout, args.participant_label)
    if not subjects:
        logger.error("No subjects found in %s", input_dir)
        sys.exit(1)

    logger.info("Subjects to process: %s", subjects)

    for subject in subjects:
        sessions = resolve_sessions(layout, subject, getattr(args, "session", None))
        if not sessions:
            sessions = [None]

        for session in sessions:
            _run_fit_single(
                subject, session, layout, input_dir, output_dir, args, config, logger
            )


def _run_fit_single(subject, session, layout, input_dir, output_dir,
                    args, config, logger):
    """Run GLM fit for a single subject/session."""
    sess_str = f"sub-{subject}" + (f"/ses-{session}" if session else "")
    logger.info("Processing %s", sess_str)

    # Set up logging to file
    log_dir = setup_log_dir(output_dir, subject, session)
    fh = get_file_handler(log_dir / "fit.log")
    logger.addHandler(fh)

    try:
        _fit_core(subject, session, layout, input_dir, output_dir, args, config, logger)
        # Note: update_processing_status is called per-task in _fit_for_task_space
    finally:
        logger.removeHandler(fh)
        fh.close()


def _fit_core(subject, session, layout, input_dir, output_dir, args, config, logger):
    """Core GLM fitting logic."""
    entities = {"sub": subject}
    if session:
        entities["ses"] = session

    # --- Discover input files ------------------------------------------------
    query = {"subject": subject, "suffix": "bold", "extension": [".nii.gz", ".nii"]}
    if session:
        query["session"] = session

    tasks = resolve_tasks(layout, subject, session, getattr(args, "task", None))
    spaces = resolve_spaces(layout, subject, session, tasks[0] if tasks else None,
                            getattr(args, "space", None))

    if not tasks:
        logger.error("No tasks found for %s", subject)
        return

    for task in tasks:
        for space in (spaces or [None]):
            _fit_for_task_space(
                subject, session, task, space, layout, input_dir, output_dir,
                args, config, logger,
            )


def _fit_for_task_space(subject, session, task, space, layout, input_dir,
                        output_dir, args, config, logger):
    """Run fit for a specific subject/session/task/space combination."""
    entities = {"sub": subject}
    if session:
        entities["ses"] = session
    entities["task"] = task
    if space:
        entities["space"] = space

    logger.info("  Task: %s, Space: %s", task, space or "native")

    # Find preprocessed BOLD
    bold_query = {
        "subject": subject,
        "task": task,
        "suffix": "bold",
        "desc": "preproc",
        "extension": [".nii.gz", ".nii"],
    }
    if session:
        bold_query["session"] = session
    if space:
        bold_query["space"] = space

    bold_files = layout.get(**bold_query)
    if not bold_files:
        logger.warning("  No preprocessed BOLD found, skipping.")
        return

    bold_file = bold_files[0]
    bold_path = Path(bold_file.path)
    logger.info("  BOLD file: %s", bold_path)

    # Load BOLD metadata (JSON sidecar)
    bold_json_path = bold_path.with_suffix("") if bold_path.suffix == ".gz" else bold_path
    while bold_json_path.suffix:
        bold_json_path = bold_json_path.with_suffix("")
    bold_json_path = bold_json_path.with_suffix(".json")
    bold_meta = load_json_metadata(bold_json_path) if bold_json_path.exists() else {}
    tr = bold_meta.get("RepetitionTime")
    if tr is None:
        logger.error("  RepetitionTime not found in BOLD metadata.")
        return

    # Set up sourcedata: decompress NIfTI
    src_dir = setup_sourcedata(output_dir, subject, session)
    nii_path = decompress_nifti(bold_path, src_dir)
    n_volumes = get_nifti_n_volumes(nii_path)
    logger.info("  Volumes: %d, TR: %s", n_volumes, tr)

    # Apply smoothing if requested
    smooth_fwhm = getattr(args, "smooth", None)
    if smooth_fwhm is None:
        smooth_fwhm = get_fit_param(config, "smooth")
    if smooth_fwhm and smooth_fwhm > 0:
        nii_path = _smooth_image(
            nii_path, smooth_fwhm, n_volumes, bold_json_path,
            config.get("spm_path", ""), config.get("matlab_path", "matlab"),
            config, logger
        )

    # Set up SPM output directory (where SPM.mat will be written)
    # SPM files will be stored in a dedicated subfolder to preserve internal paths
    spm_func_dir = output_dir / f"sub-{subject}"
    if session:
        spm_func_dir = spm_func_dir / f"ses-{session}"
    spm_func_dir = spm_func_dir / "func"
    spm_func_dir.mkdir(parents=True, exist_ok=True)
    
    # Create SPM subfolder for original SPM outputs
    spm_work_dir = spm_func_dir / "SPM"
    spm_work_dir.mkdir(parents=True, exist_ok=True)

    # Remove existing SPM.mat to avoid interactive overwrite prompt
    existing_spm_mat = spm_work_dir / "SPM.mat"
    if existing_spm_mat.exists():
        logger.info("  Removing existing SPM.mat: %s", existing_spm_mat)
        existing_spm_mat.unlink()

    # Build scans list
    scans = [f"'{nii_path},{i}'" for i in range(1, n_volumes + 1)]
    scans_str = "\n".join(scans)

    # Build conditions
    conditions_code = _build_conditions(
        subject, session, task, layout, input_dir, args, config, logger
    )

    # Build regressors (confounds)
    regressors_code = _build_regressors(
        subject, session, task, space, layout, args, config, logger
    )

    # Find brain mask
    mask_path = _find_mask(subject, session, task, space, layout, src_dir, logger)

    # Read template
    has_contrasts = bool(getattr(args, "contrast", None))
    template_name = "fmri_fit.m" if has_contrasts else "fmri_fit_nocontrast.m"
    template_dir = Path(__file__).parent.parent / "templates"
    template_text = (template_dir / template_name).read_text()

    # Build contrast code
    contrasts_code = ""
    result_conspec_code = ""
    if has_contrasts:
        contrasts_code, result_conspec_code = _build_contrasts(
            args.contrast, conditions_code, args, config, logger
        )

    # Replace placeholders
    batch_code = template_text
    batch_code = batch_code.replace("%%OUTPUT_DIR%%", str(spm_work_dir))
    batch_code = batch_code.replace("%%TR%%", str(tr))
    batch_code = batch_code.replace("%%FMRI_T%%", str(get_fit_param(config, "fmri_t")))
    batch_code = batch_code.replace("%%FMRI_T0%%", str(get_fit_param(config, "fmri_t0")))
    batch_code = batch_code.replace("%%SCANS%%", scans_str)
    batch_code = batch_code.replace("%%CONDITIONS%%", conditions_code)
    batch_code = batch_code.replace("%%REGRESSORS%%", regressors_code)
    batch_code = batch_code.replace("%%HPF%%", str(get_fit_param(config, "hpf")))
    batch_code = batch_code.replace("%%MASK%%", f"'{mask_path}'" if mask_path else "''")
    batch_code = batch_code.replace(
        "%%WRITE_RESIDUALS%%", str(get_fit_param(config, "write_residuals"))
    )
    if has_contrasts:
        batch_code = batch_code.replace("%%CONTRASTS%%", contrasts_code)
        batch_code = batch_code.replace("%%RESULT_CONSPEC%%", result_conspec_code)

    # Generate full MATLAB script
    script = generate_matlab_script(
        spm_path=config.get("spm_path", ""),
        matlabbatch_code=batch_code,
        clean_path=config.get("clean_matlab_path", False),
        logger=logger,
    )

    # Save script for debugging
    log_dir = setup_log_dir(output_dir, subject, session)
    log_script = log_dir / f"fit_task-{task}"
    if space:
        log_script = log_dir / f"fit_task-{task}_space-{space}"
    log_script = log_script.with_suffix(".m")

    # Run MATLAB
    logger.info("  Launching MATLAB for GLM fitting...")
    run_matlab_script(
        script,
        matlab_path=config.get("matlab_path", "matlab"),
        work_dir=spm_work_dir,
        logger=logger,
        log_script_path=log_script,
        single_comp_thread=config.get("single_comp_thread", False),
        clean_path=config.get("clean_matlab_path", False),
    )
    logger.info("  MATLAB completed.")

    # Organize SPM outputs to BIDS-compliant format
    _organize_fit_outputs(subject, session, task, space, spm_work_dir, output_dir,
                         args, logger)
    
    # Mark this task as completed for fit stage
    update_processing_status(output_dir, subject, session, "fit", task=task)


def _smooth_image(nii_path, smooth_fwhm, n_volumes, input_json_path,
                  spm_path, matlab_path, config, logger):
    """Apply Gaussian smoothing to NIfTI image using SPM.

    If FWHM > 0, renames file from "desc-preproc" to "desc-smoothed" and updates JSON.
    Returns the new path if smoothed, otherwise returns the original path unchanged.

    Parameters
    ----------
    nii_path : Path
        Path to NIfTI file to smooth.
    smooth_fwhm : float
        Full-width at half-maximum (FWHM) of Gaussian kernel in mm.
        If <= 0, returns original path unchanged.
    n_volumes : int
        Number of volumes in the 4D image.
    input_json_path : Path
        Path to JSON sidecar in INPUT_DIR to copy and update.
    spm_path : str
        Path to SPM installation.
    matlab_path : str
        Path to MATLAB executable.
    config : dict
        Configuration dictionary.
    logger : logging.Logger

    Returns
    -------
    Path
        Path to the processed NIfTI file (renamed to "desc-smoothed" if smoothing applied).
    """
    if smooth_fwhm <= 0:
        logger.debug("  Smoothing disabled (FWHM=%.2f)", smooth_fwhm)
        return nii_path

    logger.info("  Smoothing image with FWHM=%.2f mm", smooth_fwhm)

    nii_path = Path(nii_path)
    work_dir = nii_path.parent

    # Build scan list for matlabbatch: all volumes of the same file
    scans = [f"'{nii_path},{i}'" for i in range(1, n_volumes + 1)]
    scans_str = ",\n                                          ".join(scans)

    # Build matlabbatch code for smoothing
    matlabbatch_code = f"""matlabbatch{{1}}.spm.spatial.smooth.data = {{
                                          {scans_str}
                                          }};
matlabbatch{{1}}.spm.spatial.smooth.fwhm = [{smooth_fwhm} {smooth_fwhm} {smooth_fwhm}];
matlabbatch{{1}}.spm.spatial.smooth.dtype = 0;
matlabbatch{{1}}.spm.spatial.smooth.im = 0;
matlabbatch{{1}}.spm.spatial.smooth.prefix = 's';
"""

    # Generate and run MATLAB script
    script = generate_matlab_script(
        spm_path=config.get("spm_path", ""),
        matlabbatch_code=matlabbatch_code,
        clean_path=config.get("clean_matlab_path", False),
        logger=logger,
    )

    run_matlab_script(
        script,
        matlab_path=config.get("matlab_path", "matlab"),
        work_dir=work_dir,
        logger=logger,
        single_comp_thread=config.get("single_comp_thread", False),
        clean_path=config.get("clean_matlab_path", False),
    )

    # Rename smoothed file: remove 's' prefix added by SPM
    smoothed_path = nii_path.parent / ("s" + nii_path.name)
    if not smoothed_path.exists():
        logger.error("  Smoothed image not created: %s", smoothed_path)
        return nii_path

    # Rename file from "desc-preproc" to "desc-smoothed"
    new_filename = nii_path.name.replace("desc-preproc", "desc-smoothed")
    new_nii_path = nii_path.parent / new_filename
    smoothed_path.rename(new_nii_path)
    logger.info("  Smoothed image saved: %s", new_nii_path)

    # Copy and update JSON sidecar
    input_json_path = Path(input_json_path)
    if input_json_path.exists():
        # Create new JSON path to match new NIfTI (desc-smoothed)
        new_json_filename = new_filename.replace(".nii.gz", ".json").replace(".nii", ".json")
        new_json_path = nii_path.parent / new_json_filename

        # Copy JSON from input directory
        meta = load_json_metadata(input_json_path)
        
        # Add smoothing information
        meta["Smoothing"] = {
            "FWHM_mm": smooth_fwhm,
            "Kernel": "Gaussian",
        }
        
        write_json_sidecar(new_json_path, meta)
        logger.debug("  Updated JSON sidecar: %s", new_json_path)
    else:
        logger.warning("  Input JSON not found at %s, skipping sidecar update", input_json_path)

    return new_nii_path


def _organize_fit_outputs(subject, session, task, space, spm_work_dir, output_dir,
                          args, logger):
    """Reorganize and rename SPM fit outputs to BIDS-compliant format.

    Copies mask.nii and contrast maps (if generated) from SPM output directory
    to the main output directory with proper BIDS naming and compression.

    Parameters
    ----------
    subject : str
        Subject label (without 'sub-' prefix).
    session : str or None
        Session label (without 'ses-' prefix) or None.
    task : str
        Task name.
    space : str or None
        Template space name or None for native space.
    spm_work_dir : Path
        SPM working directory containing mask.nii and contrast maps.
    output_dir : Path
        Output directory root (where files will be copied).
    args : argparse.Namespace
        CLI arguments (contains contrast info).
    logger : logging.Logger
        Logger instance.
    """
    spm_work_dir = Path(spm_work_dir)
    output_dir = Path(output_dir)

    # Build base output filename
    base_name = f"sub-{subject}"
    if session:
        base_name += f"_ses-{session}"
    if task:
        base_name += f"_task-{task}"
    if space:
        base_name += f"_space-{space}"

    # Determine target directory
    target_dir = output_dir / f"sub-{subject}"
    if session:
        target_dir = target_dir / f"ses-{session}"
    target_dir = target_dir / "func"
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy and compress mask.nii
    mask_src = spm_work_dir / "mask.nii"
    if mask_src.exists():
        mask_dest_name = f"{base_name}_desc-brain_mask.nii.gz"
        mask_dest = target_dir / mask_dest_name
        mask_compressed = compress_nifti(mask_src, mask_dest)
        logger.info("  Organized mask: %s", mask_compressed)
    else:
        logger.warning("  Mask file not found: %s", mask_src)

    # Copy and rename contrast maps if they exist
    contrast_exprs = getattr(args, "contrast", None) or []
    if not contrast_exprs:
        return

    for idx, contrast_expr in enumerate(contrast_exprs, start=1):
        con_name = contrast_expr.replace(" ", "")  # Sanitized name (same as MATLAB)
        con_idx_str = f"{idx:04d}"  # SPM uses zero-padded 4-digit format

        # Copy contrast effect size map (con_00XX.nii)
        con_src = spm_work_dir / f"con_{con_idx_str}.nii"
        if con_src.exists():
            con_dest_name = f"{base_name}_contrast-{con_name}_effectSize.nii.gz"
            con_dest = target_dir / con_dest_name
            con_compressed = compress_nifti(con_src, con_dest)
            logger.info("  Organized contrast effect size: %s", con_compressed)
        else:
            logger.warning("  Contrast map not found: %s", con_src)

        # Copy t-score map (spmT_00XX.nii)
        spm_t_src = spm_work_dir / f"spmT_{con_idx_str}.nii"
        if spm_t_src.exists():
            spm_t_dest_name = f"{base_name}_contrast-{con_name}_tScore.nii.gz"
            spm_t_dest = target_dir / spm_t_dest_name
            spm_t_compressed = compress_nifti(spm_t_src, spm_t_dest)
            logger.info("  Organized t-score: %s", spm_t_compressed)
        else:
            logger.warning("  T-score map not found: %s", spm_t_src)


def _build_conditions(subject, session, task, layout, input_dir, args, config, logger):
    """Build MATLAB condition blocks from events.tsv.

    Returns
    -------
    str
        MATLAB code for condition definitions.
    """
    condition_names = getattr(args, "condition", None)
    if not condition_names:
        return (
            "matlabbatch{1}.spm.stats.fmri_spec.sess.cond = "
            "struct('name', {}, 'onset', {}, 'duration', {}, 'tmod', {}, "
            "'pmod', {}, 'orth', {});"
        )

    # Find events file
    # Priority 1: CLI argument --events-file
    events_path = getattr(args, "events_file", None)
    if events_path:
        events_path = Path(events_path)
        if not events_path.exists():
            logger.error("  Events file specified but not found: %s", events_path)
            sys.exit(1)
    else:
        # Priority 2: BIDS layout search
        events_query = {"subject": subject, "task": task, "suffix": "events",
                        "extension": ".tsv"}
        if session:
            events_query["session"] = session

        events_files = layout.get(**events_query)
        if not events_files:
            # Priority 3: Look in input_dir root (events might be at root level)
            logger.warning("  No events.tsv found via layout, looking in input_dir root.")
            events_pattern = input_dir / f"sub-{subject}"
            if session:
                events_pattern = events_pattern / f"ses-{session}"
            events_pattern = events_pattern / "func" / f"*task-{task}*_events.tsv"
            events_candidates = list(events_pattern.parent.glob(events_pattern.name))
            if not events_candidates:
                logger.error("  Cannot find events.tsv for task %s", task)
                sys.exit(1)
            events_path = events_candidates[0]
        else:
            events_path = Path(events_files[0].path)

    logger.info("  Events file: %s", events_path)
    events_df = pd.read_csv(events_path, sep="\t")

    # Validate that required conditions exist
    available_types = events_df["trial_type"].unique().tolist()
    for cond in condition_names:
        if cond not in available_types:
            logger.error(
                "  Condition '%s' not found in events.tsv trial_type column. "
                "Available: %s",
                cond,
                available_types,
            )
            sys.exit(1)

    lines = []
    tmod = get_fit_param(config, "cond_tmod")
    orth = get_fit_param(config, "cond_orth")

    for idx, cond_name in enumerate(condition_names, start=1):
        cond_rows = events_df[events_df["trial_type"] == cond_name]
        onsets = cond_rows["onset"].tolist()
        durations = cond_rows["duration"].tolist()

        onsets_str = " ".join(str(o) for o in onsets)
        durations_str = " ".join(str(d) for d in durations)

        prefix = f"matlabbatch{{1}}.spm.stats.fmri_spec.sess.cond({idx})"
        lines.append(f"{prefix}.name = '{cond_name}';")
        lines.append(f"{prefix}.onset = [{onsets_str}];")
        lines.append(f"{prefix}.duration = [{durations_str}];")
        lines.append(f"{prefix}.tmod = {tmod};")
        lines.append(
            f"{prefix}.pmod = struct('name', {{}}, 'param', {{}}, 'poly', {{}});"
        )
        lines.append(f"{prefix}.orth = {orth};")

    return "\n".join(lines)


def _build_regressors(subject, session, task, space, layout, args, config, logger):
    """Build MATLAB regressor blocks from confounds TSV.

    Regressors are determined by priority:
    1. CLI argument: --confound REG1 [REG2 ...]
    2. Config file: fmri.fit.regressors (list of regressor names)
    3. Default: no regressors

    Returns
    -------
    str
        MATLAB code for regressor definitions.
    """
    # Priority 1: CLI arguments override everything
    confound_names = getattr(args, "confound", None)
    
    # Priority 2: Try config file if CLI not specified
    if not confound_names:
        confound_names = get_fit_param(config, "regressors")
    
    # Priority 3: If still not defined, use no regressors
    if not confound_names:
        return (
            "matlabbatch{1}.spm.stats.fmri_spec.sess.regress = "
            "struct('name', {}, 'val', {});"
        )

    # Find confounds file
    confounds_query = {
        "subject": subject,
        "task": task,
        "suffix": "timeseries",
        "desc": "confounds",
        "extension": ".tsv",
    }
    if session:
        confounds_query["session"] = session

    confounds_files = layout.get(**confounds_query)
    if not confounds_files:
        logger.error("  No confounds timeseries file found.")
        sys.exit(1)

    confounds_path = Path(confounds_files[0].path)
    logger.info("  Confounds file: %s", confounds_path)
    confounds_df = pd.read_csv(confounds_path, sep="\t")

    # Validate columns
    for reg in confound_names:
        if reg not in confounds_df.columns:
            logger.error(
                "  Confound '%s' not found in confounds file. Available: %s",
                reg,
                list(confounds_df.columns),
            )
            sys.exit(1)

    lines = []
    for idx, reg_name in enumerate(confound_names, start=1):
        values = confounds_df[reg_name].fillna(0).tolist()
        vals_str = " ".join(str(v) for v in values)
        prefix = f"matlabbatch{{1}}.spm.stats.fmri_spec.sess.regress({idx})"
        lines.append(f"{prefix}.name = '{reg_name}';")
        lines.append(f"{prefix}.val = [{vals_str}];")

    return "\n".join(lines)


def _find_mask(subject, session, task, space, layout, src_dir, logger):
    """Find the BOLD brain mask and decompress if needed.

    Returns
    -------
    Path or None
        Path to the uncompressed mask, or None if not found.
    """
    mask_query = {
        "subject": subject,
        "task": task,
        "suffix": "mask",
        "desc": "brain",
        "extension": [".nii.gz", ".nii"],
    }
    if session:
        mask_query["session"] = session
    if space:
        mask_query["space"] = space

    mask_files = layout.get(**mask_query)
    if not mask_files:
        logger.warning("  No brain mask found; SPM will use default thresholding.")
        return None

    mask_path = Path(mask_files[0].path)
    if mask_path.name.endswith(".nii.gz"):
        mask_path = decompress_nifti(mask_path, src_dir)
    return mask_path


def _build_contrasts(contrast_exprs, conditions_code, args, config, logger):
    """Build MATLAB contrast definition and result conspec blocks.

    Parameters
    ----------
    contrast_exprs : list of str
        Contrast expressions (e.g. "face - house").
    conditions_code : str
        The MATLAB conditions code (used to extract condition order).

    Returns
    -------
    tuple of (str, str)
        (contrasts MATLAB code, result conspec MATLAB code)
    """
    # Extract condition names from MATLAB code to determine order
    condition_names = getattr(args, "condition", []) or []

    lines = []
    conspec_lines = []

    for idx, expr in enumerate(contrast_exprs, start=1):
        # Build contrast vector using the condition names
        contrast_vector = _parse_contrast_expression(expr, condition_names)
        vec_str = " ".join(str(v) for v in contrast_vector)

        # Sanitize contrast name for SPM
        con_name = expr.replace(" ", "")

        prefix = f"matlabbatch{{3}}.spm.stats.con.consess{{{idx}}}.tcon"
        lines.append(f"{prefix}.name = '{con_name}';")
        lines.append(f"{prefix}.weights = [{vec_str}];")
        lines.append(f"{prefix}.sessrep = 'none';")

        # Result conspec
        cs_prefix = f"matlabbatch{{4}}.spm.stats.results.conspec({idx})"
        conspec_lines.append(f"{cs_prefix}.titlestr = '{con_name}';")
        conspec_lines.append(f"{cs_prefix}.contrasts = {idx};")
        conspec_lines.append(f"{cs_prefix}.threshdesc = 'none';")
        conspec_lines.append(f"{cs_prefix}.thresh = 0.001;")
        conspec_lines.append(f"{cs_prefix}.extent = 0;")
        conspec_lines.append(f"{cs_prefix}.conjunction = 1;")
        conspec_lines.append(
            f"{cs_prefix}.mask = struct('contrasts', {{}}, 'thresh', {{}}, "
            f"'mtype', {{}});"
        )

    return "\n".join(lines), "\n".join(conspec_lines)


def _parse_contrast_expression(expr, condition_names):
    """Parse a contrast expression string into a weight vector.

    Uses a simple parser that understands condition names with +, -, and
    scalar multipliers (e.g. '0.5*face - 0.5*house').

    Parameters
    ----------
    expr : str
        Contrast expression.
    condition_names : list of str
        Ordered condition names (matching matlabbatch order).

    Returns
    -------
    list of float
        Contrast weight vector.
    """
    n_conds = len(condition_names)
    weights = [0.0] * n_conds

    # Tokenize: split on + or - while keeping the sign
    # Normalize: ensure expression starts with a sign
    expr = expr.strip()
    if not expr.startswith(("+", "-")):
        expr = "+" + expr

    # Pattern: optional sign, optional multiplier, condition name
    pattern = r"([+-])\s*(?:(\d+(?:\.\d+)?)\s*\*)?\s*(\w+)"
    for match in re.finditer(pattern, expr):
        sign_str, mult_str, cond = match.groups()
        sign = 1.0 if sign_str == "+" else -1.0
        mult = float(mult_str) if mult_str else 1.0

        if cond not in condition_names:
            raise ValueError(
                f"Condition '{cond}' in contrast expression not found in "
                f"condition list: {condition_names}"
            )
        idx = condition_names.index(cond)
        weights[idx] = sign * mult

    return weights
