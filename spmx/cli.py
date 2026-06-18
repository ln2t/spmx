"""Command-line interface for spmx."""

import argparse
import sys
import textwrap
from pathlib import Path

from spmx import __version__


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class ColoredHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter with colored section headers."""

    def __init__(self, prog, indent_increment=2, max_help_position=40, width=100):
        super().__init__(prog, indent_increment, max_help_position, width)

    def _format_usage(self, usage, actions, groups, prefix):
        if prefix is None:
            prefix = f'{Colors.BOLD}Usage:{Colors.END} '
        return super()._format_usage(usage, actions, groups, prefix)

    def start_section(self, heading):
        if heading:
            heading = f'{Colors.BOLD}{Colors.CYAN}{heading}{Colors.END}'
        super().start_section(heading)


def _add_general_options(parser: argparse.ArgumentParser) -> None:
    """Add general options shared by all modules."""
    general = parser.add_argument_group(f'{Colors.BOLD}General Options{Colors.END}')

    general.add_argument(
        '-h',
        '--help',
        action='help',
        default=argparse.SUPPRESS,
        help='Show this help message and exit.',
    )
    general.add_argument(
        '--version',
        action='version',
        version=f'spmx {__version__}',
        help='Show program version and exit.',
    )
    general.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug-level logging output.',
    )
    general.add_argument(
        '--config',
        type=Path,
        metavar='FILE',
        help='Path to YAML configuration file. CLI arguments override config.',
    )
    general.add_argument(
        '--matlab-path',
        type=Path,
        metavar='PATH',
        dest='matlab_path',
        help='Path to MATLAB executable (default: search PATH).',
    )
    general.add_argument(
        '--spm-path',
        type=Path,
        metavar='PATH',
        dest='spm_path',
        help='Path to SPM installation (default: $MATLABPATH/toolboxes/spm).',
    )
    general.add_argument(
        '--clean-spm-files',
        action='store_true',
        dest='clean_spm_files',
        help='Delete <output_dir>/sourcedata/ after processing.',
    )
    general.add_argument(
        '--overwrite',
        action='store_true',
        help='Reprocess stages even if already marked as completed in ProcessingLog.',
    )


def _add_bids_filters(parser: argparse.ArgumentParser) -> None:
    """Add BIDS entity filter options."""
    filters = parser.add_argument_group(
        f'{Colors.BOLD}BIDS Entity Filters{Colors.END}',
        'Filter which data to process based on BIDS entities.',
    )
    filters.add_argument(
        '-p', '--participant-label',
        metavar='LABEL',
        dest='participant_label',
        nargs='+',
        help='Process one or more participants (without \'sub-\' prefix).',
    )
    filters.add_argument(
        '-s', '--session',
        metavar='SESSION',
        nargs='+',
        help='Process only these sessions (without \'ses-\' prefix).',
    )
    filters.add_argument(
        '-t', '--task',
        metavar='TASK',
        nargs='+',
        help='Process only these tasks (without \'task-\' prefix).',
    )
    filters.add_argument(
        '--space',
        metavar='SPACE',
        nargs='+',
        help='Process only data in these template spaces.',
    )


def _add_fit_options(parser: argparse.ArgumentParser) -> None:
    """Add fmri-fit-specific options."""
    fit_opts = parser.add_argument_group(
        f'{Colors.BOLD}Fit Options (--fit){Colors.END}'
    )
    fit_opts.add_argument(
        '--events-file',
        type=Path,
        metavar='PATH',
        dest='events_file',
        help='Path to events.tsv file. If not provided, file is discovered via BIDS layout.',
    )
    fit_opts.add_argument(
        '--condition',
        metavar='COND',
        nargs='+',
        help='Task condition names to include as regressors (from events.tsv trial_type).',
    )
    fit_opts.add_argument(
        '--confound',
        metavar='REG',
        nargs='+',
        help='Confound regressor names (columns in confounds_timeseries.tsv).',
    )
    fit_opts.add_argument(
        '--contrast',
        metavar='EXPR',
        nargs='+',
        help='Contrast expressions (e.g. \'face - house\'). Optional.',
    )
    fit_opts.add_argument(
        '--smooth',
        type=float,
        metavar='VALUE',
        help='Gaussian kernel FWHM in mm for image smoothing (0 = no smoothing).',
    )


def _add_dcm_options(parser: argparse.ArgumentParser) -> None:
    """Add fmri-dcm-specific options."""
    dcm_opts = parser.add_argument_group(
        f'{Colors.BOLD}DCM Options (--dcm){Colors.END}'
    )
    dcm_opts.add_argument(
        '--model',
        metavar='MODEL',
        nargs='+',
        help='Pre-defined DCM model names (e.g. \'full\', \'resting-state-full\').',
    )

    # Group-level DCM (PEB) options
    group_opts = parser.add_argument_group(
        f'{Colors.BOLD}Group-Level DCM Options (group analysis only){Colors.END}'
    )
    group_opts.add_argument(
        '--participants-file',
        type=Path,
        metavar='PATH',
        dest='participants_file',
        help='Path to participants.tsv file containing group-level covariates (for group-level DCM only).',
    )
    group_opts.add_argument(
        '--regressors',
        metavar='COL',
        nargs='+',
        help='Column names from participants file to use as covariates (e.g. age group sex IQ).',
    )
    group_opts.add_argument(
        '--categorical-regressors',
        metavar='COL',
        nargs='+',
        dest='categorical_regressors',
        help=(
            'Specify which regressors are categorical (e.g. group sex). '
            'Each categorical regressor must be paired with --contrast, which '
            'defines the linear combination of class labels to test '
            '(e.g. --contrast "control - patient"). '
            'The design matrix will contain K-1 orthogonal columns per K-class '
            'regressor, all de-meaned so they are orthogonal to SPM\'s intercept.'
        ),
    )
    group_opts.add_argument(
        '--group-name',
        metavar='NAME',
        dest='group_name',
        default='PEB_analysis',
        help='Name for the group-level analysis output (default: PEB_analysis).',
    )
    group_opts.add_argument(
        '--custom-group-label',
        metavar='LABEL',
        dest='custom_group_label',
        help=(
            'Custom label for the group-level analysis folder. '
            'If provided, OUTPUT_DIR/group_LABEL will be created instead of OUTPUT_DIR/group. '
            'Example: "--custom-group-label controls" creates OUTPUT_DIR/group_controls.'
        ),
    )


def create_parser() -> argparse.ArgumentParser:
    """Create the top-level argument parser."""
    description = textwrap.dedent(f'''\
    {Colors.BOLD}{Colors.GREEN}\
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║              spmx - BIDS-compliant SPM Processing Wrapper               ║
    ║                          v{__version__:<57s}║
    ╚══════════════════════════════════════════════════════════════════════════════╝{Colors.END}

    {Colors.BOLD}Description:{Colors.END}
      A wrapper around SPM (via MATLAB) for BIDS-compliant neuroimaging
      analysis. Supports fMRI GLM fitting, VOI extraction, and DCM estimation.

    {Colors.BOLD}Workflow:{Colors.END}
      All fMRI steps share the same INPUT_DIR and OUTPUT_DIR.
      INPUT_DIR contains preprocessed data (read-only).
      OUTPUT_DIR is the shared working directory for all SPM steps.
      ANALYSIS_LEVEL specifies the level of analysis: "participant" for first-level
      or "group" for group-level (currently work in progress).

      1. --fit : Copy preprocessed data, fit GLM model
      2. --voi : Extract VOI timeseries from seed regions
      3. --dcm : Specify and estimate DCM models

      {Colors.BOLD}Processing Status Tracking:{Colors.END}
        Each step stores completion status in dataset_description.json.
        By default, completed stages are skipped to avoid reprocessing.
        Use --overwrite to force reprocessing of already-completed stages.
    ''')

    epilog = textwrap.dedent(f'''\
    {Colors.BOLD}{Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    {Colors.BOLD}EXAMPLES{Colors.END}
    {Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}

    {Colors.BOLD}fMRI first-level GLM:{Colors.END}

      {Colors.YELLOW}# Fit GLM for all subjects{Colors.END}
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm participant --fit

      {Colors.YELLOW}# Fit with contrasts for specific subjects{Colors.END}
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm participant --fit \\
          --participant-label 01 02 --condition face house \\
          --contrast "face - house" --config my_config.yaml

      {Colors.YELLOW}# Fit with custom events file location{Colors.END}
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm participant --fit \\
          --events-file ~/data/events/sub-001_task-gas_events.tsv \\
          --condition gas --config my_config.yaml

    {Colors.BOLD}VOI extraction:{Colors.END}

      {Colors.YELLOW}# Extract VOIs defined in config{Colors.END}
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm participant --voi \\
          --config seeds.yaml

    {Colors.BOLD}DCM estimation:{Colors.END}

      {Colors.YELLOW}# Estimate DCM models{Colors.END}
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm participant --dcm \\
          --model resting-state-full --config dcm_config.yaml

    {Colors.BOLD}Full pipeline in one command:{Colors.END}

      {Colors.YELLOW}# Run fit, VOI extraction, and DCM in sequence{Colors.END}
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm participant \\
          --fit --voi --dcm --config full_config.yaml

    {Colors.BOLD}Handling completed stages:{Colors.END}

      {Colors.YELLOW}# By default, completed stages are skipped{Colors.END}
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm --fit
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm --voi
      {Colors.CYAN}# Output: 'Stage voi already completed for requested subjects/sessions'{Colors.END}

      {Colors.YELLOW}# Force reprocessing with --overwrite{Colors.END}
      spmx fmri /data/derivatives/fmriprep /data/derivatives/spm --fit \\
          --overwrite

    {Colors.BOLD}{Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    {Colors.BOLD}MORE INFORMATION{Colors.END}
    {Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}

      Documentation:  https://gitlab.ulb.be/ln2t/spmx
      Report Issues:  https://gitlab.ulb.be/ln2t/spmx/issues
      Version:        {__version__}
    ''')

    parser = argparse.ArgumentParser(
        prog='spmx',
        description=description,
        epilog=epilog,
        formatter_class=ColoredHelpFormatter,
        add_help=False,
    )

    subparsers = parser.add_subparsers(dest='module', help='Processing module')

    # -- fmri module ----------------------------------------------------------
    fmri_parser = subparsers.add_parser(
        'fmri',
        help='fMRI processing module (fit, VOI, DCM)',
        formatter_class=ColoredHelpFormatter,
        add_help=False,
    )

    # Positional arguments (input_dir, output_dir, analysis_level)
    required = fmri_parser.add_argument_group(
        f'{Colors.BOLD}Required Arguments{Colors.END}'
    )
    required.add_argument(
        'input_dir',
        type=Path,
        metavar='INPUT_DIR',
        help='Path to preprocessed BIDS dataset (read-only).',
    )
    required.add_argument(
        'output_dir',
        type=Path,
        metavar='OUTPUT_DIR',
        help='Shared output/working directory for all SPM steps.',
    )
    required.add_argument(
        'analysis_level',
        metavar='ANALYSIS_LEVEL',
        choices=['participant', 'group'],
        help='Analysis level: "participant" for first-level analysis, "group" for group-level (WIP).',
    )

    # Pipeline step flags
    steps = fmri_parser.add_argument_group(
        f'{Colors.BOLD}Pipeline Steps{Colors.END}',
        'Select one or more steps to run (executed in order: fit → voi → dcm).',
    )
    steps.add_argument(
        '--fit',
        action='store_true',
        help='Run first-level GLM specification, estimation, and optional contrasts.',
    )
    steps.add_argument(
        '--voi',
        action='store_true',
        help='Extract BOLD timeseries from seed regions (requires prior --fit).',
    )
    steps.add_argument(
        '--dcm',
        action='store_true',
        help='Specify and estimate DCM models (requires prior --fit and --voi).',
    )

    _add_bids_filters(fmri_parser)
    _add_general_options(fmri_parser)
    _add_fit_options(fmri_parser)
    _add_dcm_options(fmri_parser)

    # -- pet module (placeholder) ---------------------------------------------
    pet_parser = subparsers.add_parser(
        'pet',
        help='PET processing module (placeholder)',
        formatter_class=ColoredHelpFormatter,
        add_help=False,
    )
    pet_required = pet_parser.add_argument_group(
        f'{Colors.BOLD}Required Arguments{Colors.END}'
    )
    pet_required.add_argument(
        'input_dir',
        type=Path,
        metavar='INPUT_DIR',
        help='Path to input BIDS dataset.',
    )
    pet_required.add_argument(
        'output_dir',
        type=Path,
        metavar='OUTPUT_DIR',
        help='Path to output directory.',
    )
    _add_bids_filters(pet_parser)
    _add_general_options(pet_parser)

    # top-level help/version
    parser.add_argument(
        '-h',
        '--help',
        action='help',
        default=argparse.SUPPRESS,
        help='Show this help message and exit.',
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'spmx {__version__}',
    )

    return parser


def main() -> None:
    """Main entry point for the spmx CLI."""
    parser = create_parser()
    args = parser.parse_args()

    if args.module is None:
        parser.print_help()
        sys.exit(1)

    # Late imports to keep CLI responsive
    from spmx.config import load_config
    from spmx.logging_setup import setup_logging

    logger = setup_logging(debug=getattr(args, 'debug', False))

    config = load_config(
        config_path=getattr(args, 'config', None),
        matlab_path=getattr(args, 'matlab_path', None),
        spm_path=getattr(args, 'spm_path', None),
    )

    logger.info('spmx v%s', __version__)
    logger.info('Module: %s', args.module)
    logger.info('Input:  %s', args.input_dir)
    logger.info('Output: %s', args.output_dir)
    
    if hasattr(args, 'analysis_level'):
        logger.info('Analysis level: %s', args.analysis_level)

    if args.module == 'fmri':
        steps = []
        if getattr(args, 'fit', False):
            steps.append('fit')
        if getattr(args, 'voi', False):
            steps.append('voi')
        if getattr(args, 'dcm', False):
            steps.append('dcm')
        if steps:
            logger.info('Steps:  %s', ' → '.join(steps))

    try:
        _dispatch(args, config, logger)
    except KeyboardInterrupt:
        logger.error('Interrupted by user')
        sys.exit(130)
    except Exception as exc:
        logger.error('Pipeline failed: %s', exc, exc_info=getattr(args, 'debug', False))
        sys.exit(1)

    if getattr(args, 'clean_spm_files', False):
        import shutil

        sourcedata = args.output_dir / 'sourcedata'
        if sourcedata.exists():
            logger.info('Cleaning sourcedata directory: %s', sourcedata)
            shutil.rmtree(sourcedata)


def _discover_subject_session_pairs(input_dir, output_dir, args):
    """Discover which subject/session pairs need to be processed.
    
    When no explicit --participant-label is given, discovers from INPUT directory
    (what's available in fmriprep) to ensure we process all available data, not just
    what's already been processed. 
    
    Returns a list of (subject, session) tuples based on explicit arguments
    or discovered from the input directory.
    """
    from spmx.bids_utils import get_layout
    
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    requested_subjects = getattr(args, "participant_label", None)
    requested_sessions = getattr(args, "session", None)
    requested_tasks = getattr(args, "task", None)
    
    subject_session_pairs = []
    
    # If explicit subjects/sessions were requested, build pairs from those
    if requested_subjects:
        if requested_sessions:
            # Both subjects and sessions specified
            for subj in requested_subjects:
                for sess in requested_sessions:
                    subject_session_pairs.append((subj, sess))
        else:
            # Only subjects specified - discover sessions for each from input_dir via BIDSLayout
            if input_dir.exists():
                try:
                    layout = get_layout(input_dir)
                    for subject in requested_subjects:
                        sessions = layout.get_sessions(subject=subject)
                        if sessions:
                            for session in sessions:
                                subject_session_pairs.append((subject, session))
                        else:
                            subject_session_pairs.append((subject, None))
                except Exception:
                    # If layout fails, just return the subjects with no session
                    for subject in requested_subjects:
                        subject_session_pairs.append((subject, None))
    elif requested_sessions and input_dir.exists():
        # Sessions specified but not subjects - discover all subjects, filter by session
        try:
            layout = get_layout(input_dir)
            all_subjects = layout.get_subjects()
            for subject in all_subjects:
                for session in requested_sessions:
                    if session in layout.get_sessions(subject=subject):
                        subject_session_pairs.append((subject, session))
        except Exception:
            pass  # If we can't access layout, return empty
    elif input_dir.exists():
        # No explicit subjects/sessions - discover all from INPUT directory (fmriprep)
        try:
            layout = get_layout(input_dir)
            subjects = layout.get_subjects()
            
            # Filter by task if specified
            for subject in subjects:
                sessions = layout.get_sessions(subject=subject)
                
                if sessions:
                    for session in sessions:
                        # If task is specified, only include if task exists for this subject/session
                        if requested_tasks:
                            session_tasks = layout.get_tasks(subject=subject, session=session)
                            if any(t in session_tasks for t in requested_tasks):
                                subject_session_pairs.append((subject, session))
                        else:
                            subject_session_pairs.append((subject, session))
                else:
                    # No sessions for this subject
                    if requested_tasks:
                        subject_tasks = layout.get_tasks(subject=subject)
                        if any(t in subject_tasks for t in requested_tasks):
                            subject_session_pairs.append((subject, None))
                    else:
                        subject_session_pairs.append((subject, None))
        except Exception:
            pass  # If we can't access layout, return empty
    
    return subject_session_pairs


def _dispatch(args, config, logger):
    """Route to the correct module handler."""
    if args.module == 'fmri':
        # Validate analysis level
        analysis_level = getattr(args, 'analysis_level', 'participant')
        
        if analysis_level == 'group':
            # Group-level analysis (currently only DCM/PEB supported)
            logger.info('═════════════════════════════════════════════════════════════════════')
            logger.info('Group-level DCM (PEB) Analysis')
            logger.info('═════════════════════════════════════════════════════════════════════')
            
            if not args.dcm:
                logger.error(
                    'For group-level analysis, --dcm flag is required. '
                    'Fit and VOI steps must be run at participant level.'
                )
                sys.exit(1)
            
            # Import and run group-level DCM
            from spmx.fmri.group_dcm import run_group_dcm
            run_group_dcm(args, config, logger)
            return
        
        # Participant-level analysis
        logger.info('═════════════════════════════════════════════════════════════════════')
        logger.info('Participant-level Analysis')
        logger.info('═════════════════════════════════════════════════════════════════════')
        
        if not (args.fit or args.voi or args.dcm):
            logger.error(
                'No pipeline step specified. Use --fit, --voi, and/or --dcm.'
            )
            sys.exit(1)

        from spmx.bids_utils import (
            create_dataset_description,
            check_fmri_prerequisites,
            stage_already_processed,
        )

        input_dir = Path(args.input_dir).resolve()
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        create_dataset_description(output_dir, module="fmri", submodule=None)

        # Discover subject/session pairs from INPUT directory to ensure we process all available data
        subject_session_pairs = _discover_subject_session_pairs(input_dir, output_dir, args)
        overwrite = getattr(args, 'overwrite', False)

        if args.fit:
            # Check if fit is already complete
            skip_fit = False
            if subject_session_pairs and stage_already_processed(output_dir, subject_session_pairs, "fit"):
                if not overwrite:
                    logger.info("Stage 'fit' already completed for requested subjects/sessions. Use --overwrite to reprocess.")
                    skip_fit = True
                else:
                    logger.info("Stage 'fit' already completed. --overwrite set, processing anyway.")
            
            if not skip_fit:
                from spmx.fmri.fit import run_fit
                run_fit(args, config, logger)

        if args.voi:
            # Check prerequisites before running
            if not check_fmri_prerequisites(output_dir, args, "voi", logger):
                sys.exit(1)
            
            # Check if voi is already complete
            skip_voi = False
            if subject_session_pairs and stage_already_processed(output_dir, subject_session_pairs, "voi"):
                if not overwrite:
                    logger.info("Stage 'voi' already completed for requested subjects/sessions. Use --overwrite to reprocess.")
                    skip_voi = True
                else:
                    logger.info("Stage 'voi' already completed. --overwrite set, processing anyway.")
            
            if not skip_voi:
                from spmx.fmri.voi import run_voi
                run_voi(args, config, logger)

        if args.dcm:
            # Check prerequisites before running
            if not check_fmri_prerequisites(output_dir, args, "dcm", logger):
                sys.exit(1)
            
            # Check if dcm is already complete
            skip_dcm = False
            if subject_session_pairs and stage_already_processed(output_dir, subject_session_pairs, "dcm"):
                if not overwrite:
                    logger.info("Stage 'dcm' already completed for requested subjects/sessions. Use --overwrite to reprocess.")
                    skip_dcm = True
                else:
                    logger.info("Stage 'dcm' already completed. --overwrite set, processing anyway.")
            
            if not skip_dcm:
                from spmx.fmri.dcm import run_dcm
                run_dcm(args, config, logger)

    elif args.module == 'pet':
        from spmx.pet.runner import run_pet

        run_pet(args, config, logger)

    else:
        logger.error('Unknown module: %s', args.module)
        sys.exit(1)


if __name__ == "__main__":
    main()
