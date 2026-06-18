"""fMRI VOI (Volume of Interest) extraction submodule.

Extracts BOLD timeseries from spherical seed regions using SPM's VOI tool.
Seeds and radii are defined in the config file.

All steps share the same OUTPUT_DIR. SPM.mat and associated files from the
fit step are already present in OUTPUT_DIR/sub-*/[ses-*/]func/. VOI
extraction runs directly in that directory — no copying or symlinking needed.

VOI is defined as the intersection of the spherical seed region with the
brain mask created by SPM during the --fit step.
"""

import sys
from pathlib import Path

from spmx.bids_utils import decompress_nifti, check_prerequisites_met, update_processing_status
from spmx.defaults import FMRI_VOI
from spmx.logging_setup import get_file_handler
from spmx.matlab_runner import generate_matlab_script, run_matlab_script
from spmx.spm_utils import (
    setup_log_dir,
    setup_sourcedata,
)


def run_voi(args, config, logger):
    """Run VOI extraction.

    Parameters
    ----------
    args : argparse.Namespace
    config : dict
    logger : logging.Logger
    """
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    # Get seed definitions from config
    voi_cfg = config.get("fmri", {}).get("voi", {})
    seeds = voi_cfg.get("seeds")
    if not seeds:
        logger.error("No seeds defined in config file (fmri.voi.seeds).")
        sys.exit(1)

    global_radius = voi_cfg.get("radius", FMRI_VOI["radius"])

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
        logger.error("No subjects found in %s. Run --fit first.", output_dir)
        sys.exit(1)

    logger.info("Subjects to process: %s", subjects)
    logger.info("Seeds: %s", [s["name"] for s in seeds])

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
            _run_voi_single(
                subject, session, seeds, global_radius,
                output_dir, args, config, logger,
            )


def _run_voi_single(subject, session, seeds, global_radius,
                    output_dir, args, config, logger):
    """Run VOI extraction for one subject/session."""
    sess_str = f"sub-{subject}" + (f"/ses-{session}" if session else "")
    logger.info("Processing %s", sess_str)

    log_dir = setup_log_dir(output_dir, subject, session)
    fh = get_file_handler(log_dir / "voi.log")
    logger.addHandler(fh)

    try:
        _voi_core(
            subject, session, seeds, global_radius,
            output_dir, args, config, logger,
        )
        # Mark subject/session as completed voi stage (task-agnostic)
        update_processing_status(output_dir, subject, session, "voi", task=None)
    finally:
        logger.removeHandler(fh)
        fh.close()


def _voi_core(subject, session, seeds, global_radius,
              output_dir, args, config, logger):
    """Core VOI extraction logic."""
    # SPM working directory (where SPM.mat lives from the fit step)
    spm_func_dir = output_dir / f"sub-{subject}"
    if session:
        spm_func_dir = spm_func_dir / f"ses-{session}"
    spm_func_dir = spm_func_dir / "func"
    
    # SPM files are stored in the SPM subfolder
    spm_dir = spm_func_dir / "SPM"

    spm_mat = spm_dir / "SPM.mat"
    if not spm_mat.exists():
        logger.error("  SPM.mat not found at %s. Run --fit first.", spm_mat)
        return

    logger.info("  SPM.mat: %s", spm_mat)

    # Session number is always 1 (fit creates one session per SPM.mat)
    session_number = 1

    # Build BIDS entities for output naming
    entities = {"sub": subject}
    if session:
        entities["ses"] = session
    tasks = getattr(args, "task", None)
    if tasks:
        entities["task"] = tasks[0] if isinstance(tasks, list) else tasks

    # Find brain mask created by SPM fit step
    mask_path = _prepare_spm_mask(spm_dir, output_dir, subject, session, logger)
    if not mask_path:
        logger.warning("  Brain mask not found. VOI will use sphere only.")
    else:
        logger.info("  Brain mask (prepared): %s", mask_path)

    # Load template
    template_dir = Path(__file__).parent.parent / "templates"
    template_text = (template_dir / "fmri_voi.m").read_text()

    log_dir = setup_log_dir(output_dir, subject, session)

    # Run VOI extraction for each seed
    for seed in seeds:
        seed_name = seed["name"]
        x, y, z = seed["x"], seed["y"], seed["z"]
        radius = seed.get("radius", global_radius)

        logger.info("  Extracting VOI: %s (centre=[%s,%s,%s], r=%s)",
                     seed_name, x, y, z, radius)

        batch_code = template_text
        batch_code = batch_code.replace("%%SPM_MAT_PATH%%", str(spm_mat))
        batch_code = batch_code.replace("%%SESSION_NUMBER%%", str(session_number))
        batch_code = batch_code.replace("%%VOI_NAME%%", seed_name)
        batch_code = batch_code.replace("%%SPHERE_CENTRE%%", f"{x} {y} {z}")
        batch_code = batch_code.replace("%%SPHERE_RADIUS%%", str(radius))

        # Handle mask conditionally
        if mask_path:
            batch_code = batch_code.replace("%%MASK_PATH%%", str(mask_path))
        else:
            # If no mask found, remove mask specification and use sphere-only expression
            batch_code = batch_code.replace(
                "% ROI 2: Brain mask\nmatlabbatch{1}.spm.util.voi.roi{2}.mask.image = {'%%MASK_PATH%%'};\nmatlabbatch{1}.spm.util.voi.roi{2}.mask.threshold = 0.5;\n% Expression: intersection of sphere (i1) with mask (i2)\nmatlabbatch{1}.spm.util.voi.expression = 'i1&i2';",
                "% Expression: sphere only (no mask)\nmatlabbatch{1}.spm.util.voi.expression = 'i1';"
            )

        script = generate_matlab_script(
            spm_path=config.get("spm_path", ""),
            matlabbatch_code=batch_code,
            clean_path=config.get("clean_matlab_path", False),
            logger=logger,
        )

        log_script = log_dir / f"voi_{seed_name}.m"
        run_matlab_script(
            script,
            matlab_path=config.get("matlab_path", "matlab"),
            work_dir=spm_dir,
            logger=logger,
            log_script_path=log_script,
            single_comp_thread=config.get("single_comp_thread", False),
            clean_path=config.get("clean_matlab_path", False),
        )

        # Rename VOI output to BIDS
        # SPM creates VOI_<name>_<session>.mat in the SPM working directory
        voi_candidates = list(spm_dir.glob(f"VOI_{seed_name}*.mat"))
        if voi_candidates:
            voi_file = voi_candidates[0]
            logger.info("  VOI %s created: %s", seed_name, voi_file)
        else:
            logger.warning("  VOI file for %s not found after SPM run.", seed_name)


def _prepare_spm_mask(spm_dir, output_dir, subject, session, logger):
    """Find and prepare brain mask created by SPM fit step.

    SPM creates mask.nii files during GLM fitting. If the mask is found,
    decompress it to the sourcedata folder if necessary (SPM requires uncompressed files).

    Parameters
    ----------
    spm_dir : Path
        Directory where SPM.mat is located (sub-*/func/)
    output_dir : Path
        OUTPUT_DIR path
    subject : str
        Subject label (without 'sub-' prefix)
    session : str or None
        Session label (without 'ses-' prefix)
    logger : logging.Logger

    Returns
    -------
    str or None
        Path to uncompressed mask file if found, None otherwise
    """
    # Look for mask file created by SPM fit step
    # Common names: mask.nii, mask.nii.gz
    mask_candidates = list(spm_dir.glob("mask.nii*"))

    if not mask_candidates:
        return None

    mask_file = mask_candidates[0]
    logger.info("    Found mask file: %s", mask_file)

    # If mask is compressed, decompress to sourcedata
    if str(mask_file).endswith(".nii.gz"):
        # Create sourcedata directory structure
        src_dir = output_dir / "sourcedata" / f"sub-{subject}"
        if session:
            src_dir = src_dir / f"ses-{session}"
        src_dir = src_dir / "func"
        src_dir.mkdir(parents=True, exist_ok=True)

        # Decompress
        try:
            decompressed_mask = decompress_nifti(mask_file, src_dir)
            logger.info("    Mask decompressed to: %s", decompressed_mask)
            return str(decompressed_mask)
        except Exception as e:
            logger.warning("    Failed to decompress mask: %s", e)
            return None
    else:
        # Mask is already uncompressed
        return str(mask_file)

