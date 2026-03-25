from sdss_access.path import Path
from tqdm import tqdm, trange
import os
import logging
import numpy as np
from astropy.table import Table
from pathlib import Path as Pathpy
from astropy.io import fits
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('null_columns_report.log'),
        logging.StreamHandler()  # Also print to console
    ]
)

logger = logging.getLogger(__name__)

def check_null_columns(file_path):
    """
    check for null columns in all HDUs of file
    """
    results_tbl = {}
    hdu = fits.open(file_path)
    for i in range(1, len(hdu)):
        results_tbl[f'HDU {i}'] = {}
        # Read the file as an Astropy Table
        tbl = Table.read(file_path, hdu=i)

        if len(tbl) > 0:
            # Find columns where all values are masked/null
            null_cols_all = [
                col for col in tbl.colnames
                if hasattr(tbl[col], 'mask') and tbl[col].mask.all()
            ]

            results_tbl[f'HDU {i}']['all'] = null_cols_all

            if null_cols_all:
                logger.warning(
                    f"HDU = {i}, File: {file_path.name} | "
                    f"All-null columns ({len(null_cols_all)}): {', '.join(null_cols_all)}"
                )

            # do release specific
            try:
                release = np.unique(tbl['release'])
                for r in release:
                    ev_release = tbl['release'] == r
                    # Find columns where all values are masked/null
                    null_cols = [
                        col for col in tbl.colnames
                        if hasattr(tbl[col], 'mask') and tbl[col][ev_release].mask.all()
                    ]

                    # remove things in the all category
                    null_cols = [item for item in null_cols if item not in null_cols_all]

                    results_tbl[f'HDU {i}'][r] = null_cols

                    if null_cols:
                        logger.warning(
                            f"HDU = {i}, File: {file_path.name} | "
                            f"{r} only-null columns ({len(null_cols)}): {', '.join(null_cols)}"
                        )
            except KeyError:
                pass
    return results_tbl


def process_directory(path, v_astra):
    """
    Process all astra summary files
    """
    directory_path = str(Pathpy(path.full('mwmAllStar', v_astra=v_astra)).parent)
    directory = Pathpy(directory_path)
    logger.info(f"Starting scan of directory: {directory}")

    fits_files = list(directory.glob("*.fits*"))
    logger.info(f"Found {len(fits_files)} FITS files to process")

    results = {}
    for file_path in fits_files:
        results[file_path.name] = check_null_columns(file_path)
    return results

# Example usage
if __name__ == "__main__":

    cwd = Pathpy(".")
    files = list(cwd.glob("astraAllStarASPCAP*.fits"))

    raise a
    # Process all FITS files in IPL-4
    path = Path(release='ipl4', preserve_envvars=True)
    v_astra = '0.8'
    results = process_directory(path, v_astra)
    with open('null_columns_report_dict.json', 'w') as f:
        json.dump(results, f, indent=4)

