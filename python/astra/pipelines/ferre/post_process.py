import os
import numpy as np
from typing import Iterable

from astra.utils import log, expand_path
from astra.pipelines.ferre.utils import (
    read_ferre_headers,
    read_control_file, 
    read_input_parameter_file,
    read_output_parameter_file,
    read_and_sort_output_data_file,
    get_processing_times,
    parse_ferre_spectrum_name,
    parse_header_path,
    TRANSLATE_LABELS
)

def write_pixel_array_with_names(path, names, data):
    os.system(f"mv {path} {path}.original")
    np.savetxt(
        path,
        np.hstack([np.atleast_2d(names).reshape((-1, 1)), data]).astype(str),
        fmt="%s"
    )

LARGE = 1e10 # TODO: This is also defined in pre_process, move it common

def post_process_ferre(dir, pwd=None, skip_pixel_arrays=False) -> Iterable[dict]:
    """
    Post-process results from a FERRE execution.

    :param dir:
        The working directory of the FERRE execution.
    
    :param pwd: [optional]
        The directory where FERRE was actually executed from. Normally `pwd` and `dir` will always be
        the same, so this keyword argument is optional. However, if FERRE is run in abundance mode
        with the `-l` flag, it might be executed from a path like `analysis/abundances/GKg_b/` but
        the individual FERRE executions exist in places like:

        `abundances/GKg_b/Al`
        `abundances/GKg_b/Mg`

        In these cases, the thing you want is `post_process_ferre('abundances/GKg_b/Al', 'abundances/GKg_b')`.
    """
    
    if skip_pixel_arrays:
        log.warning(f"Not checking any pixel arrays from FERRE!")

    dir = expand_path(dir)
    ref_dir = pwd or dir 
    # When finding paths, if the path is in the input.nml file, we should use `ref_dir`, otherwise `dir`.
    
    # TODO: Put this somewhere common?
    stdout_path = os.path.join(dir, "stdout")
    try:
        with open(stdout_path, "r") as fp:
            stdout = fp.read()
        # Parse timing information
        timing = get_processing_times(stdout)
    
    except:
        log.warning(f"No timing information available (tried stdout: {stdout_path})")
        timing = {}

    control_kwds = read_control_file(os.path.join(dir, "input.nml"))

    # Load input files.
    input_names, input_parameters = read_input_parameter_file(ref_dir, control_kwds)   
    N = len(input_names)

    try:
        parameters, e_parameters, meta, names_with_missing_outputs = read_output_parameter_file(ref_dir, control_kwds, input_names)
    except:
        D = int(control_kwds["NDIM"])
        parameters = np.nan * np.ones((N, D))
        e_parameters = np.ones_like(parameters)
        meta = {
            "log_snr_sq": np.nan * np.ones(N),
            "log_chisq_fit": np.nan * np.ones(N),
        }
        names_with_missing_outputs = input_names

    if len(names_with_missing_outputs) > 0:
        log.warn(f"The following {len(names_with_missing_outputs)} are missing outputs: {names_with_missing_outputs}")

    offile_path = os.path.join(ref_dir, control_kwds["OFFILE"])
    if not skip_pixel_arrays:
        flux = np.atleast_2d(np.loadtxt(os.path.join(ref_dir, control_kwds["FFILE"])))
        e_flux = np.atleast_2d(np.loadtxt(os.path.join(ref_dir, control_kwds["ERFILE"])))

        try:
            rectified_model_flux, names_with_missing_rectified_model_flux, output_rectified_model_flux_indices = read_and_sort_output_data_file(
                offile_path, 
                input_names
            )
            write_pixel_array_with_names(offile_path, input_names, rectified_model_flux)
        except:
            log.exception(f"Exception when trying to read and sort {offile_path}")
            names_with_missing_rectified_model_flux = input_names
            rectified_model_flux = np.nan * np.ones_like(flux)
                            
        sffile_path = os.path.join(ref_dir, control_kwds["SFFILE"])
        try:
            rectified_flux, names_with_missing_rectified_flux, output_rectified_flux_indices = read_and_sort_output_data_file(
                sffile_path,
                input_names
            )
            # Re-write the model flux file with the correct names.
            write_pixel_array_with_names(sffile_path, input_names, rectified_flux)
        except:
            log.exception(f"Exception when trying to read and sort {sffile_path}")
            names_with_missing_rectified_flux = input_names
            rectified_flux = np.nan * np.ones_like(flux)



        model_flux_output_path = os.path.join(dir, "model_flux.output")
        if os.path.exists(model_flux_output_path):
            model_flux, *_ = read_and_sort_output_data_file(
                model_flux_output_path,
                input_names
            )            
            write_pixel_array_with_names(model_flux_output_path, input_names, model_flux)
        else:
            log.warn(f"Cannot find model_flux output in {dir} ({model_flux_output_path})")
            model_flux = np.nan * np.ones_like(flux)
                        
        if len(names_with_missing_rectified_model_flux) > 0:
            log.warn(f"The following {len(names_with_missing_rectified_model_flux)} are missing model fluxes: {names_with_missing_rectified_model_flux}")
        if len(names_with_missing_rectified_flux) > 0:
            log.warn(f"The following {len(names_with_missing_rectified_flux)} are missing rectified fluxes: {names_with_missing_rectified_flux}")

        is_missing_model_flux = ~np.all(np.isfinite(model_flux), axis=1)
        is_missing_rectified_flux = ~np.all(np.isfinite(rectified_flux), axis=1)

    else:
        is_missing_model_flux = np.zeros(N, dtype=bool)
        is_missing_rectified_flux = np.zeros(N, dtype=bool)

    ferre_log_chi_sq = meta["log_chisq_fit"]
    ferre_log_snr_sq = meta["log_snr_sq"]
    
    is_missing_parameters = ~np.all(np.isfinite(parameters), axis=1)

    # Create some boolean flags. 
    header_path = control_kwds["SYNTHFILE(1)"]
    headers, *segment_headers = read_ferre_headers(expand_path(header_path))
    bad_lower = headers["LLIMITS"] + headers["STEPS"] / 8
    bad_upper = headers["ULIMITS"] - headers["STEPS"] / 8
    warn_lower = headers["LLIMITS"] + headers["STEPS"]
    warn_upper = headers["ULIMITS"] - headers["STEPS"]

    flag_grid_edge_bad = (parameters < bad_lower) | (parameters > bad_upper)
    flag_grid_edge_warn = (parameters < warn_lower) | (parameters > warn_upper)
    flag_ferre_fail = (parameters == -9999) | (e_parameters < -0.01) | ~np.isfinite(parameters)
    flag_any_ferre_fail = np.any(flag_ferre_fail, axis=1)
    flag_potential_ferre_timeout = is_missing_parameters
    flag_missing_model_flux = is_missing_model_flux | is_missing_rectified_flux

    # Get human-readable parameter names.
    to_human_readable_parameter_name = dict([(v, k) for k, v in TRANSLATE_LABELS.items()])
    parameter_names = [to_human_readable_parameter_name[k] for k in headers["LABEL"]]

    # TODO: we don't ahve any information about any continuum that was applied BEFORE ferre was executed.
    short_grid_name = parse_header_path(header_path)["short_grid_name"]

    common = dict(
        header_path=header_path, 
        short_grid_name=short_grid_name,
        pwd=dir, # TODO: Consider renaming
        ferre_n_obj=len(input_names),
        n_threads=control_kwds["NTHREADS"],
        interpolation_order=control_kwds["INTER"],
        continuum_reject=control_kwds.get("REJECTCONT", 0.0),
        continuum_order=control_kwds.get("NCONT", -1),
        continuum_flag=control_kwds.get("CONT", 0),
        continuum_observations_flag=control_kwds.get("OBSCONT", 0),
        f_format=control_kwds["F_FORMAT"],
        f_access=control_kwds["F_ACCESS"],
        weight_path=control_kwds["FILTERFILE"],
    )
    # Add frozen parameter flags.
    frozen_indices = set(range(1, 1 + len(parameter_names))).difference(set(map(int, control_kwds["INDV"].split())))
    for index in frozen_indices:
        common[f"flag_{parameter_names[index - 1]}_frozen"] = True

    ndim = int(control_kwds["NDIM"])
    for i, name in enumerate(input_names):
        name_meta = parse_ferre_spectrum_name(name)

        result = common.copy()
        result.update(
            source_id=name_meta["source_id"],
            spectrum_id=name_meta["spectrum_id"],
            initial_flags=name_meta["initial_flags"] or 0,
            upstream_id=name_meta["upstream_id"],
            ferre_name=name,
            ferre_input_index=name_meta["index"],
            ferre_output_index=i,
            r_chi_sq=10**ferre_log_chi_sq[i], 
            penalized_r_chi_sq=10**ferre_log_chi_sq[i],     
            ferre_log_snr_sq=ferre_log_snr_sq[i],
            flag_ferre_fail=flag_any_ferre_fail[i],
            flag_potential_ferre_timeout=flag_potential_ferre_timeout[i],
            flag_missing_model_flux=flag_missing_model_flux[i],
        )

        # Add correlation coefficients.
        #meta["cov"]
        #raise a

        # Add timing information, if we can.
        try:
            result.update(
                ferre_time_load_grid=timing["ferre_time_load_grid"][i],
                ferre_time_elapsed=timing["ferre_time_elapsed"][i],
            )
            result["t_elapsed"] = result["ferre_time_elapsed"] + result["ferre_time_load_grid"]/len(input_names)
        except:
            None

        if not skip_pixel_arrays:
            snr = np.nanmedian(flux[i]/e_flux[i])
            result.update(
                snr=snr,
                flux=flux[i],
                e_flux=e_flux[i],
                model_flux=model_flux[i],
                rectified_flux=rectified_flux[i],
                rectified_model_flux=rectified_model_flux[i],
            )

        for j, parameter in enumerate(parameter_names):
            result.update({
                f"initial_{parameter}": input_parameters[i, j],
                parameter: parameters[i, j],
                f"e_{parameter}": e_parameters[i, j],
                f"flag_{parameter}_ferre_fail": flag_ferre_fail[i, j],
                f"flag_{parameter}_grid_edge_bad": flag_grid_edge_bad[i, j],
                f"flag_{parameter}_grid_edge_warn": flag_grid_edge_warn[i, j],
            })

        # TODO: Load metadata from dir/meta.json (e.g., pre-continuum steps)
        # TODO: Include correlation coefficients?
        yield result
        