"""Extract and export PEB (xPEB) results to TSV and JSON files.

This module loads xPEB results from MATLAB .mat files and exports key
results to TSV and JSON formats for downstream analysis.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Try to import h5py for v7.3 files, fall back gracefully
try:
    import h5py
    HAS_H5PY = True
except ImportError:
    HAS_H5PY = False

try:
    import scipy.io as sio
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# Note: Probability computation is now done during PEB estimation in group_dcm.py


def _load_matlab_file(mat_path, logger=None):
    """Load MATLAB .mat file, trying h5py first (v7.3), then scipy (older versions).
    
    Parameters
    ----------
    mat_path : Path or str
        Path to .mat file
    logger : logging.Logger, optional
        Logger for debug output
    
    Returns
    -------
    dict
        Dictionary containing the loaded data
    """
    mat_path = Path(mat_path)
    
    # Try h5py first (modern MATLAB v7.3 HDF5 format is most common)
    if HAS_H5PY:
        try:
            return _load_matlab_h5py(mat_path, logger=logger)
        except (OSError, KeyError, RuntimeError) as e:
            # h5py failed - likely not an HDF5 file, try scipy
            if logger:
                logger.debug(f"h5py loader failed: {e}, trying scipy...")
            pass
    
    # Fall back to scipy for older MATLAB formats
    if HAS_SCIPY:
        try:
            return sio.loadmat(str(mat_path), simplify_cells=True)
        except NotImplementedError as e:
            # scipy detected v7.3 but can't read it
            raise RuntimeError(
                f"File appears to be MATLAB v7.3 format but h5py is not installed. "
                f"Install h5py with: pip install h5py"
            ) from e
    
    # Both loaders unavailable
    raise ImportError(
        "Neither h5py nor scipy is available. "
        "Install with: pip install h5py scipy"
    )


def _load_matlab_h5py(mat_path, logger=None):
    """Load MATLAB v7.3 file using h5py.
    
    Parameters
    ----------
    mat_path : Path or str
        Path to .mat file
    logger : logging.Logger, optional
        Logger for debug output
    
    Returns
    -------
    dict
        Dictionary with extracted data
    """
    with h5py.File(mat_path, 'r') as f:
        if logger:
            logger.debug(f"HDF5 file contents (top level): {list(f.keys())}")
        
        # Recursively extract data from HDF5 groups
        def _extract_group(group, path=""):
            result = {}
            for key in group.keys():
                item = group[key]
                current_path = f"{path}/{key}" if path else key
                
                if isinstance(item, h5py.Dataset):
                    # Convert dataset to numpy array
                    try:
                        data = np.array(item)
                        result[key] = data
                        if logger and key in ['xPEB', 'Ep', 'Cp', 'Eg']:
                            logger.debug(f"  Extracted dataset {current_path}: shape={data.shape if hasattr(data, 'shape') else 'N/A'}, dtype={data.dtype}")
                    except Exception as e:
                        if logger:
                            logger.debug(f"  Failed to extract dataset {current_path}: {e}")
                        result[key] = item
                elif isinstance(item, h5py.Group):
                    # Recursively handle nested groups
                    if logger and key in ['xPEB', 'DCM']:
                        logger.debug(f"  Found group {current_path} with contents: {list(item.keys())}")
                    result[key] = _extract_group(item, current_path)
            return result
        
        data = _extract_group(f)
    
    return data






def _convert_parameter_names(param_indices, roi_names):
    """Convert SPM Pnames like ``A(i,j)`` to human-readable connectivity labels.

    In SPM's DCM convention ``A(i,j)`` encodes the influence of region *j*
    (source / column) on region *i* (target / row).  The resulting label is
    therefore ``"source→target"`` = ``"roi_names[j]→roi_names[i]"``.

    SPM vectorises the A matrix in MATLAB column-major order, so the Pnames
    list arrives as::

        A(1,1), A(2,1), A(3,1), …, A(n,1),   ← source=ROI1, varying target
        A(1,2), A(2,2), …, A(n,2),            ← source=ROI2, varying target
        …

    which matches the label ordering ``roi_names[j]→roi_names[i]`` (source
    cycles slowly, target cycles fast).

    Note: ``roi_names`` must be in the SAME order as the ROIs were entered
    when defining the first-level DCMs — SPM does *not* sort them.

    Args:
        param_indices: List of Pname strings like ``["A(1,1)", "A(2,1)", "A(1,2)", …]``.
        roi_names: List of ROI names in original DCM-definition order,
                   e.g. ``["mPFC", "LIPL", "RIPL", "PCC"]``.

    Returns:
        List of labels like ``["mPFC→mPFC", "mPFC→LIPL", "LIPL→mPFC", …]``.
        For ``A(i,j)``: label = ``roi_names[j]→roi_names[i]``
        (source j → target i).
    """
    labels = []
    for param in param_indices:
        try:
            content = param.strip().split('(')[1].split(')')[0]
            row_col = content.split(',')
            i = int(row_col[0].strip()) - 1  # row index → target (0-based)
            j = int(row_col[1].strip()) - 1  # col index → source (0-based)
            if i < len(roi_names) and j < len(roi_names):
                label = f"{roi_names[j]}→{roi_names[i]}"  # source→target
            else:
                label = param  # index out of range, keep raw Pname
        except Exception:
            label = param  # parse error, keep raw Pname
        labels.append(label)
    return labels


def _generate_parameter_labels(np_, roi_names):
    """Generate A-matrix parameter labels from ROI names without requiring Pnames.

    Uses the same MATLAB column-major ordering that SPM applies when
    vectorising the DCM A matrix:

    * **Source** (column *j* of A) cycles **slowly** (outer loop).
    * **Target** (row *i* of A) cycles **fast** (inner loop).
    * Label format: ``"source→target"`` (same as SPM GUI display).

    For 4 ROIs ``[mPFC, LIPL, RIPL, PCC]`` the first few labels are::

        mPFC→mPFC   (index 1)
        mPFC→LIPL   (index 2)
        mPFC→RIPL   (index 3)
        mPFC→PCC    (index 4)
        LIPL→mPFC   (index 5)
        …
        PCC→PCC     (index 16)

    Args:
        np_: Expected total number of DCM A-matrix parameters.
        roi_names: ROI names in original DCM-definition order (not sorted).

    Returns:
        List[str] of labels, or ``None`` if ``np_`` ≠ ``len(roi_names)²``
        (e.g. when B/C-matrix parameters are also included).
    """
    n = len(roi_names)
    if n == 0 or np_ != n * n:
        return None
    # Outer loop = source (j, column of A), inner loop = target (i, row of A)
    return [f"{roi_names[j]}→{roi_names[i]}" for j in range(n) for i in range(n)]


def extract_and_export_peb_results(xpeb_mat_path, output_dir=None, logger=None):
    """Load xPEB results and export key tables to TSV files.
    
    Probabilities are computed during PEB estimation and extracted here.
    
    Parameters
    ----------
    xpeb_mat_path : Path or str
        Path to xPEB_[model].mat file
    output_dir : Path or str, optional
        Directory to save TSV files. Defaults to same directory as xpeb_mat_path
    logger : logging.Logger, optional
        Logger for status messages
    
    Returns
    -------
    dict
        Dictionary with keys: 'ep', 'cp', 'eg', 'pp', 'xnames', 'roi_names'
        Contains the extracted xPEB data
    """
    xpeb_mat_path = Path(xpeb_mat_path)
    
    if not xpeb_mat_path.exists():
        msg = f"xPEB file not found: {xpeb_mat_path}"
        if logger:
            logger.error(msg)
        raise FileNotFoundError(msg)
    
    if output_dir is None:
        output_dir = xpeb_mat_path.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if logger:
        logger.info(f"Loading xPEB results from: {xpeb_mat_path}")
    
    # Load MATLAB file (handles both v7.3 and older versions)
    try:
        mat_data = _load_matlab_file(xpeb_mat_path, logger=logger)
    except (ImportError, NotImplementedError) as e:
        msg = f"Failed to load MATLAB file: {e}"
        if logger:
            logger.error(msg)
        raise RuntimeError(msg) from e
    
    if logger:
        logger.debug(f"Loaded mat_data keys: {list(mat_data.keys())}")
    
    if 'xPEB' not in mat_data:
        msg = f"xPEB variable not found in {xpeb_mat_path}. Available keys: {list(mat_data.keys())}"
        if logger:
            logger.error(msg)
        raise ValueError(msg)
    
    xpeb = mat_data['xPEB']
    if logger:
        logger.debug(f"xPEB type: {type(xpeb)}, xPEB keys: {list(xpeb.keys()) if hasattr(xpeb, 'keys') else 'N/A'}")
    
    # The actual PEB results are in xpeb['PEB'] (h5py structure from MATLAB v7.3)
    if isinstance(xpeb, dict) and 'PEB' in xpeb:
        peb = xpeb['PEB']
        if logger:
            logger.debug(f"Found nested PEB group: {type(peb)}")
    elif isinstance(xpeb, h5py.Group) and 'PEB' in xpeb:
        peb = xpeb['PEB']
        if logger:
            logger.debug(f"Found PEB group in xPEB: {type(peb)}")
    else:
        # Try to extract from xpeb directly (fallback for different MATLAB versions)
        peb = xpeb
        if logger:
            logger.debug(f"Using xpeb directly as peb: {type(peb)}")
    
    # Extract key components
    results = {}
    
    # Posterior expected values of parameters
    if isinstance(xpeb, np.ndarray):
        # xPEB might be stored as structured array or object array
        # Try to unwrap it
        if xpeb.size == 1:
            xpeb = xpeb.item()
        elif xpeb.dtype.names:  # Structured array
            # Convert structured array to dict
            xpeb = {name: xpeb[name] for name in xpeb.dtype.names}
    
    # Helper function to resolve HDF5 object references to strings
    def resolve_reference(obj_ref, file_obj=None):
        """Resolve h5py object reference, typically for strings."""
        try:
            if isinstance(obj_ref, h5py.Reference):
                resolved = file_obj[obj_ref] if file_obj else None
                if resolved is not None:
                    return np.array(resolved).astype(str)
            elif isinstance(obj_ref, np.ndarray) and obj_ref.dtype == 'O':
                # Array of object references
                return [resolve_reference(ref, file_obj) for ref in obj_ref.flat]
        except:
            pass
        return None
    
    # Helper function to convert sparse matrix (data, ir, jc format) to dense
    def sparse_to_dense(sparse_group):
        """Convert MATLAB sparse matrix format to dense array."""
        try:
            data = np.array(sparse_group.get('data', []))
            ir = np.array(sparse_group.get('ir', []), dtype=int)
            jc = np.array(sparse_group.get('jc', []), dtype=int)
            
            if len(data) == 0:
                return np.array([])
            
            # Number of columns = len(jc) - 1
            ncols = len(jc) - 1

            # Prefer the MATLAB_sparse attribute for nrows (authoritative);
            # fall back to ir.max()+1 when the attribute is absent.
            if hasattr(sparse_group, 'attrs') and 'MATLAB_sparse' in sparse_group.attrs:
                nrows = int(np.asarray(sparse_group.attrs['MATLAB_sparse']).flat[0])
            else:
                nrows = int(ir.max()) + 1 if len(ir) > 0 else 1
            
            # special case: if only 1 column, return as 1D vector
            if ncols == 1:
                # Already have the data in the right order
                return data
            
            # Otherwise, reconstruct sparse matrix (MATLAB format: column-compressed)
            matrix = np.zeros((nrows, ncols))
            for col in range(ncols):
                for idx in range(jc[col], jc[col + 1]):
                    if idx < len(ir) and idx < len(data):
                        matrix[ir[idx], col] = data[idx]
            
            return matrix
        except Exception as e:
            if logger:
                logger.debug(f"Failed to convert sparse matrix: {e}")
            return None
    
    # Helper function to safely access nested data and convert h5py objects to numpy
    def get_field(obj, field_name, xpeb_group=None):
        """Safely get field from dict-like or object-like structure."""
        val = None
        if isinstance(obj, dict):
            val = obj.get(field_name)
        elif isinstance(obj, h5py.Group) and field_name in obj:
            val = obj[field_name]
        elif hasattr(obj, field_name):
            val = getattr(obj, field_name)
        
        # Check if value is a sparse matrix dict (from _load_matlab_h5py)
        if isinstance(val, dict) and 'data' in val and 'ir' in val and 'jc' in val:
            # Convert sparse matrix dict to dense array
            data = np.asarray(val.get('data', []))
            ir = np.asarray(val.get('ir', []), dtype=int)
            jc = np.asarray(val.get('jc', []), dtype=int)
            
            if len(data) == 0:
                return np.array([])
            
            nrows = ir.max() + 1 if len(ir) > 0 else 1
            ncols = len(jc) - 1
            
            if ncols == 1:
                # Return as 1D vector
                return data
            else:
                # Return as 2D matrix
                matrix = np.zeros((nrows, ncols))
                for col in range(ncols):
                    for idx in range(jc[col], jc[col + 1]):
                        if idx < len(ir) and idx < len(data):
                            matrix[ir[idx], col] = data[idx]
                return matrix
        
        # Convert h5py objects to numpy arrays
        if val is not None:
            if isinstance(val, h5py.Group):
                # Check if it's a sparse matrix
                if 'data' in val and 'ir' in val and 'jc' in val:
                    return sparse_to_dense(val)
                # Otherwise can't handle
                return None
            elif isinstance(val, h5py.Dataset):
                return np.array(val)
        
        return val
    
    # Unwrap peb if needed
    if isinstance(peb, np.ndarray):
        peb = peb.item() if peb.size == 1 else peb[0]

    if logger:
        logger.debug(f"After unwrapping, peb type: {type(peb)}")
        if isinstance(peb, (dict, h5py.Group)):
            keys = list(peb.keys()) if hasattr(peb, 'keys') else []
            logger.debug(f"peb keys: {keys}")

    # -----------------------------------------------------------------------
    # Helper: resolve an array of h5py object references to a list of strings.
    # Also handles uint16/uint8 character arrays stored inline.
    # -----------------------------------------------------------------------
    def _resolve_str_array(raw, mat_path):
        """Return list[str] from a raw Pnames/Xnames/region_names value."""
        if raw is None:
            return []
        arr = np.asarray(raw)
        # Case 1: object reference array (h5py cell-of-strings)
        if arr.dtype == object:
            resolved = []
            try:
                with h5py.File(mat_path, 'r') as hf:
                    for ref in arr.flat:
                        try:
                            data = np.array(hf[ref][()])
                            if data.dtype in (np.uint16, np.uint8, np.int32):
                                s = ''.join(chr(int(c)) for c in data.flatten())
                            else:
                                s = str(data.flat[0]) if data.size == 1 else str(data)
                            resolved.append(s.strip())
                        except Exception:
                            resolved.append('unknown')
            except Exception as e:
                if logger:
                    logger.debug(f"Could not resolve object references: {e}")
            return resolved
        # Case 2: uint16/uint8 character array — single string stored as code points
        if arr.dtype in (np.uint16, np.uint8):
            return [''.join(chr(int(c)) for c in arr.flatten()).strip()]
        # Case 3: already string-like
        return [str(s).strip() for s in arr.flat]

    # -----------------------------------------------------------------------
    # Helper: resolve a cell array of matrices (h5py object references → list
    # of numpy arrays).  Used for PEB.M.Q (covariance component bases).
    # -----------------------------------------------------------------------
    def _resolve_mat_cell_array(raw, mat_path):
        """Return list[ndarray] from a raw MATLAB cell array of matrices.

        Handles three storage formats h5py may produce:
          - object-reference array: re-opens the file to dereference
          - already-dense 2-D/3-D array (single matrix or stacked)
          - dict from _extract_group (should not normally occur for cell arrays)
        """
        if raw is None:
            return []
        arr = np.asarray(raw)
        if arr.dtype == object:
            matrices = []
            try:
                with h5py.File(mat_path, 'r') as hf:
                    for ref in arr.flat:
                        try:
                            node = hf[ref]
                            if isinstance(node, h5py.Group):
                                # Sparse matrix stored as group with data/ir/jc
                                m = sparse_to_dense(node)
                                if m is not None and np.asarray(m).size > 0:
                                    matrices.append(np.asarray(m))
                                else:
                                    if logger:
                                        logger.debug(
                                            "M.Q cell reference is a sparse Group "
                                            "but sparse_to_dense returned empty"
                                        )
                            elif isinstance(node, h5py.Dataset):
                                m = np.asarray(node[()])
                                matrices.append(m)
                            else:
                                if logger:
                                    logger.debug(
                                        "M.Q cell reference has unexpected type: %s",
                                        type(node),
                                    )
                        except Exception as e:
                            if logger:
                                logger.debug("Could not dereference M.Q cell ref: %s", e)
            except Exception as e:
                if logger:
                    logger.debug(f"Could not resolve mat cell array: {e}")
            return matrices
        # Dense array — treat as a single matrix
        return [arr]

    # -----------------------------------------------------------------------
    # Step 1 — Extract Pnames (length == np) and Xnames (length == nc)
    # Mirror spm_dcm_peb_review.m:
    #   np = length(PEB.Pnames)
    #   nc = size(PEB.M.X, 2)
    #   if size(PEB.Ep, 2) ~= nc; PEB.Ep = reshape(PEB.Ep, np, nc); end
    # -----------------------------------------------------------------------
    pnames_list = _resolve_str_array(get_field(peb, 'Pnames', xpeb_group=peb),
                                     xpeb_mat_path)
    np_true = len(pnames_list)
    if np_true > 0:
        results['pnames'] = pnames_list
        if logger:
            logger.info(f"  ✓ Pnames ({np_true}): {pnames_list[:3]}…")
    else:
        if logger:
            logger.warning("  ✗ Pnames not found — parameter labels will be generic")

    xnames_list = _resolve_str_array(get_field(peb, 'Xnames', xpeb_group=peb),
                                     xpeb_mat_path)
    nc_from_xnames = len(xnames_list)
    if nc_from_xnames > 0:
        results['cov_names'] = xnames_list
        if logger:
            logger.info(f"  ✓ Xnames ({nc_from_xnames}): {xnames_list}")

    # -----------------------------------------------------------------------
    # Step 2 — Extract Ep and reshape to (np, nc) matrix.
    #
    # SPM may store PEB.Ep in one of several shapes in the .mat file:
    #   (a) flat (np*nc, 1) column vector → h5py gives (1, np*nc) or (np*nc,)
    #   (b) (np, nc) matrix → h5py gives (nc, np) [standard h5py transposition]
    #   (c) (nc, np) matrix → h5py gives (np, nc) [h5py transposes it back]
    #
    # IMPORTANT: do NOT blindly call .flatten() on a 2-D array — that would
    # interleave the covariate columns and produce completely wrong values.
    # -----------------------------------------------------------------------
    ep_raw = get_field(peb, 'Ep', xpeb_group=peb)
    if ep_raw is not None:
        ep_arr = np.asarray(ep_raw)
        if np_true > 0 and nc_from_xnames > 0:
            target_np, target_nc = np_true, nc_from_xnames
            if ep_arr.ndim == 2 and ep_arr.shape == (target_np, target_nc):
                # Case (c): h5py returned (np, nc) directly — already correct
                ep_matrix = ep_arr
                nc_ep = target_nc
                if logger:
                    logger.info(f"  ✓ Ep shape ({target_np},{target_nc}) — used as-is")
            elif ep_arr.ndim == 2 and ep_arr.shape == (target_nc, target_np):
                # Case (b): h5py standard transposition → need .T
                ep_matrix = ep_arr.T
                nc_ep = target_nc
                if logger:
                    logger.info(f"  ✓ Ep shape ({target_nc},{target_np}) — transposed to ({target_np},{target_nc})")
            elif ep_arr.size == target_np * target_nc:
                # Case (a): flat vector — MATLAB column-major (block per covariate)
                ep_matrix = ep_arr.flatten().reshape(target_nc, target_np).T
                nc_ep = target_nc
                if logger:
                    logger.info(f"  ✓ Ep flat ({ep_arr.size},) — reshaped to ({target_np},{target_nc})")
            else:
                # Unexpected size — best effort using np_true
                ep_flat = ep_arr.flatten()
                nc_ep = ep_flat.size // target_np if ep_flat.size % target_np == 0 else 1
                ep_matrix = ep_flat.reshape(nc_ep, target_np).T
                if logger:
                    logger.warning(f"  Ep unexpected shape {ep_arr.shape}; reshaped to ({target_np},{nc_ep})")
        elif np_true > 0:
            ep_flat = ep_arr.flatten()
            nc_ep = ep_flat.size // np_true if ep_flat.size % np_true == 0 else 1
            ep_matrix = ep_flat.reshape(nc_ep, np_true).T
        else:
            ep_flat = ep_arr.flatten()
            nc_ep = 1
            np_true = int(ep_flat.size)
            ep_matrix = ep_flat.reshape(nc_ep, np_true).T

        results['ep'] = ep_matrix
        results['np'] = np_true
        # Prefer nc from Xnames; fall back to nc derived from Ep shape
        nc_true = nc_from_xnames if nc_from_xnames == nc_ep else nc_ep
        results['nc'] = nc_true
        # Ensure cov_names has nc entries
        if 'cov_names' not in results or len(results['cov_names']) != nc_true:
            results['cov_names'] = [f"effect_{i+1}" for i in range(nc_true)]
        if logger:
            logger.info(f"  ✓ Ep final shape: ({np_true}, {nc_true})")
    else:
        results['nc'] = nc_from_xnames or 1
        if logger:
            logger.warning("  ✗ Ep not found in PEB")

    # -----------------------------------------------------------------------
    # Step 3 — Extract Cp (covariance, (np*nc, np*nc) matrix)
    # -----------------------------------------------------------------------
    cp = get_field(peb, 'Cp', xpeb_group=peb)
    if cp is not None:
        results['cp'] = np.asarray(cp)
        if logger:
            logger.info(f"  ✓ Cp found, shape: {results['cp'].shape}")
    else:
        if logger:
            logger.warning("  ✗ Cp not found in PEB")

    # -----------------------------------------------------------------------
    # Step 3.5 — Extract Ce (between-subject random-effects variance).
    #
    # PEB.Ce is an (np × np) symmetric matrix describing how much individual
    # subjects vary around the group mean for each DCM parameter.
    # Distinct from Cp (estimation uncertainty of the group mean itself).
    # Ce is symmetric so h5py transposition does not change values.
    # -----------------------------------------------------------------------
    ce = get_field(peb, 'Ce', xpeb_group=peb)
    if ce is not None:
        results['ce'] = np.asarray(ce)
        if logger:
            logger.info(f"  ✓ Ce found, shape: {results['ce'].shape}")
    else:
        if logger:
            logger.warning("  ✗ Ce not found in PEB")

    # -----------------------------------------------------------------------
    # Step 3.6 — Extract M.Q (covariance component basis matrices).
    #
    # PEB.M.Q is a cell array {Q_1, ..., Q_k} of (np × np) symmetric matrices
    # that define the structure of between-subject variability.  The full
    # between-subject covariance is reconstructed as:
    #
    #   Ce = Σ_i exp(Eh_i) * Q_i
    #
    # These are sometimes called "precision components" because they appear as
    # the basis of prior precision in the ReML estimation inside spm_PEB.m.
    #
    # In default SPM PEB, M.Q usually contains 1 component: an identity matrix
    # (uniform prior variance across all parameters) or a diagonal matrix that
    # allows per-parameter scaling.
    #
    # Since peb is a dict built by _extract_group, M is a nested dict and Q is
    # a numpy object array of h5py references (file already closed) — we
    # re-open the file via _resolve_mat_cell_array to recover the matrices.
    # -----------------------------------------------------------------------
    m_sub = peb.get('M') if isinstance(peb, dict) else None
    if m_sub is None:
        m_sub = get_field(peb, 'M', xpeb_group=peb)
    q_raw = None
    if isinstance(m_sub, dict):
        q_raw = m_sub.get('Q')
    elif m_sub is not None:
        q_raw = get_field(m_sub, 'Q', xpeb_group=peb)
    if q_raw is not None:
        q_matrices = _resolve_mat_cell_array(q_raw, xpeb_mat_path)
        if q_matrices:
            results['mq'] = q_matrices
            if logger:
                logger.info(f"  ✓ M.Q found: {len(q_matrices)} component(s), "
                            f"each shape {q_matrices[0].shape}")
        else:
            if logger:
                logger.warning("  ✗ M.Q empty after extraction")
    else:
        if logger:
            logger.warning("  ✗ M.Q not found in PEB.M")

    # -----------------------------------------------------------------------
    # Step 4 — Get Pp as (np, nc) matrix.
    #
    # Priority:
    #   A) xPEB.Pp from .mat file (new MATLAB: length np*nc flat vector)
    #   B) xPEB.Pp legacy (old MATLAB: length np, effect-1 only) → tiled
    #   C) Compute from Ep and Cp using the same formula as spm_dcm_peb_review:
    #      Pp = 1 - spm_Ncdf(0, |Ep|, diag(Cp))  =  Φ(|Ep| / √diag(Cp))
    # -----------------------------------------------------------------------
    np_ = results.get('np', 0)
    nc_ = results.get('nc', 1)

    pp_raw = get_field(xpeb, 'Pp', xpeb_group=xpeb)
    if pp_raw is not None:
        pp_arr = np.asarray(pp_raw)
        if np_ > 0 and nc_ > 0:
            if pp_arr.ndim == 2 and pp_arr.shape == (np_, nc_):
                results['pp'] = pp_arr            # (np, nc) directly
                if logger:
                    logger.info(f"  ✓ Pp shape ({np_}×{nc_}) — used as-is")
            elif pp_arr.ndim == 2 and pp_arr.shape == (nc_, np_):
                results['pp'] = pp_arr.T          # standard h5py transpose
                if logger:
                    logger.info(f"  ✓ Pp shape ({nc_}×{np_}) — transposed to ({np_}×{nc_})")
            elif pp_arr.size == np_ * nc_:
                # Flat vector — assume same MATLAB column-major layout as Ep
                results['pp'] = pp_arr.flatten().reshape(nc_, np_).T
                if logger:
                    logger.info(f"  ✓ Pp flat ({pp_arr.size},) → ({np_}×{nc_})")
            elif pp_arr.size == np_:
                # Legacy: effect-1 only → tile across covariates
                results['pp'] = np.tile(pp_arr.flatten().reshape(-1, 1), (1, nc_))
                if logger:
                    logger.info(f"  ✓ Pp (legacy effect-1 only) tiled to ({np_}×{nc_})")
            else:
                if logger:
                    logger.warning(f"  Pp size {pp_arr.size} unexpected (np={np_}, nc={nc_}); will recompute")
        else:
            if logger:
                logger.warning(f"  Pp found but np/nc unknown; will recompute")
    else:
        if logger:
            logger.warning("  ✗ Pp not found in xPEB — will compute from Ep and Cp")

    # Fallback: compute Pp in Python from Ep and Cp
    if 'pp' not in results and 'ep' in results and 'cp' in results:
        try:
            from scipy.stats import norm as _norm
            ep_mtx = results['ep']           # (np, nc)
            cp_full = np.asarray(results['cp'])  # (np*nc, np*nc)
            if np_ > 0 and nc_ > 0 and cp_full.ndim == 2 and cp_full.shape[0] == np_ * nc_:
                cp_diag = np.diag(cp_full)
                pp_mtx = np.zeros((np_, nc_))
                for k in range(nc_):
                    ep_k  = ep_mtx[:, k]
                    cp_k  = np.maximum(cp_diag[k * np_:(k + 1) * np_], 1e-16)
                    pp_mtx[:, k] = _norm.cdf(np.abs(ep_k) / np.sqrt(cp_k))
                results['pp'] = pp_mtx
                if logger:
                    logger.info(f"  ✓ Pp computed from Ep/Cp: ({np_}×{nc_})")
        except Exception as _e:
            if logger:
                logger.warning(f"  Could not compute Pp from Ep/Cp: {_e}")

    # -----------------------------------------------------------------------
    # Step 5 — Group effects (Eh = log-precision weights, 1-D)
    # -----------------------------------------------------------------------
    eg = get_field(peb, 'Eg', xpeb_group=peb)
    if eg is None:
        eg = get_field(peb, 'Eh', xpeb_group=peb)
    if eg is not None:
        results['eg'] = np.asarray(eg).flatten()
        if logger:
            logger.info(f"  ✓ Group effects found, shape: {results['eg'].shape}")
    else:
        if logger:
            logger.warning("  ✗ Group effects (Eg/Eh) not found in PEB")

    # -----------------------------------------------------------------------
    # Step 6 — ROI names from xPEB.region_names
    # -----------------------------------------------------------------------
    roi_names_raw = get_field(xpeb, 'region_names', xpeb_group=xpeb)
    results['roi_names'] = _resolve_str_array(roi_names_raw, xpeb_mat_path)
    if results['roi_names']:
        if logger:
            logger.info(f"  ✓ ROIs found: {results['roi_names']}")
    else:
        if logger:
            logger.warning("  ✗ region_names not found in xPEB")

    results['num_covariates'] = results.get('nc', 1)

    # Summary
    ep_shape = results['ep'].shape if 'ep' in results else 'missing'
    pp_shape = results['pp'].shape if 'pp' in results else 'missing'
    if logger:
        logger.info(f"Extraction complete: Ep={ep_shape}, Cp={results.get('cp', np.array([])).shape}, "
                    f"Ce={results.get('ce', np.array([])).shape}, "
                    f"M.Q components={len(results.get('mq', []))}, "
                    f"Pp={pp_shape}, eg={len(results.get('eg', []))}, "
                    f"rois={results['roi_names']}, pnames({len(results.get('pnames',[]))}), "
                    f"cov_names={results.get('cov_names', [])}")
    
    # Save results to TSV files
    _save_results_to_tsv(results, output_dir, xpeb_mat_path.stem, logger)
    
    if logger:
        logger.info(f"✓ PEB results exported to TSV files in: {output_dir}")
    
    return results


def _save_results_to_tsv(results, output_dir, file_prefix, logger=None):
    """Save extracted results to TSV files.

    Ep and Pp are stored as (np, nc) matrices — rows are DCM parameters,
    columns are design-matrix covariates.  That gives one file with all
    effects, matching the display logic of spm_dcm_peb_review.m.
    """
    pnames    = results.get('pnames', [])    # length np
    cov_names = results.get('cov_names', []) # length nc
    roi_names = results.get('roi_names', [])
    np_       = results.get('np', 0)
    nc_       = results.get('nc', 1)

    # Row labels (one per DCM parameter).
    # Priority:
    #  1. Pnames (A(i,j) strings from PEB.Pnames) + roi_names → human labels
    #  2. roi_names alone → generate A-matrix labels in MATLAB column-major
    #     order (source cycles slowly, target cycles fast) — only when
    #     np_ == len(roi_names)^2 (i.e. pure A-matrix DCM)
    #  3. Pnames as-is (A(i,j) strings, no ROI lookup)
    #  4. Generic param_0, param_1, …
    #
    # ROI names are taken in the original DCM-definition order (never sorted).
    if pnames and roi_names and len(pnames) == np_:
        row_labels = _convert_parameter_names(pnames, roi_names)
    elif roi_names and np_ > 0:
        generated = _generate_parameter_labels(np_, roi_names)
        if generated is not None:
            row_labels = generated
        elif pnames and len(pnames) == np_:
            row_labels = pnames
        else:
            row_labels = [f"param_{k}" for k in range(np_)]
    elif pnames and len(pnames) == np_:
        row_labels = pnames
    else:
        row_labels = [f"param_{k}" for k in range(np_)] if np_ > 0 else []

    # Column labels (covariate names)
    col_labels = cov_names if len(cov_names) == nc_ else [f"effect_{i+1}" for i in range(nc_)]

    def _to_matrix_df(data, row_lbl, col_lbl):
        """Convert (np, nc) ndarray or 1-D fallback to a labelled DataFrame."""
        arr = np.asarray(data)
        n_rows, n_cols = len(row_lbl), len(col_lbl)
        if arr.ndim == 2 and arr.shape == (n_rows, n_cols):
            df = pd.DataFrame(arr, index=row_lbl, columns=col_lbl)
            df.index.name = 'parameter'
            return df
        # Auto-reshape 1-D array when size matches expected (np × nc)
        if arr.ndim == 1 and n_rows > 0 and n_cols > 0 and arr.size == n_rows * n_cols:
            # MATLAB column-major flat → each block of np_ values is one covariate
            arr2d = arr.reshape(n_cols, n_rows).T  # (np, nc)
            df = pd.DataFrame(arr2d, index=row_lbl, columns=col_lbl)
            df.index.name = 'parameter'
            return df
        # Fallback: something unexpected — dump as-is
        flat = arr.flatten()
        return pd.DataFrame({'param_index': range(len(flat)),
                             'value': flat})

    # --- parameter_estimates.tsv  (np × nc matrix) -----------------------
    if 'ep' in results:
        ep_file = output_dir / f"{file_prefix}_parameter_estimates.tsv"
        df_ep = _to_matrix_df(results['ep'], row_labels, col_labels)
        df_ep.to_csv(ep_file, sep='\t')
        if logger:
            logger.info(f"  Saved: {ep_file}  shape={df_ep.shape}")

    # --- posterior_probabilities.tsv  (np × nc matrix) -------------------
    if 'pp' in results:
        pp_file = output_dir / f"{file_prefix}_posterior_probabilities.tsv"
        df_pp = _to_matrix_df(results['pp'], row_labels, col_labels)
        df_pp.to_csv(pp_file, sep='\t')
        if logger:
            logger.info(f"  Saved: {pp_file}  shape={df_pp.shape}")

    # --- covariance_matrix.tsv  ((np*nc) × (np*nc) square matrix) --------
    if 'cp' in results:
        cp_file = output_dir / f"{file_prefix}_covariance_matrix.tsv"
        cp = np.asarray(results['cp'])
        n_cp = cp.shape[0]
        # Build flat labels: cov0_param0, cov0_param1, ..., cov1_param0, ...
        if row_labels and nc_ > 0 and len(row_labels) * nc_ == n_cp:
            cp_labels = [f"{cov}_{p}" for cov in col_labels for p in row_labels]
        else:
            cp_labels = [f"p{i}" for i in range(n_cp)]
        df_cp = pd.DataFrame(cp, index=cp_labels, columns=cp_labels)
        df_cp.index.name = 'parameter'
        df_cp.to_csv(cp_file, sep='\t')
        if logger:
            logger.info(f"  Saved: {cp_file}")

    # --- precision_component_NNN.tsv  (one file per M.Q component) ---------
    # M.Q is a cell array of (np × np) symmetric matrices — the covariance
    # component bases that, weighted by exp(Eh), reconstruct Ce.
    # Each component is saved as a separate file (zero-padded index).
    if 'mq' in results:
        for k, q_k in enumerate(results['mq']):
            qk_file = output_dir / f"{file_prefix}_precision_component_{k+1:03d}.tsv"
            q_arr = np.asarray(q_k)
            # h5py may return (nc_q, nr_q) due to transposition; Ce is symmetric
            # so .T does not change values, but we ensure square shape matches
            if q_arr.ndim == 2 and row_labels and q_arr.shape[0] == len(row_labels):
                df_q = pd.DataFrame(q_arr, index=row_labels, columns=row_labels)
            elif q_arr.ndim == 2 and row_labels and q_arr.shape[1] == len(row_labels):
                df_q = pd.DataFrame(q_arr.T, index=row_labels, columns=row_labels)
            else:
                n_q = q_arr.shape[0] if q_arr.ndim >= 1 else 0
                lbl = [f"p{i}" for i in range(n_q)]
                df_q = pd.DataFrame(q_arr.reshape(n_q, -1), index=lbl)
            df_q.index.name = 'parameter'
            df_q.to_csv(qk_file, sep='\t')
            if logger:
                logger.info(f"  Saved: {qk_file}  shape={df_q.shape}")

    # --- random_effects_variance.tsv  (np × np symmetric matrix) ----------
    if 'ce' in results:
        ce_file = output_dir / f"{file_prefix}_random_effects_variance.tsv"
        ce = np.asarray(results['ce'])
        # Ce is (np, np) — same parameter ordering as row_labels
        if row_labels and ce.ndim == 2 and ce.shape == (len(row_labels), len(row_labels)):
            df_ce = pd.DataFrame(ce, index=row_labels, columns=row_labels)
        elif row_labels and ce.ndim == 2 and ce.shape[0] == len(row_labels):
            df_ce = pd.DataFrame(ce, index=row_labels,
                                 columns=[f"param_{k}" for k in range(ce.shape[1])])
        else:
            n_ce = ce.shape[0] if ce.ndim >= 1 else 0
            lbl = [f"p{k}" for k in range(n_ce)]
            df_ce = pd.DataFrame(ce.reshape(n_ce, -1), index=lbl)
        df_ce.index.name = 'parameter'
        df_ce.to_csv(ce_file, sep='\t')
        if logger:
            logger.info(f"  Saved: {ce_file}  shape={df_ce.shape}")

    # --- group_effects.tsv  (1-D vector, one row per precision component) -
    if 'eg' in results:
        eg_file = output_dir / f"{file_prefix}_group_effects.tsv"
        eg = np.asarray(results['eg']).flatten()
        df_eg = pd.DataFrame({'component': range(len(eg)), 'group_effect': eg})
        df_eg.to_csv(eg_file, sep='\t', index=False)
        if logger:
            logger.info(f"  Saved: {eg_file}")

    # --- metadata.json ----------------------------------------------------
    metadata_file = output_dir / f"{file_prefix}_metadata.json"
    metadata = {
        'num_parameters': np_,
        'num_covariates': nc_,
        'num_rois': len(roi_names),
        'roi_list': roi_names,
        'covariate_names': col_labels,
        'parameter_names': row_labels,
        'outputs': {
            'parameter_estimates':       'PEB.Ep  — posterior mean of group-level parameters (np × nc)',
            'posterior_probabilities':   'PEB.Pp  — P(param ≠ 0) = Φ(|Ep|/√diag(Cp))  (np × nc)',
            'covariance_matrix':         'PEB.Cp  — posterior covariance of group-level estimates ((np×nc) × (np×nc))',
            'random_effects_variance':   'PEB.Ce  — between-subject random-effects variance (np × np)',
            'precision_component_NNN':   'PEB.M.Q{k}  — k-th covariance component basis (np × np); Ce = Σ exp(Eh_k)·Q_k',
            'group_effects':             'PEB.Eh/Eg  — log-precision hyperparameter weights (1-D)',
        },
    }
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    if logger:
        logger.info(f"  Saved: {metadata_file}")


if __name__ == '__main__':
    # Example usage
    if len(sys.argv) > 1:
        xpeb_file = sys.argv[1]
        output = sys.argv[2] if len(sys.argv) > 2 else None
        results = extract_and_export_peb_results(xpeb_file, output)
        print(f"Extracted results keys: {results.keys()}")
    else:
        print("Usage: python extract_peb_results.py xPEB_file.mat [output_dir]")
