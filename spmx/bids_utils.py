"""BIDS utilities for spmx.

Helpers for discovering data via PyBIDS, building BIDS-compliant output
filenames, and creating JSON sidecar files.
"""

import gzip
import json
import shutil
from pathlib import Path

import nibabel as nib
from bids import BIDSLayout


def get_layout(input_dir, validate=False, derivatives=False):
    """Return a BIDSLayout for the given directory.

    Parameters
    ----------
    input_dir : Path
        Root of the BIDS dataset (or derivative).
    validate : bool
        Whether to run BIDS validation.
    derivatives : bool
        Whether to treat the directory as a derivatives dataset.

    Returns
    -------
    BIDSLayout

    Raises
    ------
    FileNotFoundError
        If dataset_description.json is missing.
    ValueError
        If dataset_description.json is malformed.
    """
    input_dir = Path(input_dir)
    dataset_desc = input_dir / "dataset_description.json"

    # Check if dataset_description.json exists
    if not dataset_desc.exists():
        raise FileNotFoundError(
            f"\n{'='*70}\n"
            f"ERROR: dataset_description.json not found at:\n"
            f"  {dataset_desc}\n\n"
            f"BIDS requires a dataset_description.json file at the root of each\n"
            f"dataset and derivative. Create one with:\n\n"
            f"  cat > {dataset_desc} << 'EOF'\n"
            f"{{\n"
            f'  "Name": "My BIDS dataset",\n'
            f'  "BIDSVersion": "1.9.0",\n'
            f'  "DatasetType": "raw",\n'
            f'  "License": "CC0",\n'
            f'  "Authors": [],\n'
            f'  "Acknowledgements": "",\n'
            f'  "HowToAcknowledge": "",\n'
            f'  "Funding": [],\n'
            f'  "EthicsApprovals": [],\n'
            f'  "ReferencesAndLinks": [],\n'
            f'  "DatasetLinks": {{}},\n'
            f'  "GeneratedBy": []\n'
            f"}}\n"
            f"  EOF\n"
            f"{'='*70}\n"
        )

    # Validate dataset_description.json structure
    try:
        with open(dataset_desc) as f:
            desc = json.load(f)
        if not isinstance(desc, dict):
            raise ValueError("dataset_description.json must be a JSON object")
    except json.JSONDecodeError as e:
        raise ValueError(
            f"\n{'='*70}\n"
            f"ERROR: dataset_description.json is malformed (invalid JSON):\n"
            f"  {dataset_desc}\n\n"
            f"JSONDecodeError: {e}\n"
            f"{'='*70}\n"
        ) from e

    try:
        if derivatives:
            return BIDSLayout(
                input_dir,
                validate=validate,
                config=["bids", "derivatives"],
                is_derivative=True,
            )
        return BIDSLayout(input_dir, validate=validate)
    except TypeError as e:
        if "string indices must be integers" in str(e):
            raise ValueError(
                f"\n{'='*70}\n"
                f"ERROR: dataset_description.json is malformed.\n"
                f"  {dataset_desc}\n\n"
                f"The 'GeneratedBy' field must be a list of objects, not a string.\n"
                f"Verify the JSON structure is valid. Example:\n\n"
                f'{{\n'
                f'  "GeneratedBy": [\n'
                f'    {{\n'
                f'      "Name": "My pipeline",\n'
                f'      "Version": "1.0.0"\n'
                f'    }}\n'
                f'  ]\n'
                f'}}\n'
                f"{'='*70}\n"
            ) from e
        raise


def resolve_subjects(layout, participant_label=None):
    """Return list of subject labels to process."""
    if participant_label:
        return list(participant_label)
    return layout.get_subjects()


def resolve_sessions(layout, subject, sessions=None):
    """Return list of session labels for a subject (may be empty)."""
    available = layout.get_sessions(subject=subject)
    if sessions:
        return [s for s in sessions if s in available]
    return available


def resolve_tasks(layout, subject, session=None, tasks=None):
    """Return list of task labels for a subject/session."""
    kwargs = {"subject": subject}
    if session:
        kwargs["session"] = session
    available = layout.get_tasks(**kwargs)
    if tasks:
        return [t for t in tasks if t in available]
    return available


def resolve_spaces(layout, subject, session=None, task=None, spaces=None):
    """Return list of space labels."""
    kwargs = {"subject": subject}
    if session:
        kwargs["session"] = session
    if task:
        kwargs["task"] = task
    available = layout.get_spaces(**kwargs)
    if spaces:
        return [s for s in spaces if s in available]
    return available


def build_bids_filename(entities, suffix, extension, description=None):
    """Build a BIDS-compliant filename from entities.

    Parameters
    ----------
    entities : dict
        Keys like 'sub', 'ses', 'task', 'space', 'model', etc.
    suffix : str
        BIDS suffix (e.g. 'bold', 'SPMmat', 'betamap').
    extension : str
        File extension including dot (e.g. '.nii.gz', '.mat', '.json').
    description : str or None
        Value for the desc- entity.

    Returns
    -------
    str
        BIDS filename.
    """
    parts = []
    ordered_keys = ["sub", "ses", "task", "space", "model", "contrast", "desc"]
    for key in ordered_keys:
        val = entities.get(key)
        if val is not None:
            parts.append(f"{key}-{val}")
    if description and "desc" not in entities:
        parts.append(f"desc-{description}")
    parts.append(suffix)
    return "_".join(parts) + extension


def build_output_path(output_dir, entities, suffix, extension, description=None):
    """Build a full output path respecting BIDS directory structure.

    Returns
    -------
    Path
    """
    sub_dir = output_dir / f"sub-{entities['sub']}"
    if entities.get("ses"):
        sub_dir = sub_dir / f"ses-{entities['ses']}"
    sub_dir = sub_dir / "func"
    sub_dir.mkdir(parents=True, exist_ok=True)
    fname = build_bids_filename(entities, suffix, extension, description)
    return sub_dir / fname


def write_json_sidecar(path, metadata):
    """Write a JSON sidecar file next to the given path.

    Parameters
    ----------
    path : Path
        Path to the data file; the sidecar will be written with ``.json`` extension.
    metadata : dict
        Metadata to write.
    """
    json_path = path.with_suffix("") if path.suffix == ".gz" else path
    # strip all extensions for multi-ext (e.g. .nii.gz)
    while json_path.suffix:
        json_path = json_path.with_suffix("")
    json_path = json_path.with_suffix(".json")
    with open(json_path, "w") as fh:
        json.dump(metadata, fh, indent=2, default=str)
    return json_path


def decompress_nifti(nii_gz_path, dest_dir):
    """Decompress a .nii.gz file or copy a .nii file into dest_dir.

    Handles both compressed (.nii.gz) and uncompressed (.nii) NIfTI files.

    Parameters
    ----------
    nii_gz_path : Path
        Path to the NIfTI file (can be .nii.gz or .nii).
    dest_dir : Path
        Destination directory (e.g. output_dir / 'sourcedata').

    Returns
    -------
    Path
        Path to the decompressed .nii file.
    """
    nii_gz_path = Path(nii_gz_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Build output name
    out_name = nii_gz_path.name
    if out_name.endswith(".nii.gz"):
        out_name = out_name[:-3]  # remove .gz
    out_path = dest_dir / out_name

    # Handle both compressed and uncompressed files
    if str(nii_gz_path).endswith(".nii.gz"):
        # Decompress gzipped file
        with gzip.open(nii_gz_path, "rb") as f_in:
            with open(out_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    else:
        # File is already .nii (uncompressed), just copy it
        shutil.copy2(nii_gz_path, out_path)

    return out_path


def get_nifti_n_volumes(nii_path):
    """Return number of volumes (4th dimension) of a NIfTI file."""
    img = nib.load(str(nii_path))
    shape = img.shape
    if len(shape) < 4:
        return 1
    return shape[3]


def compress_nifti(nii_path, output_path=None):
    """Compress a .nii file to .nii.gz.

    Parameters
    ----------
    nii_path : Path
        Path to the uncompressed NIfTI.
    output_path : Path or None
        Where to write the compressed file. If None, append '.gz'.

    Returns
    -------
    Path
    """
    nii_path = Path(nii_path)
    if output_path is None:
        output_path = nii_path.with_suffix(nii_path.suffix + ".gz")
    output_path = Path(output_path)
    with open(nii_path, "rb") as f_in:
        with gzip.open(output_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    return output_path


def load_json_metadata(json_path):
    """Load metadata from a JSON sidecar file."""
    with open(json_path) as fh:
        return json.load(fh)


def create_dataset_description(output_dir, module, submodule):
    """Create a dataset_description.json file for the output directory.

    This ensures the output directory is a valid BIDS derivative dataset.
    If the file already exists, it will be updated to preserve ProcessingLog.

    Parameters
    ----------
    output_dir : Path
        Root output directory where dataset_description.json will be created.
    module : str
        Module name (e.g., 'fmri', 'pet').
    submodule : str or None
        Submodule name (e.g., 'fit', 'voi', 'dcm') or None if no submodule.

    Returns
    -------
    Path
        Path to the created dataset_description.json file.
    """
    from spmx import __version__

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_desc_path = output_dir / "dataset_description.json"

    # Check if file already exists - if so, preserve ProcessingLog
    existing_processing_log = None
    if dataset_desc_path.exists():
        try:
            with open(dataset_desc_path) as f:
                existing_metadata = json.load(f)
            existing_processing_log = existing_metadata.get("ProcessingLog")
        except (json.JSONDecodeError, IOError):
            pass  # If we can't read it, we'll just create a new one

    # Build a descriptive name
    if submodule:
        name = f"spmx {module} {submodule}"
    else:
        name = f"spmx {module}"

    # Build metadata
    metadata = {
        "Name": name,
        "BIDSVersion": "1.9.0",
        "DatasetType": "derivatives",
        "GeneratedBy": [
            {
                "Name": "spmx",
                "Version": __version__,
                "CodeURL": "https://gitlab.ulb.be/ln2t/spmx",
                "Container": {
                    "Type": "singularity"
                } if False else None,  # Set to image path if containerized
            }
        ],
        "License": "CC0",
        "Authors": [
            {
                "Name": "spmx Contributors",
            }
        ],
        "Acknowledgements": "Generated by spmx, a BIDS-compliant SPM wrapper",
        "HowToAcknowledge": "Please cite spmx and SPM",
        "Funding": [],
        "EthicsApprovals": [],
        "ReferencesAndLinks": [],
        "DatasetLinks": {
            "template": "MNI152NLin2009cAsym"
        },
    }

    # Clean up None values
    if metadata["GeneratedBy"][0]["Container"] is None:
        del metadata["GeneratedBy"][0]["Container"]

    # Initialize or preserve ProcessingLog to track completed stages
    if existing_processing_log is not None:
        # Preserve existing ProcessingLog
        metadata["ProcessingLog"] = existing_processing_log
    else:
        # Create new empty ProcessingLog
        metadata["ProcessingLog"] = {
            "fit": {},
            "voi": {},
            "dcm": {}
        }

    # Write the file
    with open(dataset_desc_path, "w") as fh:
        json.dump(metadata, fh, indent=2)

    return dataset_desc_path


def get_processing_status(output_dir):
    """Load the processing status from dataset_description.json.

    Returns
    -------
    dict
        The ProcessingLog field with structure:
        {
            "fit": {"sub-001": [ses_labels], "sub-002": [None]},
            "voi": {...},
            "dcm": {...}
        }
    """
    output_dir = Path(output_dir)
    dataset_desc_path = output_dir / "dataset_description.json"

    if not dataset_desc_path.exists():
        return {"fit": {}, "voi": {}, "dcm": {}}

    try:
        with open(dataset_desc_path) as f:
            metadata = json.load(f)
        return metadata.get("ProcessingLog", {"fit": {}, "voi": {}, "dcm": {}})
    except (json.JSONDecodeError, IOError):
        return {"fit": {}, "voi": {}, "dcm": {}}


def update_processing_status(output_dir, subject, session, stage, task=None):
    """Mark a subject/session/task as completed at a given processing stage.

    Parameters
    ----------
    output_dir : Path
        Root output directory.
    subject : str
        Subject label (without 'sub-' prefix).
    session : str or None or int
        Session label (without 'ses-' prefix), or None for no session.
        Will be converted to string if not None.
    stage : str
        Processing stage: "fit", "voi", or "dcm".
    task : str or None
        Task label (without 'task-' prefix), or None if no task-specific tracking.
    """
    output_dir = Path(output_dir)
    dataset_desc_path = output_dir / "dataset_description.json"

    # Normalize session to string (or keep as None)
    if session is not None:
        session = str(session)

    if not dataset_desc_path.exists():
        return

    try:
        with open(dataset_desc_path) as f:
            metadata = json.load(f)
    except (json.JSONDecodeError, IOError):
        return

    # Ensure ProcessingLog exists
    if "ProcessingLog" not in metadata:
        metadata["ProcessingLog"] = {"fit": {}, "voi": {}, "dcm": {}}

    # Ensure stage exists in ProcessingLog
    if stage not in metadata["ProcessingLog"]:
        metadata["ProcessingLog"][stage] = {}

    # Ensure subject exists in stage
    sub_key = f"sub-{subject}"
    if sub_key not in metadata["ProcessingLog"][stage]:
        metadata["ProcessingLog"][stage][sub_key] = {}

    # New structure: metadata["ProcessingLog"][stage][sub_key] is now a dict
    # keyed by session, containing list of completed tasks
    session_key = session if session is not None else "no-session"
    if session_key not in metadata["ProcessingLog"][stage][sub_key]:
        metadata["ProcessingLog"][stage][sub_key][session_key] = []

    # Add task if provided
    if task is not None:
        tasks_list = metadata["ProcessingLog"][stage][sub_key][session_key]
        if task not in tasks_list:
            tasks_list.append(task)

    # Write back to file
    try:
        with open(dataset_desc_path, "w") as f:
            json.dump(metadata, f, indent=2)
    except IOError:
        pass


def check_prerequisites_met(output_dir, subject, session, required_stages, task=None):
    """Check if prerequisites are met for a subject/session/task.

    Parameters
    ----------
    output_dir : Path
        Root output directory.
    subject : str
        Subject label (without 'sub-' prefix).
    session : str or None or int
        Session label (without 'ses-' prefix), or None for no session.
    required_stages : list of str
        List of required completed stages (e.g., ["fit"] or ["fit", "voi"]).
    task : str or None
        Task label (without 'task-' prefix). If None, checks only session level
        (for backward compatibility with task-independent processing).

    Returns
    -------
    bool
        True if all required stages are completed, False otherwise.
    """
    # Normalize session to string (or keep as None)
    if session is not None:
        session = str(session)
    
    status = get_processing_status(output_dir)
    sub_key = f"sub-{subject}"
    session_key = session if session is not None else "no-session"

    for stage in required_stages:
        if stage not in status or sub_key not in status[stage]:
            return False
        
        # Check if session exists in this stage
        if session_key not in status[stage][sub_key]:
            return False
        
        # If checking for a specific task, verify it's in the completed list
        if task is not None:
            tasks_list = status[stage][sub_key][session_key]
            if task not in tasks_list:
                return False

    return True


def stage_already_processed(output_dir, subject_session_pairs, stage, task=None):
    """Check if a stage has already been processed for given subject/session/task pairs.

    Parameters
    ----------
    output_dir : Path
        Root output directory.
    subject_session_pairs : list of tuple
        List of (subject, session) tuples.
    stage : str
        Stage name ("fit", "voi", or "dcm").
    task : str or None
        Task label (without 'task-' prefix). If None, checks only session level.

    Returns
    -------
    bool
        True if ALL subject/session/task pairs have been processed at this stage.
    """
    status = get_processing_status(output_dir)
    
    if stage not in status or not status[stage]:
        return False  # Stage not processed for anyone
    
    for subject, session in subject_session_pairs:
        # Normalize session
        if session is not None:
            session = str(session)
        
        sub_key = f"sub-{subject}"
        session_key = session if session is not None else "no-session"
        
        # Check if this subject has been processed at this stage
        if sub_key not in status[stage]:
            return False  # Not processed for this subject
        
        # Check if this session has been processed
        if session_key not in status[stage][sub_key]:
            return False
        
        # If checking for a specific task, verify it's in the completed list
        if task is not None:
            tasks_list = status[stage][sub_key][session_key]
            if task not in tasks_list:
                return False
    
    # All subject/session/task pairs have been processed at this stage
    return True


def get_subjects_missing_prerequisites(output_dir, subject_session_pairs, required_stages_tuple, task=None):
    """Identify which subject/session/task combinations are missing prerequisites.

    This is useful for generating suggested command lines to run missing stages.

    Parameters
    ----------
    output_dir : Path
        Root output directory.
    subject_session_pairs : list of tuple
        List of (subject, session) tuples to check.
        subject is str without 'sub-' prefix.
        session is str without 'ses-' prefix, int, or None.
    required_stages_tuple : tuple of str
        Stages that must be completed (e.g., ("fit",) or ("fit", "voi")).
    task : str or None
        Task label (without 'task-' prefix). If None, checks only session level.

    Returns
    -------
    dict
        Missing stages per subject/session/task. Structure:
        {
            (subject, session): ["fit"],  # only fit is missing
            (subject, None): ["fit", "voi"],  # both fit and voi are missing
        }
    """
    status = get_processing_status(output_dir)
    missing_by_subject_session = {}

    for subject, session in subject_session_pairs:
        # Normalize session to string (or keep as None)
        if session is not None:
            session = str(session)
        
        sub_key = f"sub-{subject}"
        session_key = session if session is not None else "no-session"
        missing_stages = []

        for stage in required_stages_tuple:
            if stage not in status or sub_key not in status[stage]:
                # Stage has never been run for this subject
                missing_stages.append(stage)
            else:
                # Check if session exists
                if session_key not in status[stage][sub_key]:
                    missing_stages.append(stage)
                elif task is not None:
                    # If checking for specific task, verify it's completed
                    tasks_list = status[stage][sub_key][session_key]
                    if task not in tasks_list:
                        missing_stages.append(stage)

        if missing_stages:
            missing_by_subject_session[(subject, session)] = missing_stages

    return missing_by_subject_session


def build_suggested_command(args, output_dir, missing_stages):
    """Build a suggested command line for running missing preprocessing stages.

    Parameters
    ----------
    args : argparse.Namespace
        Original command-line arguments.
    output_dir : Path
        Output directory path.
    missing_stages : set of str
        Set of missing stages (e.g., {"fit"}, {"fit", "voi"}).

    Returns
    -------
    str
        Suggested command line that can be copy/pasted.
    """
    from pathlib import Path as PathlibPath
    
    output_dir = PathlibPath(output_dir).resolve()
    input_dir = PathlibPath(args.input_dir).resolve()
    
    # Build base command
    cmd_parts = [
        "spmx fmri",
        str(input_dir),
        str(output_dir),
    ]
    
    # Add missing stage flags in order: fit, voi, dcm
    for stage in ["fit", "voi", "dcm"]:
        if stage in missing_stages:
            cmd_parts.append(f"--{stage}")
    
    # Add BIDS filters if provided
    if getattr(args, "participant_label", None):
        labels_str = " ".join(args.participant_label)
        cmd_parts.append(f"--participant-label {labels_str}")
    
    if getattr(args, "session", None):
        sessions_str = " ".join(args.session)
        cmd_parts.append(f"--session {sessions_str}")
    
    if getattr(args, "task", None):
        tasks_str = " ".join(args.task)
        cmd_parts.append(f"--task {tasks_str}")
    
    if getattr(args, "space", None):
        spaces_str = " ".join(args.space)
        cmd_parts.append(f"--space {spaces_str}")
    
    # Add config file if provided
    if getattr(args, "config", None):
        config_path = PathlibPath(args.config).resolve()
        cmd_parts.append(f"--config {config_path}")
    
    # Add general options if provided
    if getattr(args, "matlab_path", None):
        matlab_path = PathlibPath(args.matlab_path).resolve()
        cmd_parts.append(f"--matlab-path {matlab_path}")
    
    if getattr(args, "spm_path", None):
        spm_path = PathlibPath(args.spm_path).resolve()
        cmd_parts.append(f"--spm-path {spm_path}")
    
    if getattr(args, "debug", False):
        cmd_parts.append("--debug")
    
    if getattr(args, "clean_spm_files", False):
        cmd_parts.append("--clean-spm-files")

    # Add fit-specific options if --fit is in missing_stages
    if "fit" in missing_stages:
        if getattr(args, "condition", None):
            conds_str = " ".join(args.condition)
            cmd_parts.append(f"--condition {conds_str}")
        
        if getattr(args, "confound", None):
            confounds_str = " ".join(args.confound)
            cmd_parts.append(f"--confound {confounds_str}")
        
        if getattr(args, "contrast", None):
            # Contrastsmay have spaces, so quote them
            contrasts = " ".join([f"'{c}'" if " " in c else c for c in args.contrast])
            cmd_parts.append(f"--contrast {contrasts}")

    # Add dcm-specific options if --dcm is in missing_stages
    if "dcm" in missing_stages:
        if getattr(args, "model", None):
            models_str = " ".join(args.model)
            cmd_parts.append(f"--model {models_str}")
    
    return " \\\n  ".join(cmd_parts)


def check_fmri_prerequisites(output_dir, args, requested_step, logger):
    """Check if prerequisites are met for a requested fMRI step.

    This function discovers which subject/session combinations need the
    requested step, then checks if all required prerequisite steps have
    been completed. If not, it logs an error with a suggested command.

    Parameters
    ----------
    output_dir : Path
        Output directory where processing status is tracked.
    args : argparse.Namespace
        Command-line arguments.
    requested_step : str
        The requested step: "voi" or "dcm".
    logger : logging.Logger
        Logger for output.

    Returns
    -------
    bool
        True if all prerequisites are met, False otherwise.
    """
    from pathlib import Path as PathlibPath
    
    output_dir = PathlibPath(output_dir).resolve()
    
    # Determine which prerequisite stages are required
    if requested_step == "voi":
        required_stages = ("fit",)
    elif requested_step == "dcm":
        required_stages = ("fit", "voi")
    else:
        return True  # Unknown step, let it proceed
    
    # Discover which subject/session combinations are being processed
    # These are derived from explicitly requested participants/sessions
    # or discovered from output_dir
    output_dir_exists = output_dir.exists()
    
    requested_subjects = getattr(args, "participant_label", None)
    requested_sessions = getattr(args, "session", None)
    
    subject_session_pairs = []
    
    # If explicit subjects/sessions were requested, build pairs from those
    if requested_subjects:
        if requested_sessions:
            # Both subjects and sessions specified
            for subj in requested_subjects:
                for sess in requested_sessions:
                    subject_session_pairs.append((subj, sess))
        else:
            # Only subjects specified - discover sessions for each from output_dir
            if output_dir_exists:
                for subject in requested_subjects:
                    sub_dir = output_dir / f"sub-{subject}"
                    if sub_dir.exists():
                        sessions = sorted([
                            d.name.replace("ses-", "")
                            for d in sub_dir.glob("ses-*")
                            if d.is_dir()
                        ])
                        if sessions:
                            for session in sessions:
                                subject_session_pairs.append((subject, session))
                        else:
                            subject_session_pairs.append((subject, None))
                    else:
                        # Subject dir doesn't exist yet, can't validate
                        return True
            else:
                # Output dir doesn't exist, can't validate
                return True
    elif requested_sessions and output_dir_exists:
        # Sessions specified but not subjects - discover all subjects, filter by session
        for sub_dir in sorted(output_dir.glob("sub-*")):
            if not sub_dir.is_dir():
                continue
            subject = sub_dir.name.replace("sub-", "")
            for session in requested_sessions:
                session_dir = sub_dir / f"ses-{session}"
                if session_dir.exists():
                    subject_session_pairs.append((subject, session))
    elif output_dir_exists:
        # No explicit subjects/sessions - discover all from output directory
        for sub_dir in sorted(output_dir.glob("sub-*")):
            if not sub_dir.is_dir():
                continue
            subject = sub_dir.name.replace("sub-", "")
            
            # Check for session subdirectories
            sessions = sorted([
                d.name.replace("ses-", "")
                for d in sub_dir.glob("ses-*")
                if d.is_dir()
            ])
            
            if sessions:
                for session in sessions:
                    subject_session_pairs.append((subject, session))
            else:
                subject_session_pairs.append((subject, None))
    else:
        # No explicit request and output_dir doesn't exist yet
        # Let the submodule handle validation
        return True
    
    if not subject_session_pairs:
        # No subject/session pairs found, let the submodule handle it
        return True
    
    # Check prerequisites using only ProcessingLog
    missing = get_subjects_missing_prerequisites(
        output_dir, subject_session_pairs, required_stages
    )
    
    if not missing:
        # All prerequisites met
        return True
    
    # Prerequisites not met - build error message
    logger.error("")
    logger.error("=" * 75)
    logger.error(f"ERROR: Missing prerequisites for --{requested_step}")
    logger.error("=" * 75)
    
    # Group missing stages by subject/session
    all_missing_stages = set()
    for stages in missing.values():
        all_missing_stages.update(stages)
    
    logger.error("")
    logger.error(f"The following stages must be completed before running --{requested_step}:")
    for stage in sorted(all_missing_stages):
        logger.error(f"  • {stage}")
    
    logger.error("")
    logger.error("Subject/session combinations with incomplete prerequisites:")
    for (subject, session), stages in sorted(missing.items()):
        sess_str = f"sub-{subject}" + (f"/ses-{session}" if session else "")
        stages_str = ", ".join(sorted(stages))
        logger.error(f"  • {sess_str}: missing {stages_str}")
    
    logger.error("")
    logger.error("Suggested command to complete missing stages:")
    logger.error("")
    suggested_cmd = build_suggested_command(args, output_dir, all_missing_stages)
    for line in suggested_cmd.split("\n"):
        logger.error(f"  {line}")
    logger.error("")
    logger.error("=" * 75)
    logger.error("")
    
    return False
