"""PET processing module runner (placeholder)."""

from pathlib import Path

from spmx.bids_utils import create_dataset_description


def run_pet(args, config, logger):
    """Run PET processing (placeholder).

    Parameters
    ----------
    args : argparse.Namespace
    config : dict
    logger : logging.Logger
    """
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create dataset_description.json for output directory (BIDS compliance)
    create_dataset_description(output_dir, module="pet", submodule=None)

    logger.info("PET module (placeholder) — nothing to do.")
    logger.info("This module will be implemented in a future release.")
