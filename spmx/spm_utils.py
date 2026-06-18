"""SPM file utilities for spmx.

Helpers for renaming SPM output files to BIDS conventions, creating JSON
sidecars, compressing NIfTI outputs, and handling sourcedata.
"""

import shutil
from pathlib import Path

from spmx.bids_utils import (
    build_bids_filename,
    compress_nifti,
    write_json_sidecar,
)


def setup_sourcedata(output_dir, subject, session=None):
    """Create the sourcedata directory structure for a subject.

    Returns
    -------
    Path
        Path to the subject (and session) sourcedata directory.
    """
    src = Path(output_dir) / "sourcedata" / f"sub-{subject}"
    if session:
        src = src / f"ses-{session}"
    src.mkdir(parents=True, exist_ok=True)
    return src


def copy_to_output(src_path, output_dir, entities, suffix, extension,
                   description=None):
    """Copy a file to the output directory with BIDS naming.

    Returns
    -------
    Path
        Destination path.
    """
    dest_dir = Path(output_dir) / f"sub-{entities['sub']}"
    if entities.get("ses"):
        dest_dir = dest_dir / f"ses-{entities['ses']}"
    dest_dir = dest_dir / "func"
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = build_bids_filename(entities, suffix, extension, description)
    dest = dest_dir / fname
    shutil.copy2(str(src_path), str(dest))
    return dest


def rename_spm_output(spm_file, output_dir, entities, suffix, extension,
                      description=None, metadata=None, compress=False):
    """Rename an SPM output file to BIDS conventions and create sidecar.

    Parameters
    ----------
    spm_file : Path
        Path to the original SPM output file.
    output_dir : Path
        Root output directory.
    entities : dict
        BIDS entities (sub, ses, task, space, etc).
    suffix : str
        BIDS suffix.
    extension : str
        Target extension (e.g. '.nii.gz', '.mat').
    description : str or None
        desc- entity value.
    metadata : dict or None
        Metadata for the JSON sidecar.
    compress : bool
        If True and extension is '.nii.gz', compress the file.

    Returns
    -------
    Path
        Path to the renamed file.
    """
    dest_dir = Path(output_dir) / f"sub-{entities['sub']}"
    if entities.get("ses"):
        dest_dir = dest_dir / f"ses-{entities['ses']}"
    dest_dir = dest_dir / "func"
    dest_dir.mkdir(parents=True, exist_ok=True)

    fname = build_bids_filename(entities, suffix, extension, description)
    dest = dest_dir / fname

    spm_file = Path(spm_file)

    if compress and extension == ".nii.gz" and spm_file.suffix == ".nii":
        compress_nifti(spm_file, dest)
    else:
        shutil.copy2(str(spm_file), str(dest))

    if metadata is None:
        metadata = {}
    metadata.setdefault("Sources", str(spm_file.name))
    write_json_sidecar(dest, metadata)

    return dest


def setup_log_dir(output_dir, subject, session=None):
    """Create and return the log directory for a subject.

    Returns
    -------
    Path
    """
    log_dir = Path(output_dir) / "logs" / f"sub-{subject}"
    if session:
        log_dir = log_dir / f"ses-{session}"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
