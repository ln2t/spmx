"""HTML report generation and BIDS output structuring for group-level DCM.

Generates:
  1. BIDS-compliant copies of xPEB TSV outputs in OUTPUT_DIR/group/
  2. Sidecar JSON files for each TSV
  3. Design matrix figures in OUTPUT_DIR/group/figures/
  4. Connectome figures in OUTPUT_DIR/group/figures/
  5. HTML report in OUTPUT_DIR/group/
"""

import base64
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Styling (CSS + colour scheme)
# ---------------------------------------------------------------------------

_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        line-height: 1.6;
        color: #333333;
        background-color: #ffffff;
    }
    .report-container { max-width: 1200px; margin: 0 auto; padding: 20px; }
    header {
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white;
        padding: 40px 20px;
        border-radius: 8px;
        margin-bottom: 30px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    header h1 { font-size: 2.2em; margin-bottom: 6px; }
    header .subtitle { font-size: 1em; opacity: 0.92; }
    .meta-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 10px;
        margin-top: 18px;
        font-size: 0.88em;
    }
    .meta-item { background: rgba(0,0,0,0.12); padding: 9px 12px; border-radius: 4px; }
    .meta-label { font-weight: 700; opacity: 0.9; }
    nav {
        background: #f8f9fa;
        margin-bottom: 30px;
        border-radius: 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        position: sticky; top: 0; z-index: 100;
    }
    nav ul { list-style: none; display: flex; flex-wrap: wrap; }
    nav li { flex: 1; min-width: 140px; }
    nav a {
        display: block; padding: 13px 18px;
        color: #333; text-decoration: none;
        border-bottom: 3px solid transparent;
        transition: all 0.25s ease; font-size: 0.9em;
    }
    nav a:hover { border-bottom-color: #667eea; background: rgba(0,0,0,0.04); }
    .section {
        margin-bottom: 36px; padding: 24px;
        background: #f9f9f9; border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .section h2 {
        color: #2d3748; font-size: 1.6em;
        margin-bottom: 18px;
        border-bottom: 2px solid #667eea;
        padding-bottom: 8px;
    }
    .section h3 { color: #2d3748; font-size: 1.15em; margin: 18px 0 8px; }
    .section p { margin-bottom: 10px; }
    pre, code {
        font-family: 'Consolas', 'Monaco', monospace;
        background: #eef0f4; padding: 3px 6px;
        border-radius: 3px; font-size: 0.88em;
    }
    pre { display: block; padding: 14px 18px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.88em; }
    thead { background: #667eea; color: white; }
    th { padding: 10px 12px; text-align: left; font-weight: 600; }
    td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }
    tbody tr:hover { background: #f7fafc; }
    .visualization {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 6px; padding: 18px;
        margin: 16px 0; text-align: center;
    }
    .visualization img { max-width: 100%; height: auto; border-radius: 4px; }
    .dl-btn {
        display: inline-block; margin-top: 8px;
        padding: 5px 14px; font-size: 0.82em; font-weight: 600;
        color: #fff; background: #4a5568; border-radius: 5px;
        text-decoration: none; border: none; cursor: pointer;
        transition: background 0.15s;
    }
    .dl-btn:hover { background: #2d3748; }
    .visualization figcaption { color: #718096; font-size: 0.85em; margin-top: 8px; }
    .info-box {
        background: #ebf8ff; border-left: 4px solid #3182ce;
        padding: 14px 18px; border-radius: 0 6px 6px 0; margin: 12px 0;
    }
    /* ---- parameter matrix heatmap ---- */
    .ep-wrap { overflow-x: auto; margin: 16px 0; }
    .ep-matrix { border-collapse: collapse; font-size: 0.82em; min-width: 100%; }
    .ep-matrix th {
        background: #4a5568; color: #fff;
        padding: 8px 10px; text-align: center;
        font-weight: 600; white-space: nowrap;
    }
    .ep-matrix td {
        padding: 7px 10px; text-align: center;
        border: 1px solid #cbd5e0; white-space: nowrap; font-variant-numeric: tabular-nums;
    }
    .ep-matrix tr th:first-child { text-align: left; }
    .ep-matrix tr td:first-child {
        background: #4a5568 !important; color: #fff;
        font-weight: 600; text-align: left; border: none;
    }
    .ep-legend {
        display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px;
        font-size: 0.80em; color: #555; margin: 6px 0 14px;
    }
    .ep-legend-swatches {
        display: flex; align-items: center; gap: 0;
    }
    .ep-swatch {
        display: inline-block; width: 20px; height: 14px;
        border-top: 1px solid #aaa; border-bottom: 1px solid #aaa;
        vertical-align: middle;
    }
    .ep-swatch:first-child  { border-left:  1px solid #aaa; border-radius: 3px 0 0 3px; }
    .ep-swatch:last-child   { border-right: 1px solid #aaa; border-radius: 0 3px 3px 0; }
    .ep-swatch-sep {
        display: inline-block; width: 16px; height: 14px; line-height: 14px;
        text-align: center; font-size: 0.9em; color: #888;
        border-top: 1px solid #aaa; border-bottom: 1px solid #aaa;
        vertical-align: middle;
    }
    /* ---- end heatmap ---- */
    /* ---- connectome tab selector ---- */
    .ct-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
    .ct-tab {
        padding: 6px 16px; font-size: 0.84em; font-weight: 600;
        border: 2px solid #667eea; border-radius: 20px;
        background: #fff; color: #667eea; cursor: pointer;
        transition: background 0.15s, color 0.15s;
    }
    .ct-tab.active, .ct-tab:hover { background: #667eea; color: #fff; }
    .ct-panel { display: none; }
    .ct-panel.active { display: block; }
    /* ---- end connectome ---- */
    footer {
        background: #2d3748; color: #e2e8f0;
        padding: 28px 20px; text-align: center;
        border-top: 1px solid #e2e8f0; margin-top: 40px; border-radius: 0 0 8px 8px;
    }
    footer p { margin: 4px 0; font-size: 0.88em; }
    footer a { color: #667eea; text-decoration: none; margin: 0 8px; }
    footer a:hover { text-decoration: underline; }
    @media (max-width: 768px) {
        header h1 { font-size: 1.6em; }
        nav ul { flex-direction: column; }
        .meta-grid { grid-template-columns: 1fr; }
    }
"""

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
<div class="report-container">
{header}
{nav}
{content}
{footer}
</div>
<script>
document.addEventListener('DOMContentLoaded', function() {{
    // Smooth scroll from nav links
    document.querySelectorAll('nav a').forEach(function(a) {{
        a.addEventListener('click', function(e) {{
            var target = document.querySelector(this.getAttribute('href'));
            if (target) {{ e.preventDefault(); target.scrollIntoView({{behavior:'smooth'}}); }}
        }});
    }});
}});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# BIDS label sanitisation
# ---------------------------------------------------------------------------

def _bids_label(name: str) -> str:
    """Strip non-alphanumeric characters to produce a BIDS-compliant label.

    ``resting-state-full`` → ``restingstatefull``
    """
    import re as _re
    return _re.sub(r'[^A-Za-z0-9]', '', name)


# ---------------------------------------------------------------------------
# BIDS filename helpers
# ---------------------------------------------------------------------------

def _bids_entities_from_prefix(xpeb_prefix: str, args, config: dict) -> dict:
    """Derive BIDS key-value entities from an xPEB file prefix and CLI args.

    The xPEB file prefix looks like ``xPEB_<model>[_<contrast>]``.
    We complement it with task/session from CLI args.

    Returns a dict like::

        {'task': 'rest', 'ses': '01', 'model': 'full', 'contrast': 'patients'}
    """
    entities: Dict[str, str] = {}

    # task
    task_list = getattr(args, 'task', None) or []
    if task_list:
        entities['task'] = task_list[0]

    # session
    ses_list = getattr(args, 'session', None) or []
    if ses_list:
        entities['ses'] = ses_list[0]

    # Parse model and contrast from prefix:  xPEB_<model>[_<contrast>]
    # prefix already has 'xPEB_' stripped by callers, but handle both just in case
    stem = xpeb_prefix
    if stem.startswith('xPEB_'):
        stem = stem[len('xPEB_'):]

    # model names from CLI
    model_names = getattr(args, 'model', None) or []
    matched_model = None
    for m in sorted(model_names, key=len, reverse=True):  # longest first
        m_bids = _bids_label(m)
        if stem.startswith(m_bids):
            matched_model = m_bids
            remainder = stem[len(m_bids):]
            if remainder.startswith('_'):
                remainder = remainder[1:]
            break

    if matched_model is None:
        # fallback: split on first '_'
        parts = stem.split('_', 1)
        matched_model = parts[0]
        remainder = parts[1] if len(parts) > 1 else ''

    entities['model'] = matched_model
    if remainder:
        entities['contrast'] = remainder

    return entities


def _build_bids_filename(entities: dict, suffix: str, extension: str) -> str:
    """Build BIDS filename from entities dict.

    Standard BIDS entity order: sub, ses, task, model, contrast.
    """
    order = ['sub', 'ses', 'task', 'model', 'contrast']
    parts = []
    for key in order:
        if key in entities:
            parts.append(f"{key}-{entities[key]}")
    # any remaining entities not in order
    for key, val in entities.items():
        if key not in order:
            parts.append(f"{key}-{val}")
    return '_'.join(parts) + f"_{suffix}{extension}"


# ---------------------------------------------------------------------------
# Suffix mapping: internal key → (suffix_label, description)
# ---------------------------------------------------------------------------

_SUFFIX_MAP = {
    'parameter_estimates':     ('paramEstimates',    'PEB posterior parameter estimates (Ep)'),
    'posterior_probabilities': ('posteriorProb',     'PEB posterior probabilities P(param≠0)'),
    'design_matrix':           ('designMatrix',      'PEB group-level design matrix (X)'),
}


# ---------------------------------------------------------------------------
# Parameter matrix heatmap rendering
# ---------------------------------------------------------------------------

# Discrete colour palettes: 5 levels of intensity (index 0 = lowest Pp)
# Warm (positive values)  — white-orange → dark red
_WARM = ['#fff5eb', '#fdd0a2', '#fd8d3c', '#d94801', '#7f2704']
# Cold (negative values)  — very pale blue → dark blue
_COLD = ['#f7fbff', '#c6dbef', '#6baed6', '#2171b5', '#084594']
# Neutral (value≈0 or Pp unavailable)
_NEUTRAL = '#f0f0f0'

# Human-readable labels for the five Pp levels
_PP_LABELS = ['Pp < 0.5', '0.5 ≤ Pp < 0.75', '0.75 ≤ Pp < 0.95', '0.95 ≤ Pp < 0.99', 'Pp ≥ 0.99']


def _pp_level(pp_val: float) -> int:
    """Return 0-4 intensity index for a posterior probability value."""
    if pp_val < 0.50:
        return 0
    if pp_val < 0.75:
        return 1
    if pp_val < 0.95:
        return 2
    if pp_val < 0.99:
        return 3
    return 4


def _pp_color(val: float, pp_val: Optional[float]) -> str:
    """Return a CSS hex colour encoding sign (warm/cold) × Pp intensity.

    Positive values use warm (red/orange) tones; negative use cold (blue)
    tones.  The intensity of the hue reflects the posterior probability:
    faint for low Pp, saturated for high Pp.
    When *pp_val* is ``None`` (Pp data unavailable) a neutral grey is used.
    """
    if pp_val is None:
        return _NEUTRAL
    idx = _pp_level(pp_val)
    if val > 0:
        return _WARM[idx]
    if val < 0:
        return _COLD[idx]
    return _NEUTRAL


def _text_color_for_bg(hex_color: str) -> str:
    """Return black or white text depending on background luminance."""
    c = hex_color.lstrip('#')
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return '#111' if lum > 140 else '#eee'


def _pp_legend_html(has_pp: bool) -> str:
    """Return a small discrete colour-key for the Pp × sign scheme."""
    # Five cold swatches (dark→light = high→low Pp) + separator + five warm swatches
    cold_swatches = ''.join(
        f'<span class="ep-swatch" style="background:{_COLD[idx]}" '
        f'title="Negative, {_PP_LABELS[idx]}"></span>'
        for idx in reversed(range(5))
    )
    warm_swatches = ''.join(
        f'<span class="ep-swatch" style="background:{_WARM[idx]}" '
        f'title="Positive, {_PP_LABELS[idx]}"></span>'
        for idx in range(5)
    )
    sep = '<span class="ep-swatch-sep">·</span>'
    scale = (
        '<div class="ep-legend-swatches">'
        + cold_swatches + sep + warm_swatches
        + '</div>'
        + '<small>←&nbsp;stronger&nbsp;&nbsp;Pp&nbsp;&nbsp;stronger&nbsp;→</small>'
    )
    axis_note = '<span>Rows = FROM&nbsp;(source),&nbsp;Columns = TO&nbsp;(target)</span>'
    color_note = '<span>Blue = negative, Red/orange = positive</span>'
    pp_note    = ('<span><em>Pp = P(param≠0)</em> shown below each estimate</span>'
                  if has_pp else '')
    return f'<div class="ep-legend">{axis_note}{color_note}{scale}{pp_note}</div>'


def _render_connectivity_matrix(
    roi_names: List[str],
    data: 'pd.DataFrame',       # square (n_rois × n_rois), index=source, columns=target
    covariate: str,
    pp: Optional['pd.DataFrame'] = None,  # same shape as data, posterior probs
) -> str:
    """Return HTML for one connectivity matrix heatmap.

    Rows = FROM (source region), Columns = TO (target region).
    Cell colour encodes sign (warm = positive, cold = negative) and
    posterior probability level (intensity: faint → saturated as Pp rises).
    The Ep value and Pp are printed inside each cell.
    """
    arr = data.values.astype(float)
    has_pp = pp is not None
    pp_arr = pp.values.astype(float) if has_pp else None

    # Column headers (TO)
    col_ths = ''.join(f'<th title="TO: {r}">{r}</th>' for r in roi_names)
    header = f'<tr><th>FROM \\ TO \u2192</th>{col_ths}</tr>'

    rows = ''
    for i, source in enumerate(roi_names):
        cells = ''
        for j, target in enumerate(roi_names):
            val   = float(arr[i, j])
            pp_val = float(pp_arr[i, j]) if has_pp and pp_arr is not None else None
            bg    = _pp_color(val, pp_val)
            fg    = _text_color_for_bg(bg)
            tip   = f'FROM {source} TO {target}: Ep={val:.4f}'
            if pp_val is not None:
                tip += f', Pp={pp_val:.3f} ({_PP_LABELS[_pp_level(pp_val)]})'
                cell_inner = (
                    f'<span style="font-size:1em">{val:+.3f}</span>'
                    f'<br><span style="font-size:0.78em;opacity:0.85">Pp={pp_val:.2f}</span>'
                )
            else:
                cell_inner = f'{val:+.3f}'
            cells += (
                f'<td style="background:{bg};color:{fg}" title="{tip}">'
                f'{cell_inner}</td>'
            )
        rows += f'<tr><td><strong>{source}</strong></td>{cells}</tr>\n'

    return (
        f'<p><strong>Covariate: {covariate}</strong></p>'
        + _pp_legend_html(has_pp)
        + f'<div class="ep-wrap"><table class="ep-matrix">'
        + f'<thead>{header}</thead><tbody>{rows}</tbody>'
        + '</table></div>'
    )


def _build_ep_section(
    spm_dir: Path,
    args,
    config: dict,
    logger=None,
) -> str:
    """Build HTML body for the Estimated Parameters section.

    For each model/contrast found in *spm_dir*, loads the
    ``xPEB_*_parameter_estimates.tsv`` file and renders the connectivity
    matrices for every covariate.

    Parameters with labels in ``source→target`` format are laid out as
    square (n_roi × n_roi) matrices.  Any remaining parameters (B-matrix,
    C-vector, etc.) are appended as a flat table.
    """
    import numpy as _np

    ep_files = sorted(spm_dir.glob('xPEB*_parameter_estimates.tsv'))
    if not ep_files:
        return '<p>No parameter estimate files found in SPM output directory.</p>'

    html_parts: List[str] = []

    for ep_path in ep_files:
        prefix = ep_path.name.replace('_parameter_estimates.tsv', '')
        # e.g. xPEB_restingstatefull or xPEB_restingstatefull_MvsF
        label = prefix.replace('xPEB_', '')

        # Load metadata for ROI names
        meta_path = spm_dir / f'{prefix}_metadata.json'
        roi_names: List[str] = []
        cov_names: List[str] = []
        if meta_path.exists():
            try:
                with open(meta_path) as fh:
                    meta = json.load(fh)
                roi_names = meta.get('roi_list', [])
                cov_names = meta.get('covariate_names', [])
            except Exception as exc:
                if logger:
                    logger.debug('Could not load %s: %s', meta_path, exc)

        # Load Ep TSV
        try:
            df_ep = pd.read_csv(ep_path, sep='\t', index_col=0)
        except Exception as exc:
            if logger:
                logger.warning('Could not load %s: %s', ep_path, exc)
            continue

        # Load Pp TSV (optional)
        pp_path = spm_dir / f'{prefix}_posterior_probabilities.tsv'
        df_pp: Optional[pd.DataFrame] = None
        if pp_path.exists():
            try:
                df_pp = pd.read_csv(pp_path, sep='\t', index_col=0)
            except Exception:
                pass

        html_parts.append(f'<h3>Model / contrast: <code>{label}</code></h3>')

        # Separate A-matrix params (label contains '→') from others
        arrow = '\u2192'  # →
        a_mask = df_ep.index.str.contains(arrow, regex=False)
        df_a   = df_ep[a_mask]
        df_pp_a = df_pp[a_mask] if df_pp is not None else None
        df_other  = df_ep[~a_mask]
        df_pp_other = df_pp[~a_mask] if df_pp is not None else None

        if df_a.empty:
            html_parts.append('<p><em>No A-matrix parameters found in this file.</em></p>')
        else:
            # Infer ROI names from labels if metadata was missing
            if not roi_names:
                sources = [lbl.split(arrow)[0].strip() for lbl in df_a.index]
                targets = [lbl.split(arrow)[1].strip() for lbl in df_a.index]
                seen: dict = {}
                for nm in sources + targets:
                    seen.setdefault(nm, None)
                roi_names = list(seen.keys())

            n = len(roi_names)

            # For each covariate column, reconstruct n×n matrix
            for cov in df_a.columns:
                # Build mapping: (source, target) → value
                ep_vals: dict = {}
                pp_vals: dict = {}
                for lbl in df_a.index:
                    parts = lbl.split(arrow)
                    if len(parts) != 2:
                        continue
                    src, tgt = parts[0].strip(), parts[1].strip()
                    ep_vals[(src, tgt)] = float(df_a.loc[lbl, cov])
                    if df_pp_a is not None and cov in df_pp_a.columns:
                        pp_vals[(src, tgt)] = float(df_pp_a.loc[lbl, cov])

                # Construct DataFrames indexed by ROI name (source=row, target=col)
                ep_matrix  = _np.zeros((n, n))
                pp_matrix  = _np.zeros((n, n)) if pp_vals else None
                for ri, src in enumerate(roi_names):
                    for ci, tgt in enumerate(roi_names):
                        ep_matrix[ri, ci] = ep_vals.get((src, tgt), _np.nan)
                        if pp_matrix is not None:
                            pp_matrix[ri, ci] = pp_vals.get((src, tgt), _np.nan)

                df_mat = pd.DataFrame(ep_matrix, index=roi_names, columns=roi_names)
                df_pp_mat = (
                    pd.DataFrame(pp_matrix, index=roi_names, columns=roi_names)
                    if pp_matrix is not None else None
                )
                html_parts.append(
                    _render_connectivity_matrix(roi_names, df_mat, cov, df_pp_mat)
                )

        # Non-A parameters (B/C/other) → flat table
        if not df_other.empty:
            html_parts.append('<h3>Other parameters (B / C / non-matrix)</h3>')
            html_parts.append(_html_table_from_df(
                df_other.reset_index().rename(columns={'parameter': 'parameter'})
            ))

    return '\n'.join(html_parts) if html_parts else '<p>No parameter estimates to display.</p>'


# ---------------------------------------------------------------------------
# Connectome figures
# ---------------------------------------------------------------------------

_CONNECTOME_PP_THRESHOLDS = [0.50, 0.75, 0.95, 0.99]


def generate_connectome_figures(
    spm_dir: Path,
    figures_dir: Path,
    args,
    logger=None,
) -> List[Dict[str, Any]]:
    """Generate connectome plots for each model/contrast/covariate/Pp-threshold.

    For every ``xPEB_*_parameter_estimates.tsv`` found in *spm_dir*:

    * Reconstructs the A-matrix for each covariate column.
    * Loads the companion posterior-probabilities TSV.
    * For each Pp threshold in ``[0.50, 0.75, 0.95, 0.99]`` generates a
      directed connectome plot (connections below the threshold are zeroed
      out before plotting so only significant edges are shown).
    * Saves each figure as an SVG in *figures_dir*.

    Returns a list of dicts with keys:
      ``prefix``, ``label``, ``covariate``, ``threshold``, ``fig_path``, ``title``
    """
    import numpy as _np

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from nilearn.plotting import plot_connectome
    except ImportError as exc:
        if logger:
            logger.warning(
                'nilearn/matplotlib not available — skipping connectome figures: %s', exc
            )
        return []

    figures_dir.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []
    arrow = '\u2192'

    ep_files = sorted(spm_dir.glob('xPEB*_parameter_estimates.tsv'))
    for ep_path in ep_files:
        prefix = ep_path.name.replace('_parameter_estimates.tsv', '')
        label  = prefix.replace('xPEB_', '')

        # --- metadata (ROI names + MNI coords)
        meta_path = spm_dir / f'{prefix}_metadata.json'
        roi_names: List[str] = []
        roi_coords: Optional[List] = None
        if meta_path.exists():
            try:
                with open(meta_path) as fh:
                    meta = json.load(fh)
                roi_names  = meta.get('roi_list', [])
                roi_coords = meta.get('roi_coords', None)  # list of [x,y,z]
            except Exception as exc:
                if logger:
                    logger.debug('Could not load %s: %s', meta_path, exc)

        # --- Ep TSV
        try:
            df_ep = pd.read_csv(ep_path, sep='\t', index_col=0)
        except Exception as exc:
            if logger:
                logger.warning('Could not load %s: %s', ep_path, exc)
            continue

        # --- Pp TSV
        pp_path = spm_dir / f'{prefix}_posterior_probabilities.tsv'
        df_pp: Optional[pd.DataFrame] = None
        if pp_path.exists():
            try:
                df_pp = pd.read_csv(pp_path, sep='\t', index_col=0)
            except Exception:
                pass

        # --- A-matrix rows only
        a_mask = df_ep.index.str.contains(arrow, regex=False)
        df_a    = df_ep[a_mask]
        df_pp_a = df_pp[a_mask] if df_pp is not None else None

        if df_a.empty:
            continue

        # Infer ROI names if not in metadata
        if not roi_names:
            seen: dict = {}
            for lbl in df_a.index:
                parts = lbl.split(arrow)
                if len(parts) == 2:
                    for nm in parts:
                        seen.setdefault(nm.strip(), None)
            roi_names = list(seen.keys())

        n = len(roi_names)
        if n == 0:
            continue

        # Build MNI coordinates array:
        # use provided coords, or fall back to a circle layout in the axial plane
        if roi_coords and len(roi_coords) == n:
            coords = _np.array(roi_coords, dtype=float)
        else:
            angles = _np.linspace(0, 2 * _np.pi, n, endpoint=False)
            coords = _np.column_stack([
                60 * _np.cos(angles),
                60 * _np.sin(angles),
                _np.zeros(n),
            ])

        for cov in df_a.columns:
            # Build n×n Ep and Pp arrays (source=row, target=col — same as heatmap)
            ep_mat = _np.zeros((n, n))
            pp_mat = _np.zeros((n, n))
            for lbl in df_a.index:
                parts = lbl.split(arrow)
                if len(parts) != 2:
                    continue
                src, tgt = parts[0].strip(), parts[1].strip()
                if src not in roi_names or tgt not in roi_names:
                    continue
                ri = roi_names.index(src)
                ci = roi_names.index(tgt)
                ep_mat[ri, ci] = float(df_a.loc[lbl, cov])
                if df_pp_a is not None and cov in df_pp_a.columns:
                    pp_mat[ri, ci] = float(df_pp_a.loc[lbl, cov])

            for thr in _CONNECTOME_PP_THRESHOLDS:
                # Zero out connections below threshold
                masked = ep_mat.copy()
                masked[pp_mat < thr] = 0.0

                fname = (
                    f'{prefix}_{_safe_id(cov)}'
                    f'_connectome_pp{int(thr * 100):02d}.svg'
                )
                fig_path  = figures_dir / fname
                fig_title = (
                    f'Connectome \u2014 {label}, covariate: {cov}, '
                    f'Pp \u2265 {thr:.2f}'
                )

                try:
                    import warnings
                    with warnings.catch_warnings():
                        # DCM A-matrices are intentionally asymmetric (directed)
                        warnings.filterwarnings(
                            'ignore',
                            message='.*adjacency_matrix.*not symmetric.*',
                            category=UserWarning,
                        )
                        display = plot_connectome(
                            adjacency_matrix=masked,
                            node_coords=coords,
                            edge_cmap='RdBu_r',
                            colorbar=True,
                            title=fig_title,
                            display_mode='ortho',
                        )

                    # Add a compact ROI legend as a matplotlib text box
                    # Get the underlying matplotlib Figure from any panel axis
                    _panels = list(display.axes.values())
                    fig = _panels[0].ax.get_figure() if _panels else None

                    legend_lines = [f'{i + 1}: {name}' for i, name in enumerate(roi_names)]
                    legend_text  = '\n'.join(legend_lines)
                    if fig is not None:
                        fig.text(
                            0.01, 0.01, legend_text,
                            fontsize=7, va='bottom', ha='left',
                            family='monospace',
                            bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.7, ec='#aaa'),
                        )
                    # Label each node with its index number using MNI data coordinates
                    for panel in display.axes.values():
                        mpl_ax = panel.ax
                        direc  = getattr(panel, 'direction', 'z')
                        for k, (name, coord) in enumerate(zip(roi_names, coords)):
                            mapping = {'x': (coord[1], coord[2]),
                                       'y': (coord[0], coord[2]),
                                       'z': (coord[0], coord[1]),
                                       'l': (coord[1], coord[2]),
                                       'r': (coord[1], coord[2])}
                            px, py = mapping.get(direc, (coord[0], coord[1]))
                            mpl_ax.text(
                                px, py, str(k + 1),
                                fontsize=6, ha='center', va='center',
                                color='white', fontweight='bold',
                                clip_on=True,
                            )

                    display.savefig(str(fig_path))
                    display.close()
                    results.append({
                        'prefix':    prefix,
                        'label':     label,
                        'covariate': cov,
                        'threshold': thr,
                        'fig_path':  fig_path,
                        'title':     fig_title,
                    })
                    if logger:
                        logger.info('Saved connectome figure: %s', fig_path.name)
                except Exception as exc:
                    if logger:
                        logger.warning(
                            'Could not generate connectome for %s/%s/%.2f: %s',
                            label, cov, thr, exc,
                        )
                    plt.close('all')

    return results


def _safe_id(s: str) -> str:
    """Make a string safe for use in filenames and HTML ids."""
    return re.sub(r'[^A-Za-z0-9_-]', '_', s)


def _build_connectome_section(
    connectome_figures: List[Dict[str, Any]],
) -> str:
    """Build the HTML body for the Connectome section.

    Figures are grouped per (label, covariate); within each group a tab bar
    lets the user switch between Pp thresholds without reloading.
    """
    if not connectome_figures:
        return (
            '<p>No connectome figures available (nilearn may not be installed, '
            'or no A-matrix parameters found).</p>'
        )

    from collections import OrderedDict
    groups: Dict[tuple, List[Dict]] = OrderedDict()
    for fig in connectome_figures:
        key = (fig['label'], fig['covariate'])
        groups.setdefault(key, []).append(fig)

    html_parts = [
        '<p>Connections are shown only for parameters with posterior probability '
        '\u2265 the selected threshold. Positive weights are shown in red, '
        'negative in blue.</p>',
    ]

    for group_idx, ((lbl, cov), figs) in enumerate(groups.items()):
        figs_sorted = sorted(figs, key=lambda f: f['threshold'])
        group_id    = f'ct_{_safe_id(lbl)}_{_safe_id(cov)}_{group_idx}'

        html_parts.append(
            f'<h3>Model/contrast: <code>{lbl}</code> \u2014 '
            f'covariate: <code>{cov}</code></h3>'
        )

        # Tab buttons
        tabs_html = '<div class="ct-tabs">'
        for i, fig in enumerate(figs_sorted):
            active    = 'active' if i == 0 else ''
            thr_label = f'Pp \u2265 {fig["threshold"]:.2f}'
            tabs_html += (
                f'<button class="ct-tab {active}" '
                f'onclick="ctSwitch(this, \'{group_id}\', {i})">'
                f'{thr_label}</button>'
            )
        tabs_html += '</div>'
        html_parts.append(tabs_html)

        # Panels
        for i, fig in enumerate(figs_sorted):
            active  = 'active' if i == 0 else ''
            img_src = _img_to_base64(fig['fig_path'])
            fname   = fig['fig_path'].name
            html_parts.append(
                f'<div id="{group_id}_panel_{i}" class="ct-panel {active}">'
                f'<div class="visualization">'
                f'<img src="{img_src}" alt="{fig["title"]}" />'
                f'<figcaption>{fig["title"]}</figcaption>'
                f'<a class="dl-btn" href="{img_src}" download="{fname}">'
                f'\u2913 Download SVG</a>'
                f'</div></div>'
            )

    # Inline JS for tab switching
    html_parts.append('''
<script>
function ctSwitch(btn, groupId, idx) {
  var wrap = btn.closest('section') || document;
  btn.parentElement.querySelectorAll('.ct-tab').forEach(function(t){
    t.classList.remove('active');
  });
  wrap.querySelectorAll('[id^="' + groupId + '_panel_"]').forEach(function(p){
    p.classList.remove('active');
  });
  btn.classList.add('active');
  var panel = wrap.querySelector('#' + groupId + '_panel_' + idx);
  if (panel) panel.classList.add('active');
}
</script>''')

    return '\n'.join(html_parts)


# ---------------------------------------------------------------------------
# BIDS TSV copy + sidecar JSON
# ---------------------------------------------------------------------------

def copy_to_bids_group(
    spm_dir: Path,
    group_dir: Path,
    args,
    config: dict,
    logger=None,
):
    """Copy relevant xPEB TSV files to BIDS-style names in *group_dir*.

    Creates ``<group_dir>/<bids_name>.tsv`` and
    ``<group_dir>/<bids_name>.json`` for each file.

    Parameters
    ----------
    spm_dir : Path
        ``OUTPUT_DIR/group/SPM/``
    group_dir : Path
        ``OUTPUT_DIR/group/``
    args : argparse.Namespace
    config : dict
    logger : logging.Logger, optional

    Returns
    -------
    list of dict
        Each entry has ``{'bids_name': str, 'suffix': str, 'src': Path, 'dst': Path}``.
    """
    group_dir.mkdir(parents=True, exist_ok=True)

    # Discover all metadata JSON files → they anchor the file sets
    metadata_files = sorted(spm_dir.glob('xPEB*metadata.json'))
    if not metadata_files:
        if logger:
            logger.warning("No xPEB*metadata.json files found in %s", spm_dir)
        return []

    created_files = []

    for meta_path in metadata_files:
        # Load metadata
        try:
            with open(meta_path) as fh:
                metadata = json.load(fh)
        except Exception as exc:
            if logger:
                logger.warning("Could not load %s: %s", meta_path, exc)
            continue

        # Derive the common file prefix (strip _metadata.json)
        prefix = meta_path.name.replace('_metadata.json', '')  # e.g. xPEB_full
        entities = _bids_entities_from_prefix(prefix, args, config)

        # TSV suffixes to copy
        for internal_key, (bids_suffix, description) in _SUFFIX_MAP.items():
            src = spm_dir / f"{prefix}_{internal_key}.tsv"
            if not src.exists():
                if logger:
                    logger.debug("Expected file not found, skipping: %s", src)
                continue

            bids_fname = _build_bids_filename(entities, bids_suffix, '.tsv')
            dst = group_dir / bids_fname
            try:
                shutil.copy2(src, dst)
                if logger:
                    logger.info("Copied %s → %s", src.name, dst.name)
            except Exception as exc:
                if logger:
                    logger.warning("Could not copy %s: %s", src, exc)
                continue

            # Build sidecar JSON
            sidecar = _build_sidecar(
                description=description,
                metadata=metadata,
                suffix_key=internal_key,
                src_path=src,
                entities=entities,
            )
            sidecar_path = group_dir / bids_fname.replace('.tsv', '.json')
            with open(sidecar_path, 'w') as fh:
                json.dump(sidecar, fh, indent=2)
            if logger:
                logger.info("Created sidecar: %s", sidecar_path.name)

            created_files.append({
                'bids_name': bids_fname,
                'suffix': internal_key,
                'src': src,
                'dst': dst,
                'entities': entities,
                'metadata': metadata,
            })

    return created_files


def _build_sidecar(
    description: str,
    metadata: dict,
    suffix_key: str,
    src_path: Path,
    entities: dict,
) -> dict:
    """Build JSON sidecar content for a BIDS TSV file."""
    sidecar: Dict[str, Any] = {
        'Description': description,
        'Sources': [str(src_path)],
        'Entities': entities,
    }

    # Column descriptions per suffix
    col_descs: Dict[str, Dict[str, str]] = {
        'parameter_estimates': {
            'parameter': 'DCM A-matrix parameter label (source→target convention)',
            '(columns)': 'One column per design-matrix covariate (Xnames). '
                         'Values are PEB.Ep posterior mean estimates.',
        },
        'posterior_probabilities': {
            'parameter': 'DCM A-matrix parameter label (source→target convention)',
            '(columns)': 'One column per design-matrix covariate (Xnames). '
                         'Values are P(param≠0) = Φ(|Ep|/√diag(Cp)).',
        },
        'design_matrix': {
            'participant_id': 'Subject identifier (BIDS format, e.g. sub-01)',
            'intercept': 'All-ones intercept column (group mean)',
            '(other columns)': 'Additional covariates as specified via --regressors.',
        },
    }

    sidecar['Columns'] = col_descs.get(suffix_key, {})

    # Embed PEB metadata
    sidecar['PEB_Metadata'] = {
        'num_parameters': metadata.get('num_parameters'),
        'num_covariates': metadata.get('num_covariates'),
        'num_rois': metadata.get('num_rois'),
        'roi_list': metadata.get('roi_list', []),
        'covariate_names': metadata.get('covariate_names', []),
        'parameter_names': metadata.get('parameter_names', []),
    }

    return sidecar


# ---------------------------------------------------------------------------
# Design matrix figure
# ---------------------------------------------------------------------------

def generate_design_matrix_figures(
    spm_dir: Path,
    figures_dir: Path,
    args,
    logger=None,
) -> List[Dict[str, Any]]:
    """Generate design matrix figures using nilearn.

    Parameters
    ----------
    spm_dir : Path
    figures_dir : Path
        ``OUTPUT_DIR/group/figures/``
    args : argparse.Namespace
    logger : logging.Logger, optional

    Returns
    -------
    list of dict
        Each entry: ``{'prefix': str, 'fig_path': Path, 'title': str}``.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from nilearn.plotting import plot_design_matrix
    except ImportError as exc:
        if logger:
            logger.warning("nilearn/matplotlib not available — skipping figures: %s", exc)
        return []

    figures_dir.mkdir(parents=True, exist_ok=True)
    figures = []

    dm_files = sorted(spm_dir.glob('xPEB*design_matrix.tsv'))
    for dm_path in dm_files:
        prefix = dm_path.name.replace('_design_matrix.tsv', '')  # xPEB_<model>[_<contrast>]

        try:
            df = pd.read_csv(dm_path, sep='\t')
        except Exception as exc:
            if logger:
                logger.warning("Could not read design matrix %s: %s", dm_path, exc)
            continue

        # Remove participant_id column — nilearn expects only numeric columns
        if 'participant_id' in df.columns:
            df = df.drop(columns=['participant_id'])

        if df.empty:
            if logger:
                logger.warning("Design matrix %s is empty after removing participant_id", dm_path.name)
            continue

        entities = _bids_entities_from_prefix(prefix, args, {})
        title_parts = []
        if 'task' in entities:
            title_parts.append(f"task-{entities['task']}")
        if 'model' in entities:
            title_parts.append(f"model-{entities['model']}")
        if 'contrast' in entities:
            title_parts.append(f"contrast-{entities['contrast']}")
        fig_title = 'PEB Design Matrix' + (' — ' + ' / '.join(title_parts) if title_parts else '')

        try:
            ax = plot_design_matrix(df)
            if ax is None:
                raise RuntimeError("plot_design_matrix returned None")
            ax.set_title(fig_title, fontsize=10, pad=10)
            fig = ax.get_figure()
            if fig is None:
                raise RuntimeError("Axes has no associated figure")
            # Ensure the figure is large enough to avoid constrained_layout collapse
            n_regressors = df.shape[1]
            fig.set_size_inches(max(8, n_regressors * 0.6 + 2), 6)

            fname = _build_bids_filename(entities, 'designMatrix', '.svg')
            fig_path = figures_dir / fname
            fig.savefig(str(fig_path), format='svg', bbox_inches='tight')
            plt.close(fig)

            figures.append({'prefix': prefix, 'fig_path': fig_path, 'title': fig_title})
            if logger:
                logger.info("Saved design matrix figure: %s", fig_path.name)
        except Exception as exc:
            if logger:
                logger.warning("Could not generate figure for %s: %s", dm_path.name, exc)
            plt.close('all')

    return figures


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _img_to_base64(path: Path) -> str:
    """Return a data-URI string for embedding an image in HTML."""
    with open(path, 'rb') as fh:
        data = base64.b64encode(fh.read()).decode()
    suffix = path.suffix.lower()
    mime = 'image/svg+xml' if suffix == '.svg' else f'image/{suffix.lstrip(".")}'  
    return f'data:{mime};base64,{data}'


def _html_table_from_df(df: pd.DataFrame, max_rows: int = 50) -> str:
    """Render a pandas DataFrame as an HTML table string."""
    rows_html = ''
    display_df = df.head(max_rows)
    for _, row in display_df.iterrows():
        cells = ''.join(f'<td>{val}</td>' for val in row)
        rows_html += f'<tr>{cells}</tr>\n'
    note = ''
    if len(df) > max_rows:
        note = f'<p><em>Showing {max_rows} of {len(df)} rows.</em></p>'
    headers = ''.join(f'<th>{c}</th>' for c in df.columns)
    return f"""
    {note}
    <table>
    <thead><tr>{headers}</tr></thead>
    <tbody>{rows_html}</tbody>
    </table>"""


def _section(section_id: str, title: str, body: str) -> str:
    return f"""
<section id="{section_id}" class="section">
<h2>{title}</h2>
{body}
</section>"""


def _reconstruct_cli_call(args) -> str:
    """Reconstruct a representative CLI call from args (generic paths)."""
    parts = ['spmx', 'fmri', '<INPUT_DIR>', '<OUTPUT_DIR>', 'group']

    if getattr(args, 'dcm', False):
        parts.append('--dcm')

    models = getattr(args, 'model', None) or []
    if models:
        parts += ['--model'] + models

    participants_file = getattr(args, 'participants_file', None)
    if participants_file:
        parts.append('--participants-file <participants.tsv>')

    regressors = getattr(args, 'regressors', None) or []
    if regressors:
        parts += ['--regressors'] + regressors

    cat_regressors = getattr(args, 'categorical_regressors', None) or []
    if cat_regressors:
        parts += ['--categorical-regressors'] + cat_regressors

    contrast = getattr(args, 'contrast', None)
    if contrast:
        c = contrast[0] if isinstance(contrast, list) else contrast
        parts += ['--contrast', f'"{c}"']

    task = getattr(args, 'task', None) or []
    if task:
        parts += ['--task'] + task

    session = getattr(args, 'session', None) or []
    if session:
        parts += ['--session'] + session

    group_name = getattr(args, 'group_name', None)
    if group_name and group_name != 'PEB_analysis':
        parts += ['--group-name', group_name]

    config_path = getattr(args, 'config', None)
    if config_path:
        parts += ['--config', '<config.yaml>']

    if getattr(args, 'debug', False):
        parts.append('--debug')

    return ' \\\n    '.join(parts)


def _describe_voi_seeds(config: dict) -> str:
    """Return an HTML snippet listing VOI and DCM seeds from config."""
    voi_seeds = config.get('fmri', {}).get('voi', {}).get('seeds', [])
    dcm_seeds = config.get('fmri', {}).get('dcm', {}).get('seeds', [])  # may be list of str
    global_radius = config.get('fmri', {}).get('voi', {}).get('radius', 'N/A')

    if not voi_seeds:
        return '<p>No VOI seeds defined in config.</p>'

    # Normalise dcm_seeds to a set of names for quick lookup
    dcm_seed_names: set = set()
    for s in dcm_seeds:
        if isinstance(s, str):
            dcm_seed_names.add(s)
        elif isinstance(s, dict):
            dcm_seed_names.add(s.get('name', ''))
    in_dcm_col = bool(dcm_seeds)  # only show the column if dcm.seeds is configured

    rows = ''
    for seed in voi_seeds:
        if isinstance(seed, str):
            name, x, y, z, radius = seed, '', '', '', global_radius
        elif isinstance(seed, dict):
            name   = seed.get('name', '')
            x      = seed.get('x', '')
            y      = seed.get('y', '')
            z      = seed.get('z', '')
            radius = seed.get('radius', global_radius)
        else:
            continue
        in_dcm = '✓' if (not in_dcm_col or name in dcm_seed_names) else ''
        dcm_cell = f'<td style="text-align:center;">{in_dcm}</td>' if in_dcm_col else ''
        rows += f'<tr><td><strong>{name}</strong></td><td>{x}</td><td>{y}</td><td>{z}</td><td>{radius}</td>{dcm_cell}</tr>\n'

    dcm_th = '<th>In DCM</th>' if in_dcm_col else ''
    return f"""
<p>Global VOI radius: <code>{global_radius} mm</code>.</p>
<table>
<thead><tr><th>Seed name</th><th>x</th><th>y</th><th>z</th><th>Radius (mm)</th>{dcm_th}</tr></thead>
<tbody>{rows}</tbody>
</table>"""


def _describe_model_a_matrix(config: dict, model_name: str) -> str:
    """Return an HTML snippet describing the A matrix for *model_name*."""
    dcm_models = config.get('fmri', {}).get('dcm', {}).get('models', [])
    model_cfg = None
    for m in dcm_models:
        if isinstance(m, dict) and m.get('name') == model_name:
            model_cfg = m
            break

    if model_cfg is None:
        return f'<p>No model definition found for <code>{model_name}</code> in config.</p>'

    a_matrix = model_cfg.get('A', None)
    seeds_cfg = config.get('fmri', {}).get('dcm', {}).get('seeds', [])
    # seeds_cfg may be list of str or list of dicts
    roi_names = []
    for s in seeds_cfg:
        if isinstance(s, str):
            roi_names.append(s)
        elif isinstance(s, dict):
            roi_names.append(s.get('name', ''))
    # Fallback: voi seeds
    if not roi_names:
        voi_seeds = config.get('fmri', {}).get('voi', {}).get('seeds', [])
        for s in voi_seeds:
            if isinstance(s, dict):
                roi_names.append(s.get('name', ''))
            elif isinstance(s, str):
                roi_names.append(s)

    lines = []
    lines.append(f'<p>Model: <code>{model_name}</code></p>')

    if a_matrix:
        n = len(a_matrix)
        col_headers = roi_names[:n] if roi_names else [f'ROI{i+1}' for i in range(n)]
        row_headers = col_headers
        th = '<th>source→target</th>' + ''.join(f'<th>{h}</th>' for h in col_headers)
        rows = ''
        for i, row in enumerate(a_matrix):
            rname = row_headers[i] if i < len(row_headers) else f'ROI{i+1}'
            cells = ''.join(f'<td style="text-align:center;">{"✓" if v else "✗"}</td>' for v in row)
            rows += f'<tr><th>{rname}</th>{cells}</tr>\n'
        lines.append(f"""
<p>A matrix (rows = targets, columns = sources; ✓ = connection included):</p>
<table>
<thead><tr>{th}</tr></thead>
<tbody>{rows}</tbody>
</table>""")

    b_matrix = model_cfg.get('B', None)
    c_matrix = model_cfg.get('C', None)
    if b_matrix or c_matrix:
        lines.append('<p><em>B/C matrices are defined in the config but not shown here.</em></p>')

    return '\n'.join(lines)


def generate_html_report(
    output_dir: Path,
    spm_dir: Path,
    args,
    config: dict,
    participants_df,
    dcm_subjects: List[str],
    bids_files: List[dict],
    figures: List[Dict[str, Any]],
    connectome_figures: Optional[List[Dict[str, Any]]] = None,
    logger=None,
) -> Path:
    """Generate the HTML group-level DCM report.

    Parameters
    ----------
    output_dir : Path
        ``OUTPUT_DIR/group/``
    spm_dir : Path
        ``OUTPUT_DIR/group/SPM/``
    args : argparse.Namespace
    config : dict
    participants_df : pd.DataFrame
        Full participants file content.
    dcm_subjects : list of str
        Subject IDs (without 'sub-') that had DCM files.
    bids_files : list of dict
        Output of :func:`copy_to_bids_group`.
    figures : list of dict
        Output of :func:`generate_design_matrix_figures`.
    logger : logging.Logger, optional

    Returns
    -------
    Path
        Path to the generated HTML file.
    """
    from spmx import __version__ as _version

    now = datetime.now()
    nav_ids    = ['overview', 'model', 'participants', 'design-matrix',
                  'parameters', 'connectome', 'outputs', 'reproducibility', 'environment']
    nav_labels = ['Overview', 'Model', 'Participants', 'Design Matrix',
                  'Parameters', 'Connectome', 'Outputs', 'Reproducibility', 'Environment']

    # ------------------------------------------------------------------ header
    task_list = getattr(args, 'task', None) or []
    ses_list  = getattr(args, 'session', None) or []
    models    = getattr(args, 'model', None) or []

    meta_items = [
        ('Date', now.strftime('%Y-%m-%d %H:%M')),
        ('spmx version', _version),
        ('Task', ', '.join(task_list) if task_list else 'N/A'),
        ('Session', ', '.join(ses_list) if ses_list else 'N/A'),
        ('Model(s)', ', '.join(models) if models else 'N/A'),
        ('N subjects (DCM)', str(len(dcm_subjects))),
    ]
    meta_html = ''.join(
        f'<div class="meta-item"><span class="meta-label">{k}:</span> {v}</div>'
        for k, v in meta_items
    )
    header_html = f"""
<header>
<h1>Group-level DCM Report</h1>
<p class="subtitle">Parametric Empirical Bayes (PEB) analysis — spmx</p>
<div class="meta-grid">{meta_html}</div>
</header>"""

    # ------------------------------------------------------------------ nav
    nav_html = '<nav><ul>' + ''.join(
        f'<li><a href="#{sid}">{lbl}</a></li>'
        for sid, lbl in zip(nav_ids, nav_labels)
    ) + '</ul></nav>'

    # ------------------------------------------------------------------ sections
    sections: List[str] = []

    # --- 1. Overview
    group_name = getattr(args, 'group_name', 'PEB_analysis')
    contrast_raw = getattr(args, 'contrast', None)
    contrast_str = (contrast_raw[0] if isinstance(contrast_raw, list) else contrast_raw) or 'N/A'
    overview_body = f"""
<p>This report summarises the group-level DCM (PEB) analysis run by
<code>spmx fmri … group --dcm</code>.</p>
<table>
<thead><tr><th>Parameter</th><th>Value</th></tr></thead>
<tbody>
<tr><td>Analysis level</td><td>group</td></tr>
<tr><td>Group name</td><td>{group_name}</td></tr>
<tr><td>Module</td><td>fmri --dcm</td></tr>
<tr><td>Task</td><td>{', '.join(task_list) if task_list else 'N/A'}</td></tr>
<tr><td>Session</td><td>{', '.join(ses_list) if ses_list else 'N/A'}</td></tr>
<tr><td>Model(s)</td><td>{', '.join(models) if models else 'N/A'}</td></tr>
<tr><td>Contrast</td><td>{contrast_str}</td></tr>
<tr><td>N subjects with DCM files</td><td>{len(dcm_subjects)}</td></tr>
<tr><td>Output directory</td><td><code>{output_dir.parent}</code></td></tr>
</tbody>
</table>"""
    sections.append(_section('overview', 'Overview', overview_body))

    # --- 2. Model description
    model_body_parts = []
    model_body_parts.append('<h3>VOI Seeds</h3>')
    model_body_parts.append(_describe_voi_seeds(config))
    for m in models:
        model_body_parts.append(f'<h3>Model: {m}</h3>')
        model_body_parts.append(_describe_model_a_matrix(config, m))
    if len(model_body_parts) == 1:  # only the VOI section was added
        model_body_parts.append('<p>No model information available.</p>')
    sections.append(_section('model', 'Model Description', '\n'.join(model_body_parts)))

    # --- 3. Participants
    regressors = getattr(args, 'regressors', None) or []
    cat_regressors = getattr(args, 'categorical_regressors', None) or []

    part_body = f"""
<p>{len(dcm_subjects)} participant(s) had valid DCM files and were included in the PEB analysis.</p>
"""
    if regressors:
        part_body += f'<p><strong>Covariates used:</strong> {", ".join(regressors)}</p>'
    if cat_regressors:
        part_body += f'<p><strong>Categorical covariates:</strong> {", ".join(cat_regressors)}</p>'
    if contrast_str != 'N/A':
        part_body += f'<p><strong>Categorical contrast:</strong> <code>{contrast_str}</code></p>'

    if participants_df is not None and not participants_df.empty:
        part_body += '<h3>Participants file content</h3>'
        part_body += _html_table_from_df(participants_df)
    else:
        part_body += '<p>No participants.tsv content available.</p>'

    sections.append(_section('participants', 'Participants', part_body))

    # --- 4. Design matrix figures
    dm_body = ''
    if figures:
        for fig_info in figures:
            img_src = _img_to_base64(fig_info['fig_path'])
            fname   = fig_info['fig_path'].name
            dm_body += f"""
<figure class="visualization">
    <img src="{img_src}" alt="{fig_info['title']}" />
    <figcaption>{fig_info['title']}</figcaption>
    <a class="dl-btn" href="{img_src}" download="{fname}">⤓ Download SVG</a>
</figure>"""
    else:
        dm_body = '<p>No design matrix figures generated (nilearn may not be installed).</p>'
    sections.append(_section('design-matrix', 'Design Matrix', dm_body))

    # --- 5. Estimated parameters
    ep_body = _build_ep_section(spm_dir=spm_dir, args=args, config=config, logger=logger)
    sections.append(_section('parameters', 'Estimated Parameters', ep_body))

    # --- 6. Connectome
    ct_body = _build_connectome_section(connectome_figures or [])
    sections.append(_section('connectome', 'Connectome', ct_body))

    # --- 7. Outputs
    if bids_files:
        outputs_rows = ''
        for f in bids_files:
            suffix_desc = _SUFFIX_MAP.get(f['suffix'], (f['suffix'], ''))[1]
            outputs_rows += f"<tr><td>{f['bids_name']}</td><td>{suffix_desc}</td></tr>\n"
        outputs_body = f"""
<p>The following BIDS-compliant files have been created in
<code>{output_dir}/</code>:</p>
<table>
<thead><tr><th>Filename</th><th>Content</th></tr></thead>
<tbody>{outputs_rows}</tbody>
</table>
<p>Each TSV file is accompanied by a <code>.json</code> sidecar with metadata.</p>"""
    else:
        outputs_body = '<p>No BIDS output files were created.</p>'
    sections.append(_section('outputs', 'Output Files', outputs_body))

    # --- 6. Reproducibility
    cli_call = _reconstruct_cli_call(args)

    config_summary_rows = ''
    flat_config = {
        'matlab_path': config.get('matlab_path', 'N/A'),
        'spm_path': config.get('spm_path', 'N/A'),
        'analysis_type': config.get('fmri', {}).get('dcm', {}).get('analysis', 'csd'),
        'default_delay': config.get('fmri', {}).get('dcm', {}).get('default_delay', 'N/A'),
        'nonlinear': config.get('fmri', {}).get('dcm', {}).get('options', {}).get('nonlinear', 'N/A'),
        'two_state': config.get('fmri', {}).get('dcm', {}).get('options', {}).get('two_state', 'N/A'),
        'stochastic': config.get('fmri', {}).get('dcm', {}).get('options', {}).get('stochastic', 'N/A'),
        'induced': config.get('fmri', {}).get('dcm', {}).get('options', {}).get('induced', 'N/A'),
    }
    for k, v in flat_config.items():
        config_summary_rows += f'<tr><td>{k}</td><td><code>{v}</code></td></tr>\n'

    repro_body = f"""
<h3>CLI call (generic paths)</h3>
<pre>{cli_call}</pre>
<h3>Configuration summary</h3>
<table>
<thead><tr><th>Parameter</th><th>Value</th></tr></thead>
<tbody>{config_summary_rows}</tbody>
</table>"""
    sections.append(_section('reproducibility', 'Reproducibility', repro_body))

    # --- 7. Environment
    import platform
    py_version = sys.version.split()[0]
    env_rows = f"""
<tr><td>spmx version</td><td>{_version}</td></tr>
<tr><td>Python version</td><td>{py_version}</td></tr>
<tr><td>Platform</td><td>{platform.platform()}</td></tr>
<tr><td>MATLAB path</td><td><code>{config.get('matlab_path', 'N/A')}</code></td></tr>
<tr><td>SPM path</td><td><code>{config.get('spm_path', 'N/A')}</code></td></tr>
<tr><td>Report generated</td><td>{now.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
"""
    env_body = f"""
<table>
<thead><tr><th>Item</th><th>Value</th></tr></thead>
<tbody>{env_rows}</tbody>
</table>"""
    sections.append(_section('environment', 'Environment', env_body))

    # ------------------------------------------------------------------ footer
    footer_html = f"""
<footer>
<p>Generated by <strong>spmx</strong> v{_version} on {now.strftime('%Y-%m-%d')}</p>
<p>
  <a href="https://gitlab.ulb.be/ln2t/spmx">Documentation</a>
  <a href="https://gitlab.ulb.be/ln2t/spmx/issues">Report Issue</a>
</p>
</footer>"""

    # ------------------------------------------------------------------ assemble
    html = _HTML_TEMPLATE.format(
        title='Group DCM Report — spmx',
        css=_CSS,
        header=header_html,
        nav=nav_html,
        content='\n'.join(sections),
        footer=footer_html,
    )

    report_path = output_dir / 'group_dcm_report.html'
    report_path.write_text(html, encoding='utf-8')
    if logger:
        logger.info("HTML report saved to: %s", report_path)
    return report_path


# ---------------------------------------------------------------------------
# Top-level entry point called from group_dcm.py
# ---------------------------------------------------------------------------

def run_group_dcm_report(
    output_dir: Path,
    args,
    config: dict,
    participants_df,
    all_dcm_subjects: List[str],
    logger=None,
):
    """Orchestrate BIDS output structuring and HTML report generation.

    Should be called once after all PEB models have been run.

    Parameters
    ----------
    output_dir : Path
        The base output directory (OUTPUT_DIR).
    args : argparse.Namespace
    config : dict
    participants_df : pd.DataFrame
    all_dcm_subjects : list of str
        Combined list of subjects that had DCM files (all models).
    logger : logging.Logger, optional
    """
    spm_dir = output_dir / 'group' / 'SPM'
    group_dir = output_dir / 'group'
    figures_dir = group_dir / 'figures'

    if logger:
        logger.info("=== Generating group DCM report ===")
        logger.info("SPM dir: %s", spm_dir)
        logger.info("Group dir: %s", group_dir)

    # 1. Copy TSVs to BIDS filenames + create sidecars
    if logger:
        logger.info("Copying TSV outputs to BIDS-compliant filenames...")
    bids_files = copy_to_bids_group(
        spm_dir=spm_dir,
        group_dir=group_dir,
        args=args,
        config=config,
        logger=logger,
    )

    # 2. Generate design matrix figures
    if logger:
        logger.info("Generating design matrix figures...")
    figures = generate_design_matrix_figures(
        spm_dir=spm_dir,
        figures_dir=figures_dir,
        args=args,
        logger=logger,
    )

    # 3. Generate connectome figures
    if logger:
        logger.info("Generating connectome figures...")
    connectome_figures = generate_connectome_figures(
        spm_dir=spm_dir,
        figures_dir=figures_dir,
        args=args,
        logger=logger,
    )

    # 4. Generate HTML report
    if logger:
        logger.info("Generating HTML report...")
    report_path = generate_html_report(
        output_dir=group_dir,
        spm_dir=spm_dir,
        args=args,
        config=config,
        participants_df=participants_df,
        dcm_subjects=all_dcm_subjects,
        bids_files=bids_files,
        figures=figures,
        connectome_figures=connectome_figures,
        logger=logger,
    )

    if logger:
        logger.info("✓ Group DCM report complete: %s", report_path)

    return report_path
