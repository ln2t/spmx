"""Group-level DCM analysis (PEB - Parametric Empirical Bayes).

Handles specification and estimation of group-level DCM models using
SPM's parametric empirical Bayes (PEB) framework.

Workflow:
1. Load participants file with covariates
2. Collect DCM files from participant-level results
3. Prepare covariate matrix (continuous + categorical/dummy-coded)
4. Generate MATLAB batch for PEB specification
5. Run SPM PEB estimation via matlabbatch
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from spmx.config import get_dcm_option, get_dcm_param
from spmx.defaults import FMRI_DCM
from spmx.logging_setup import get_file_handler
from spmx.matlab_runner import generate_matlab_script, run_matlab_script
from spmx.spm_utils import setup_log_dir
from spmx.fmri.extract_peb_results import extract_and_export_peb_results
from spmx.fmri.group_dcm_report import run_group_dcm_report


def _bids_label(name: str) -> str:
    """Return a BIDS-compliant label by stripping non-alphanumeric characters.

    BIDS entity labels (the VALUE part of ``key-VALUE``) must be purely
    alphanumeric.  Hyphens and underscores used in model names like
    ``resting-state-full`` are therefore stripped:
    ``resting-state-full`` → ``restingstatefull``.
    """
    return re.sub(r'[^A-Za-z0-9]', '', name)


def run_group_dcm(args, config, logger):
    """Run group-level DCM analysis (PEB).

    Parameters
    ----------
    args : argparse.Namespace
    config : dict
    logger : logging.Logger
    """
    output_dir = Path(args.output_dir).resolve()
    
    # Validate that --dcm flag is present (group-level only works with DCM)
    if not getattr(args, 'dcm', False):
        logger.error("Group-level analysis currently requires --dcm flag.")
        sys.exit(1)
    
    # Validate and load participants file
    participants_file = getattr(args, 'participants_file', None)
    if not participants_file:
        logger.error("Group-level DCM analysis requires --participants-file argument.")
        sys.exit(1)
    
    participants_file = Path(participants_file).resolve()
    if not participants_file.exists():
        logger.error("Participants file not found: %s", participants_file)
        sys.exit(1)
    
    logger.info("Loading participants file: %s", participants_file)
    try:
        participants_df = pd.read_csv(participants_file, sep='\t')
    except Exception as e:
        logger.error("Failed to load participants file: %s", e)
        sys.exit(1)
    
    # Check that participant_id column exists
    if 'participant_id' not in participants_df.columns:
        logger.error("Participants file must contain 'participant_id' column.")
        sys.exit(1)
    
    logger.info("Loaded %d participants", len(participants_df))

    # Filter to --participant-label if provided (supports glob patterns, e.g. "CTL*")
    requested_labels = getattr(args, 'participant_label', None) or []
    if requested_labels:
        import fnmatch
        original_n = len(participants_df)
        all_ids = participants_df['participant_id'].tolist()

        def _matches_any(pid):
            # Try matching both with and without 'sub-' prefix in the pattern
            for pat in requested_labels:
                pat_sub = pat if pat.startswith('sub-') else f'sub-{pat}'
                pat_bare = pat[4:] if pat.startswith('sub-') else pat
                pid_bare = pid[4:] if pid.startswith('sub-') else pid
                if fnmatch.fnmatch(pid, pat_sub) or fnmatch.fnmatch(pid_bare, pat_bare):
                    return True
            return False

        participants_df = participants_df[
            participants_df['participant_id'].apply(_matches_any)
        ].reset_index(drop=True)
        if participants_df.empty:
            logger.error(
                "None of the requested --participant-label patterns (%s) matched "
                "any participant in the participants file.",
                sorted(requested_labels),
            )
            sys.exit(1)
        logger.info(
            "--participant-label filter: keeping %d of %d participants (%s)",
            len(participants_df),
            original_n,
            sorted(participants_df['participant_id'].tolist()),
        )

    # Get list of requested regressors
    regressors = getattr(args, 'regressors', None) or []
    categorical_regressors = getattr(args, 'categorical_regressors', None) or []

    # Extract contrast specification (used for categorical regressors)
    contrast_raw = getattr(args, 'contrast', None)
    if isinstance(contrast_raw, list):
        contrast_str = contrast_raw[0] if contrast_raw else None
    else:
        contrast_str = contrast_raw

    if regressors:
        logger.info("Using regressors: %s", regressors)
        logger.info(
            "Categorical regressors: %s",
            categorical_regressors if categorical_regressors else "(none)",
        )
        if categorical_regressors and contrast_str:
            logger.info("Categorical contrast: '%s'", contrast_str)
        elif categorical_regressors and not contrast_str:
            logger.warning(
                "Categorical regressors specified but no --contrast provided. "
                "Each categorical regressor will require a contrast at build time."
            )

        # Validate that all regressors exist in participants file
        missing_cols = set(regressors) - set(participants_df.columns)
        if missing_cols:
            logger.error("Missing columns in participants file: %s", missing_cols)
            sys.exit(1)
    else:
        logger.info("No regressors specified (group intercept only.)")
    
    # Get DCM model name from CLI args or config file
    dcm_models = getattr(args, 'model', None) or []
    if not dcm_models:
        # Try to get from config file
        model_from_config = config.get("fmri", {}).get("dcm", {}).get("model")
        if model_from_config:
            # Could be string or list
            if isinstance(model_from_config, str):
                dcm_models = [model_from_config]
            elif isinstance(model_from_config, list):
                dcm_models = model_from_config
    
    if not dcm_models:
        logger.error(
            "For group-level DCM, you must specify --model (CLI argument) or "
            "provide 'model' in the 'fmri.dcm' section of the config file."
        )
        sys.exit(1)
    
    # Group analysis name
    group_name = getattr(args, 'group_name', 'PEB_analysis')

    # Custom group label for folder naming
    custom_group_label = getattr(args, 'custom_group_label', None)
    if custom_group_label:
        group_folder_name = f"group_{custom_group_label}"
        logger.info("Using custom group folder name: %s", group_folder_name)
    else:
        group_folder_name = "group"
        logger.info("Using default group folder name: %s", group_folder_name)

    # Collect all DCM subjects across models (for the report)
    all_dcm_subjects: list = []

    # For each model, run group-level PEB analysis
    for model_name in dcm_models:
        logger.info("Running PEB analysis for model: %s", model_name)
        model_subjects = _run_peb_single(
            model_name=model_name,
            group_name=group_name,
            group_folder_name=group_folder_name,
            participants_df=participants_df,
            regressors=regressors,
            categorical_regressors=categorical_regressors,
            contrast_str=contrast_str,
            output_dir=output_dir,
            config=config,
            logger=logger,
        )
        # Accumulate unique subjects
        for s in (model_subjects or []):
            if s not in all_dcm_subjects:
                all_dcm_subjects.append(s)

    logger.info("Group-level DCM analysis completed.")

    # Generate BIDS outputs and HTML report
    try:
        run_group_dcm_report(
            output_dir=output_dir,
            args=args,
            config=config,
            participants_df=participants_df,
            all_dcm_subjects=all_dcm_subjects,
            group_folder_name=group_folder_name,
            logger=logger,
        )
    except Exception as exc:
        logger.warning("Report generation failed (non-fatal): %s", exc)
        if getattr(args, 'debug', False):
            logger.exception("Report generation error details:")


def _run_peb_single(model_name, group_name, group_folder_name, participants_df, regressors,
                    categorical_regressors, contrast_str, output_dir, config, logger):
    """Run PEB analysis for a single model.

    Parameters
    ----------
    group_folder_name : str
        Name of the group folder to create (e.g., 'group' or 'group_custom_label')

    Returns
    -------
    list of str or None
        Subject IDs (without 'sub-' prefix) that had DCM files, or None on
        early failure before subjects are collected.
    """
    dcm_cfg = config.get("fmri", {}).get("dcm", {})

    # BIDS-safe model label (hyphens/underscores are not allowed in BIDS entity labels)
    model_name_bids = _bids_label(model_name)
    if model_name_bids != model_name:
        logger.info(
            "Model name '%s' sanitized to '%s' for BIDS output filenames",
            model_name, model_name_bids,
        )

    # Log directory for group analysis
    log_dir = output_dir / group_folder_name / "SPM"
    log_dir.mkdir(parents=True, exist_ok=True)

    fh = get_file_handler(log_dir / f"peb_{model_name_bids}.log")
    logger.addHandler(fh)

    try:
        # ------------------------------------------------------------------
        # Clean up stale derived outputs for this model before (re-)running.
        # When the user changes the design matrix (e.g. adds --regressors),
        # old TSV / metadata files from a previous run of the same model would
        # otherwise persist on disk and be picked up by the report generator,
        # making the report look as if PEB was run twice.
        # We remove only the *derived* files (TSV + metadata JSON); the old
        # .mat files are kept so the user can inspect them if needed.
        # ------------------------------------------------------------------
        stale_patterns = [
            f'xPEB_{model_name_bids}*.tsv',
            f'xPEB_{model_name_bids}*_metadata.json',
        ]
        for pattern in stale_patterns:
            for stale in sorted(log_dir.glob(pattern)):
                logger.info("Removing stale output from previous run: %s", stale.name)
                stale.unlink()

        # Collect DCM files from all subjects
        dcm_files, dcm_subjects = _collect_dcm_files(
            output_dir=output_dir,
            model_name=model_name,
            participants_df=participants_df,
            logger=logger,
        )
        
        if not dcm_files:
            logger.error("No DCM files found for model %s", model_name)
            return []
        
        logger.info("Found DCM files for %d participants", len(dcm_files))
        
        # Validate that all DCM subjects exist in the participants file
        dcm_subjects_set = set(dcm_subjects)
        participants_ids = set(participants_df['participant_id'].str.replace("sub-", "").values)
        missing_from_file = dcm_subjects_set - participants_ids
        
        if missing_from_file:
            logger.error(
                "ERROR: %d DCM subjects not found in participants file: %s",
                len(missing_from_file), missing_from_file
            )
            logger.error(
                "All DCM subjects must be listed in the participants file "
                "(but not all participants need DCM files)."
            )
            sys.exit(1)
        
        logger.info(
            "✓ All %d DCM subjects are present in participants file",
            len(dcm_subjects)
        )
        
        # Build covariate matrix (will only include dcm_subjects from participants_df)
        X, regressor_names, contrast_name_safe = _build_covariate_matrix(
            participants_df=participants_df,
            dcm_subjects=dcm_subjects,
            regressors=regressors,
            categorical_regressors=categorical_regressors,
            contrast_str=contrast_str,
            logger=logger,
        )

        # Save design matrix TSV for quality control (before running MATLAB)
        _save_design_matrix_tsv(
            X=X,
            regressor_names=regressor_names,
            dcm_subjects=dcm_subjects,
            output_dir=log_dir,
            model_name=model_name_bids,
            contrast_name=contrast_name_safe,
            logger=logger,
        )

        # Determine analysis type
        analysis_type = dcm_cfg.get("analysis", "csd")

        # Define output file path for xPEB results (include contrast name if given)
        suffix = f"_{contrast_name_safe}" if contrast_name_safe else ""
        xpeb_output_path = log_dir / f"xPEB_{model_name_bids}{suffix}.mat"
        
        # Generate direct MATLAB code for PEB (bypasses spm_jobman batch)
        peb_code = _build_peb_matlab_direct(
            dcm_mat_paths=dcm_files,
            group_name=group_name,
            model_name=model_name,
            model_name_bids=model_name_bids,
            X=X,
            regressor_names=regressor_names,
            analysis_type=analysis_type,
            output_dir=log_dir,
            xpeb_output_path=xpeb_output_path,
            contrast_name_safe=contrast_name_safe,
        )

        # Generate full MATLAB script — PEB runs directly, no spm_jobman batch
        script = generate_matlab_script(
            spm_path=config.get("spm_path", ""),
            matlabbatch_code="",
            pre_code=peb_code,
            skip_batch=True,
            clean_path=config.get("clean_matlab_path", False),
            logger=logger,
        )
        
        logger.info("Launching MATLAB for PEB estimation...")
        logger.info("PEB results will be saved to: %s", xpeb_output_path)
        run_matlab_script(
            script,
            matlab_path=config.get("matlab_path", "matlab"),
            work_dir=log_dir,
            logger=logger,
            log_script_path=log_dir / f"peb_{model_name_bids}.m",
            single_comp_thread=config.get("single_comp_thread", False),
            clean_path=config.get("clean_matlab_path", False),
        )
        logger.info("MATLAB PEB estimation completed.")
        
        # Verify output file was created
        if xpeb_output_path.exists():
            file_size = xpeb_output_path.stat().st_size
            logger.info("✓ PEB results saved successfully: %s (%.2f MB)",
                       xpeb_output_path, file_size / (1024**2))
            
            # Extract and export results to TSV format
            logger.info("Extracting PEB results to TSV format...")
            try:
                extract_and_export_peb_results(
                    xpeb_mat_path=xpeb_output_path,
                    output_dir=log_dir,
                    logger=logger,
                )
                logger.info("✓ PEB results exported to TSV files")
            except Exception as e:
                logger.error("Failed to extract PEB results: %s", e)
                if logger.level <= 10:  # DEBUG level
                    logger.exception("Detailed error:")
        else:
            logger.error("✗ PEB results file not found at: %s", xpeb_output_path)
            logger.error("Check MATLAB log for errors in PEB specification/estimation.")

        return dcm_subjects

    finally:
        logger.removeHandler(fh)
        fh.close()


def _collect_dcm_files(output_dir, model_name, participants_df, logger):
    """Collect DCM .mat files from participant-level results.
    
    Returns
    -------
    tuple
        (dcm_files: list of str, dcm_subjects: list of str)
        where dcm_subjects are the subject IDs without 'sub-' prefix
    """
    dcm_files = []
    dcm_subjects = []
    
    for _, row in participants_df.iterrows():
        participant_id = row['participant_id'].replace("sub-", "")
        sub_dir = output_dir / f"sub-{participant_id}"
        
        # Look for DCM files in any session
        dcm_candidates = list(sub_dir.rglob(f"DCM_{model_name}.mat"))
        
        if dcm_candidates:
            dcm_files.append(str(dcm_candidates[0]))
            dcm_subjects.append(participant_id)
            logger.debug("Found DCM for %s: %s", participant_id, dcm_candidates[0])
        else:
            logger.warning(
                "No DCM_%s.mat found for %s. This subject will be skipped.",
                model_name, participant_id
            )
    
    return dcm_files, dcm_subjects


def parse_categorical_contrast(contrast_str, class_labels):
    """Parse a group-contrast expression into per-class weights.

    Accepts expressions like ``"control - patient"`` or
    ``"0.5*g1 + 0.5*g2 - g3"``.  Class names must match the levels found
    in the participants file column.

    Parameters
    ----------
    contrast_str : str
        Human-readable contrast expression.
    class_labels : list of str
        Ordered list of unique class labels (from participants file column).

    Returns
    -------
    weights : np.ndarray, shape (len(class_labels),)
        Coefficient for each class in ``class_labels`` order.
    safe_name : str
        Filename-safe string derived from the contrast expression.
    """
    weights = {lbl: 0.0 for lbl in class_labels}
    s = contrast_str.strip()
    # Prepend implicit '+' so the regex always sees a leading sign
    if s and s[0] not in '+-':
        s = '+' + s

    # Match:  sign  [coef *]  label   (label = word chars: letters, digits, _)
    token_re = re.compile(r'([+-])\s*(?:(\d*\.?\d+)\s*\*)?\s*(\w+)')

    matched = False
    for m in token_re.finditer(s):
        sign_s, coef_s, label = m.groups()
        if label not in weights:
            raise ValueError(
                f"Class '{label}' not found in {class_labels!r}. "
                "Check that the contrast label exactly matches a level in "
                "the participants file column."
            )
        sign = 1.0 if sign_s == '+' else -1.0
        coef = float(coef_s) if coef_s else 1.0
        weights[label] += sign * coef
        matched = True

    if not matched:
        raise ValueError(
            f"Could not parse any class names from '{contrast_str}'. "
            f"Available classes: {class_labels}"
        )

    weights_arr = np.array([weights[lbl] for lbl in class_labels], dtype=float)

    # Build filename-safe name
    safe = contrast_str.strip()
    safe = re.sub(r'\s*\+\s*', '_plus_', safe)
    safe = re.sub(r'\s*-\s*', '_vs_', safe)
    safe = re.sub(r'[^\w]', '_', safe)
    safe = re.sub(r'_+', '_', safe).strip('_')

    return weights_arr, safe


def _build_orthogonal_group_columns(contrast_weights, group_idx_per_subject,
                                    n_classes, logger):
    """Build K-1 columns for K group classes, all orthogonal to the intercept.

    Column 0 encodes the user-specified contrast (de-meaned so its sum is
    zero, making it orthogonal to the all-ones intercept added by SPM).
    For K > 2, additional K-2 columns spanning the remaining group space
    are appended via Gram-Schmidt.

    **Why de-mean instead of 1/sqrt(N_k)?**
    For a [1, -1] contrast, de-meaning gives β₁ = (μ₁ - μ₂) / 2
    independently of group-size balance — a clean interpretable quantity.
    Weighting by 1/sqrt(N_k) changes that interpretation without benefit.

    Parameters
    ----------
    contrast_weights : np.ndarray, shape (K,)
        Coefficient for each of the K classes.
    group_idx_per_subject : np.ndarray, shape (N,), dtype int
        Zero-based group index for each subject.
    n_classes : int
        Number of groups K.
    logger : logging.Logger

    Returns
    -------
    columns : np.ndarray, shape (N, K-1)
        Orthogonal contrast columns (all orthogonal to [1, …, 1]).
    """
    N = len(group_idx_per_subject)
    K = n_classes
    N_k = np.array(
        [np.sum(group_idx_per_subject == k) for k in range(K)], dtype=float
    )
    logger.debug("Group sizes (class 0..%d): %s", K - 1, N_k.astype(int).tolist())

    # Group indicator matrix G  (N × K)
    G = np.zeros((N, K))
    for i, k in enumerate(group_idx_per_subject):
        G[i, int(k)] = 1.0

    # --- Primary contrast column: de-mean so sum = 0 ---
    raw = G @ contrast_weights          # value c_k for each subject
    col0 = raw - np.mean(raw)           # subtract grand mean → sum = 0

    norm0 = np.linalg.norm(col0)
    if norm0 < 1e-10:
        raise ValueError(
            "Primary contrast regressor has near-zero variance after de-meaning. "
            "Contrast weights may be proportional to group sizes. "
            f"Weights: {contrast_weights.tolist()}, "
            f"Group sizes: {N_k.astype(int).tolist()}"
        )

    if K == 2:
        logger.debug("2-class design: primary contrast column L2-norm = %.4f", norm0)
        return col0.reshape(-1, 1)

    # --- K > 2: Gram-Schmidt extension ---
    # De-meaned group indicators span a (K-1)-dimensional space.
    H = G - G.mean(axis=0)  # each column sums to zero → orthogonal to intercept

    q0 = col0 / norm0       # unit-norm version of primary direction
    ortho = []
    for k in range(K):
        if len(ortho) == K - 2:
            break
        v = H[:, k].copy()
        v -= np.dot(v, q0) * q0           # remove primary direction
        for q in ortho:
            v -= np.dot(v, q) * q         # remove already-found directions
        nv = np.linalg.norm(v)
        if nv > 1e-8:
            ortho.append(v / nv)

    if len(ortho) < K - 2:
        raise ValueError(
            f"Gram-Schmidt produced only {len(ortho) + 1} of the required "
            f"{K - 1} orthogonal columns. "
            "Check for empty groups or degenerate group assignments."
        )

    logger.debug(
        "%d-class design: L2-norm primary=%.4f; %d orthogonal extension(s) added",
        K, norm0, len(ortho),
    )

    # Scale additional columns to same L2-norm as the primary (comparability)
    extra = np.column_stack([norm0 * q for q in ortho])
    return np.column_stack([col0, extra])


def _save_design_matrix_tsv(X, regressor_names, dcm_subjects,
                             output_dir, model_name, contrast_name, logger):
    """Save the PEB design matrix to a TSV file for quality control.

    Parameters
    ----------
    X : np.ndarray, shape (N, n_col)
        Full covariate matrix including the intercept as column 0.
    regressor_names : list of str
        Column names for X (first entry is 'intercept').
    dcm_subjects : list of str
        Subject IDs (without 'sub-' prefix), same order as rows of X.
    output_dir : Path
    model_name : str
    contrast_name : str or None
    logger : logging.Logger
    """
    df = pd.DataFrame(X, columns=regressor_names)
    df.insert(0, 'participant_id', [f"sub-{s}" for s in dcm_subjects])

    suffix = f"_{contrast_name}" if contrast_name else ""
    tsv_path = output_dir / f"xPEB_{model_name}{suffix}_design_matrix.tsv"
    df.to_csv(tsv_path, sep='\t', index=False, float_format='%.6f')
    logger.info(
        "Design matrix (N=%d, columns=%s) saved to: %s",
        len(dcm_subjects), regressor_names, tsv_path,
    )


def _build_covariate_matrix(participants_df, dcm_subjects, regressors,
                             categorical_regressors, contrast_str, logger):
    """Build covariate matrix for PEB.

    Categorical regressors are handled via a contrast-based orthogonal coding:
    rather than simple dummy coding (which creates a singular design when SPM
    adds its own intercept), K-1 columns are built that are all orthogonal
    to SPM's intercept.  The first column encodes the user-specified contrast;
    additional columns (K > 2 classes) complete the group space via
    Gram-Schmidt.  See :func:`_build_orthogonal_group_columns` for details.

    Parameters
    ----------
    participants_df : pd.DataFrame
    dcm_subjects : list of str
    regressors : list of str
    categorical_regressors : list of str
    contrast_str : str or None
        Contrast expression for categorical regressors,
        e.g. ``"control - patient"`` or ``"0.5*g1 + 0.5*g2 - g3"``.
    logger : logging.Logger

    Returns
    -------
    X : np.ndarray, shape (N, n_col)
        Covariate matrix.  Column 0 is the intercept (all ones).
    regressor_names : list of str
        Column names for X (first entry is 'intercept').
    contrast_name_safe : str or None
        Filename-safe version of the contrast string, or None if no
        categorical regressor was processed.
    """
    # Filter to subjects with DCM files
    dcm_subjects_df = participants_df[
        participants_df['participant_id'].str.replace("sub-", "").isin(dcm_subjects)
    ].reset_index(drop=True)

    if len(dcm_subjects_df) != len(dcm_subjects):
        logger.debug(
            "Only %d of %d DCM subjects mapped from participants file.",
            len(dcm_subjects_df), len(dcm_subjects),
        )

    X = np.ones((len(dcm_subjects_df), 1))
    regressor_names = ['intercept']
    contrast_name_safe = None

    # --contrast "intercept" is a special keyword meaning: the user wants the
    # intercept effect (grand mean) but may still include continuous regressors
    # as confounds.  Categorical regressors cannot be encoded without a
    # class-level contrast, so they are skipped with a warning in this mode.
    intercept_only_contrast = (
        contrast_str is not None and contrast_str.strip().lower() == 'intercept'
    )
    if intercept_only_contrast:
        contrast_name_safe = 'intercept'
        logger.info(
            "--contrast 'intercept': design matrix will include continuous "
            "regressors as confounds; categorical regressors will be skipped."
        )

    if not regressors:
        return X, regressor_names, contrast_name_safe

    for reg in regressors:
        if reg not in dcm_subjects_df.columns:
            logger.error("Regressor '%s' not found in participants file.", reg)
            continue

        col_data = dcm_subjects_df[reg].values

        if reg in categorical_regressors:
            # --- Contrast-based orthogonal coding ---
            # When --contrast "intercept" is in effect, categorical regressors
            # cannot be encoded (no class-level contrast available) → skip.
            if intercept_only_contrast:
                logger.warning(
                    "Skipping categorical regressor '%s' because --contrast "
                    "'intercept' was specified (no class-level contrast available).",
                    reg,
                )
                continue

            # Filter NaN before calling np.unique — mixed float/str columns
            # (pandas reads missing values as float NaN) cause numpy's internal
            # sort to raise TypeError when string and float are compared.
            col_data_nonan = col_data[pd.notna(col_data)]
            unique_vals = sorted(np.unique(col_data_nonan).tolist())
            K = len(unique_vals)
            logger.info(
                "Categorical regressor '%s': %d classes: %s", reg, K, unique_vals
            )

            if contrast_str is None:
                logger.error(
                    "Categorical regressor '%s' requires --contrast to be specified "
                    "(e.g. --contrast \"control - patient\").",
                    reg,
                )
                sys.exit(1)

            # Map group labels → 0-based integer indices
            label_to_idx = {lbl: i for i, lbl in enumerate(unique_vals)}
            group_idx = np.array([label_to_idx[v] for v in col_data], dtype=int)

            # Parse contrast string → per-class weights
            try:
                weights, contrast_name_safe = parse_categorical_contrast(
                    contrast_str, unique_vals
                )
            except ValueError as exc:
                logger.error("Invalid contrast for '%s': %s", reg, exc)
                sys.exit(1)

            logger.info(
                "Contrast '%s' → per-class weights: %s",
                contrast_str,
                dict(zip(unique_vals, weights.round(4).tolist())),
            )

            # Build K-1 orthogonal columns
            try:
                cat_cols = _build_orthogonal_group_columns(
                    weights, group_idx, K, logger
                )
            except ValueError as exc:
                logger.error(
                    "Failed to build group columns for '%s': %s", reg, exc
                )
                sys.exit(1)

            # Column names: first = contrast, rest = Gram-Schmidt extensions
            col_names = [f"{reg}_{contrast_name_safe}"]
            for orth_i in range(K - 2):
                col_names.append(f"{reg}_orth{orth_i + 2}")

            X = np.column_stack((X, cat_cols))
            regressor_names.extend(col_names)
            logger.info(
                "Added %d column(s) for categorical '%s': %s",
                K - 1, reg, col_names,
            )

        else:
            # --- Continuous regressor: add as-is; missing values are an error ---
            col_data_clean = col_data.astype(float)
            if np.any(np.isnan(col_data_clean)):
                bad_subjects = dcm_subjects_df.loc[
                    np.isnan(col_data_clean), 'participant_id'
                ].tolist()
                logger.error(
                    "Regressor '%s' has missing values (n/a) for %d subject(s): %s. "
                    "Please fill or remove them before running group-level analysis.",
                    reg, len(bad_subjects), bad_subjects,
                )
                sys.exit(1)
            X = np.column_stack((X, col_data_clean))
            regressor_names.append(reg)
            logger.debug("Added continuous regressor '%s'", reg)

    logger.info(
        "Covariate matrix shape: %s (columns: %s)", X.shape, regressor_names
    )
    return X, regressor_names, contrast_name_safe


def _build_peb_matlab_direct(dcm_mat_paths, group_name, model_name, model_name_bids,
                             X, regressor_names, analysis_type,
                             output_dir, xpeb_output_path, contrast_name_safe=None):
    """Generate MATLAB code that calls spm_dcm_peb directly (not via batch).

    This approach gives us full control over where output files are saved and
    avoids the SPM batch mechanism, which would save PEB_*.mat to the first
    subject's directory instead of group/SPM/.

    Parameters
    ----------
    dcm_mat_paths : list of str
        Full paths to first-level DCM .mat files (one per subject).
    group_name : str
        Name for the group analysis (passed to PEB as M.X label).
    model_name : str
        Raw DCM model name (used in MATLAB comments).
    model_name_bids : str
        BIDS-safe model name (used in output filenames).
    X : np.ndarray, shape (N, n_col)
        Covariate matrix including intercept as column 0.
    regressor_names : list of str
        Column names for X (first entry is 'intercept').
    analysis_type : str
        'csd' for resting-state, 'timeseries' for task.
    output_dir : Path
        Directory where all group outputs should be saved (group/SPM/).
    xpeb_output_path : Path
        Full path for the xPEB output .mat file.
    contrast_name_safe : str or None
        BIDS-safe contrast name (if from categorical regressor). Used to suffix
        output filenames. If None, filenames use model_name_bids only.

    Returns
    -------
    str
        Complete MATLAB code (to be passed as pre_code).
    """
    L = []  # lines

    # ------------------------------------------------------------------
    # 1. Load first-level DCMs into a cell array (GCM)
    # ------------------------------------------------------------------
    L.append(f"%% Group-level DCM (PEB) for model: {model_name}")
    L.append("%% Step 1: Load first-level DCMs into GCM cell array")
    dcm_paths_cell = "{\n" + "\n".join(f"  '{p}';" for p in dcm_mat_paths) + "\n}"
    L.append(f"dcm_filenames = {dcm_paths_cell};")
    L.append("GCM = spm_dcm_load(dcm_filenames);")
    L.append("")

    # ------------------------------------------------------------------
    # 2. Build PEB design matrix M
    # ------------------------------------------------------------------
    N = X.shape[0]
    n_col = X.shape[1]
    L.append("%% Step 2: Build PEB design matrix M")
    L.append(f"M.X = [{'; '.join(' '.join(f'{v:.6f}' for v in row) for row in X)}];")
    L.append(f"M.Xnames = {{{', '.join(repr(n) for n in regressor_names)}}};")
    L.append("")

    # PEB prior settings (matching the old batch defaults)
    L.append("%% PEB prior settings")
    L.append("M.alpha = 1;")
    L.append("M.beta  = 16;")
    L.append("M.hE    = 0;")
    L.append("M.hC    = 1/16;")
    L.append("")

    # ------------------------------------------------------------------
    # 3. Specify DCM parameter fields
    # ------------------------------------------------------------------
    L.append("%% Step 3: Specify parameter fields to model at group level")
    if analysis_type == "csd" or "rest" in model_name.lower():
        L.append("field = {'A'};")
    else:
        L.append("field = {'A', 'B', 'C'};")
    L.append("")

    # ------------------------------------------------------------------
    # 4. Run spm_dcm_peb
    # ------------------------------------------------------------------
    L.append("%% Step 4: Run PEB estimation")
    L.append("fprintf('Running spm_dcm_peb for model: " + model_name + "\\n');")
    L.append("[PEB, GCM] = spm_dcm_peb(GCM, M, field);")
    L.append("fprintf('PEB estimation complete.\\n');")
    L.append("")

    # ------------------------------------------------------------------
    # 5. Compute posterior probabilities
    # ------------------------------------------------------------------
    L.append("%% Step 5: Compute posterior probabilities")
    L.append("np = length(PEB.Pnames);")
    L.append("nc = size(PEB.Ep, 2);")
    L.append("Ep_full = full(PEB.Ep);")
    L.append("Cp_full = full(PEB.Cp);")
    L.append("Pp_all  = zeros(np * nc, 1);")
    L.append("Cp_diag = diag(Cp_full);")
    L.append("for eff = 1:nc")
    L.append("  idx_start = (eff-1)*np + 1;")
    L.append("  idx_end   = eff*np;")
    L.append("  Ep_k = Ep_full(:, eff);")
    L.append("  Cp_k = Cp_diag(idx_start:idx_end);")
    L.append("  Pp_all(idx_start:idx_end) = 1 - spm_Ncdf(0, abs(Ep_k(:)), Cp_k(:));")
    L.append("end")
    L.append(f"fprintf('Computed %d posterior probabilities.\\n', length(Pp_all));")
    L.append("")

    # ------------------------------------------------------------------
    # 6. Build xPEB struct
    # ------------------------------------------------------------------
    L.append("%% Step 6: Build xPEB struct for downstream use")
    L.append("xPEB.PEB = PEB;")
    L.append("xPEB.DCM = GCM;")
    L.append("xPEB.Pp  = Pp_all;")
    
    # Extract VOI region names from first-level DCM xY structure (definitive source)
    # This ensures we capture the ACTUAL VOI names used in the first-level analysis,
    # NOT config file names which may be declarative rather than verified actual values.
    # SPM output (PEB.Pnames) remains unchanged as A(i,j) format.
    L.append("% Extract VOI names from first DCM's xY structure (definitive source)")
    L.append("% This preserves the actual VOI definitions from first-level analysis")
    L.append("xPEB.region_names = {};")
    L.append("if ~isempty(GCM) && isfield(GCM{1}, 'xY')")
    L.append("  if iscell(GCM{1}.xY)")
    L.append("    for i = 1:length(GCM{1}.xY)")
    L.append("      if isfield(GCM{1}.xY{i}, 'name') && ~isempty(GCM{1}.xY{i}.name)")
    L.append("        xPEB.region_names{i} = GCM{1}.xY{i}.name;")
    L.append("      else")
    L.append("        xPEB.region_names{i} = sprintf('VOI_%d', i);")
    L.append("      end")
    L.append("    end")
    L.append("  elseif isfield(GCM{1}.xY, 'name')")
    L.append("    xPEB.region_names = {GCM{1}.xY.name};")
    L.append("  end")
    L.append("end")
    L.append("if isempty(xPEB.region_names)")
    L.append("  fprintf('WARNING: Could not extract VOI names from first-level DCMs.\\n');")
    L.append("end")
    
    L.append("")

    # ------------------------------------------------------------------
    # 7. Ensure output directory exists
    # ------------------------------------------------------------------
    out_dir_escaped = str(output_dir).replace("'", "''")
    L.append("%% Step 7: Ensure output directory exists")
    L.append(f"out_dir = '{out_dir_escaped}';")
    L.append("if ~isfolder(out_dir)")
    L.append("  mkdir(out_dir);")
    L.append("end")
    L.append("")

    # ------------------------------------------------------------------
    # 8. Save xPEB_{model_name_bids}.mat (full results struct)
    # ------------------------------------------------------------------
    xpeb_out = str(xpeb_output_path).replace("'", "''")
    L.append("%% Step 8: Save xPEB results")
    L.append(f"xpeb_out_path = '{xpeb_out}';")
    L.append("fprintf('Saving xPEB to: %s\\n', xpeb_out_path);")
    L.append("save(xpeb_out_path, 'xPEB', '-v7.3');")
    L.append(f"fprintf('SUCCESS: xPEB_{model_name_bids}.mat saved.\\n');")
    L.append("")

    # ------------------------------------------------------------------
    # 9. Save DCM_{model_name_bids}.mat — extracted from xPEB.DCM
    #    (same pattern as PEB extracted from xPEB.PEB below)
    # ------------------------------------------------------------------
    dcm_out = str(output_dir / f"DCM_{model_name_bids}.mat").replace("'", "''")
    L.append(f"%% Step 9: Save DCM_{model_name_bids}.mat (group DCM, from xPEB.DCM)")
    L.append(f"dcm_out_path = '{dcm_out}';")
    L.append("DCM = xPEB.DCM;")
    L.append("fprintf('Saving DCM to: %s\\n', dcm_out_path);")
    L.append("save(dcm_out_path, 'DCM', '-v7.3');")
    L.append(f"fprintf('SUCCESS: DCM_{model_name_bids}.mat saved.\\n');")
    L.append("")

    # ------------------------------------------------------------------
    # 10. Save PEB_{model_name_bids}[_{contrast}].mat — extracted from xPEB.PEB
    # ------------------------------------------------------------------
    suffix = f"_{contrast_name_safe}" if contrast_name_safe else ""
    peb_out = str(output_dir / f"PEB_{model_name_bids}{suffix}.mat").replace("'", "''")
    L.append(f"%% Step 10: Save PEB_{model_name_bids}{suffix}.mat (standalone PEB struct, from xPEB.PEB)")
    L.append(f"peb_out_path = '{peb_out}';")
    L.append("PEB = xPEB.PEB;")
    L.append("fprintf('Saving PEB to: %s\\n', peb_out_path);")
    L.append("save(peb_out_path, 'PEB', '-v7.3');")
    L.append(f"fprintf('SUCCESS: PEB_{model_name_bids}{suffix}.mat saved.\\n');")

    return "\n".join(L)
