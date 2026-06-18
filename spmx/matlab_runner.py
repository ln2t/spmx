"""MATLAB runner for spmx.

Generates MATLAB scripts from templates, executes them via the MATLAB CLI,
and captures output.
"""

import os
import subprocess
import tempfile
from pathlib import Path


def generate_matlab_script(spm_path, matlabbatch_code, pre_code="", post_code="",
                           clean_path=False, skip_batch=False, logger=None):
    """Build the full MATLAB script string.

    Parameters
    ----------
    spm_path : str
        Path to SPM installation to add to MATLAB path.
    matlabbatch_code : str
        The matlabbatch variable assignments.  Ignored when ``skip_batch``
        is True.
    pre_code : str
        MATLAB code to run before the batch (after addpath).
    post_code : str
        MATLAB code to run after the batch.
    clean_path : bool
        If True, call ``restoredefaultpath()`` at the top of the script to
        reset the MATLAB search path to factory defaults before adding SPM.
        This removes all toolboxes that are not part of the MATLAB
        installation itself, including toolboxes installed inside
        ``matlabroot`` but not shipped by MathWorks.  Unlike a simple
        ``matlabroot``-prefix filter, ``restoredefaultpath`` uses MATLAB's
        internal manifest of factory-default paths and is therefore reliable
        regardless of where third-party toolboxes are installed.
    skip_batch : bool
        If True, skip the ``matlabbatch`` code and ``spm_jobman`` call
        entirely.  Use this when all MATLAB logic is provided via
        ``pre_code`` / ``post_code`` and no SPM batch is needed.
    logger : logging.Logger or None

    Returns
    -------
    str
        Complete MATLAB script.
    """
    if logger:
        logger.debug(
            "MATLAB script options: clean_matlab_path=%s, skip_batch=%s",
            clean_path, skip_batch,
        )
    lines = []
    if clean_path:
        lines.append("% Reset path to factory defaults — removes all non-MathWorks toolboxes")
        lines.append("restoredefaultpath();")
        lines.append("")
    lines.append(f"addpath('{spm_path}');")
    lines.append("spm('defaults', 'FMRI');")
    lines.append("spm_jobman('initcfg');")
    lines.append("spm_get_defaults('cmdline', true);")
    lines.append("")
    if pre_code:
        lines.append(pre_code)
        lines.append("")
    if not skip_batch:
        lines.append(matlabbatch_code)
        lines.append("")
        lines.append("spm_jobman('run', matlabbatch);")
        lines.append("")
    if post_code:
        lines.append(post_code)
        lines.append("")
    lines.append("exit;")
    return "\n".join(lines)


def run_matlab_script(script_content, matlab_path="matlab", work_dir=None,
                      logger=None, log_script_path=None, single_comp_thread=False,
                      clean_path=False):
    """Write script to a temp file and execute it with MATLAB.

    Parameters
    ----------
    script_content : str
        Full MATLAB script.
    matlab_path : str
        Path to MATLAB executable.
    work_dir : Path or None
        Working directory for MATLAB process.
    logger : logging.Logger or None
    log_script_path : Path or None
        If provided, save the script to this path for debugging.
    single_comp_thread : bool
        If True, pass ``-singleCompThread`` to MATLAB, limiting it to a single
        computational thread.  This can work around threading-related crashes
        (e.g. segfaults in the MATLAB thread pool on certain AMD CPUs with
        MATLAB R2025b).  Has no effect on the GTP internal thread pool.
    clean_path : bool
        If True, clear the ``MATLABPATH`` environment variable before
        launching MATLAB so that externally-installed toolboxes are not
        added to the search path during MATLAB startup.  Works in tandem
        with the ``restoredefaultpath()`` call emitted by
        ``generate_matlab_script`` when ``clean_path=True``.

    Returns
    -------
    subprocess.CompletedProcess

    Raises
    ------
    RuntimeError
        If MATLAB exits with a non-zero return code.
    """
    if log_script_path is not None:
        log_script_path = Path(log_script_path)
        log_script_path.parent.mkdir(parents=True, exist_ok=True)
        log_script_path.write_text(script_content)
        if logger:
            logger.debug("MATLAB script saved to %s", log_script_path)

    if logger:
        logger.debug(
            "MATLAB runner options: single_comp_thread=%s, clean_path=%s",
            single_comp_thread, clean_path,
        )

    # Build subprocess environment
    env = os.environ.copy()
    if clean_path:
        env["MATLABPATH"] = ""

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".m", delete=False, dir=work_dir, prefix="spmx_"
    ) as tmp:
        tmp.write(script_content)
        tmp_path = Path(tmp.name)

    script_name = tmp_path.stem
    run_dir = str(tmp_path.parent)

    cmd = [
        str(matlab_path),
        "-nodisplay",
        "-nosplash",
        "-nodesktop",
    ]
    if single_comp_thread:
        cmd.append("-singleCompThread")
    cmd += ["-batch", f"run('{tmp_path}')"]

    if logger:
        logger.info("Running MATLAB: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=run_dir,
        env=env,
    )

    # Clean up temp file
    try:
        tmp_path.unlink()
    except OSError:
        pass

    if logger:
        if result.stdout:
            logger.debug("MATLAB stdout:\n%s", result.stdout)
        if result.stderr:
            logger.debug("MATLAB stderr:\n%s", result.stderr)

    if result.returncode != 0:
        extra = ""
        if result.returncode < 0:
            import signal
            sig = -result.returncode
            sig_name = next(
                (s.name for s in signal.Signals if s.value == sig), str(sig)
            )
            extra = (
                f"\nNote: MATLAB was killed by signal {sig} ({sig_name}). "
                "This usually indicates a MATLAB internal crash (segfault) or "
                "an out-of-memory condition. "
                "If you are using MATLAB R2025b on an AMD Zen‑5 CPU, this is a known "
                "MATLAB threading bug. Workarounds: (1) add 'single_comp_thread: true' "
                "to your spmx config; (2) downgrade to MATLAB R2024b."
            )
        raise RuntimeError(
            f"MATLAB exited with code {result.returncode}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}{extra}"
        )

    return result
