"""Task for executing FERRE."""
import os
import numpy as np
import subprocess
import sys
import pickle
from tempfile import mkdtemp
from astropy.nddata import StdDevUncertainty
from collections import OrderedDict
from astra import log, __version__
from astra.base import TaskInstance, Parameter, TupleParameter, DictParameter
from astra.database.astradb import Status, Task, TaskBundle, Bundle
from astra.tools.spectrum import Spectrum1D, SpectrumList
from astra.tools.spectrum.utils import spectrum_overlaps
from astra.contrib.ferre import bitmask, utils
from astra.utils import dict_to_list, list_to_dict, flatten, executable, expand_path, nested_list
from astra.database.astradb import (
    database,
    DataProduct,
    TaskOutputDataProducts,
    Output,
    TaskOutput,
    FerreOutput,
)
from astra.sdss.datamodels.pipeline import create_pipeline_product
from astra.sdss.datamodels.base import get_extname
from astra.contrib.ferre.bitmask import (PixelBitMask, ParamBitMask)

# FERRE v4.8.8 src trunk : /uufs/chpc.utah.edu/common/home/sdss09/software/apogee/Linux/apogee/trunk/external/ferre/src


class Ferre(TaskInstance):

    header_path = Parameter(bundled=True)
    initial_parameters = DictParameter(default=None)
    frozen_parameters = DictParameter(default=None, bundled=True)
    interpolation_order = Parameter(default=3, bundled=True)
    weight_path = Parameter(default=None, bundled=True)
    lsf_shape_path = Parameter(default=None, bundled=True)
    lsf_shape_flag = Parameter(default=0, bundled=True)
    error_algorithm_flag = Parameter(default=1, bundled=True)
    wavelength_interpolation_flag = Parameter(default=0, bundled=True)
    optimization_algorithm_flag = Parameter(default=3, bundled=True)
    continuum_flag = Parameter(default=1, bundled=True)
    continuum_order = Parameter(default=4, bundled=True)
    continuum_segment = Parameter(default=None, bundled=True)
    continuum_reject = Parameter(default=0.3, bundled=True)
    continuum_observations_flag = Parameter(default=1, bundled=True)
    full_covariance = Parameter(default=False, bundled=True)
    pca_project = Parameter(default=False, bundled=True)
    pca_chi = Parameter(default=False, bundled=True)
    f_access = Parameter(default=None, bundled=True)
    f_format = Parameter(default=1, bundled=True)
    ferre_kwds = DictParameter(default=None, bundled=True)
    parent_dir = Parameter(default=None, bundled=True)
    n_threads = Parameter(default=1, bundled=True)

    # For rectification to be made before the FERRE run.
    continuum_method = Parameter(default=None)
    continuum_kwargs = DictParameter(default=None)

    data_slice = TupleParameter(default=[0, 1]) # only relevant for ApStar data products

    bad_pixel_flux_value = Parameter(default=1e-4)
    bad_pixel_sigma_value = Parameter(default=1e10)
    skyline_sigma_multiplier = Parameter(default=100)
    min_sigma_value = Parameter(default=0.05)

    # FERRE will sometimes hang forever if there is a spike in the data (e.g., a skyline) that
    # is not represented by the uncertainty array (e.g., it looks 'real').
    # An example of this on Utah is under ~/ferre-death-examples/spike/
    # To self-preserve FERRE, we do a little adjustment to the uncertainty array.
    spike_threshold_to_inflate_uncertainty = Parameter(default=5)

    # Maximum timeout in seconds for FERRE
    timeout = Parameter(default=12 * 60 * 60, bundled=True)

    @classmethod
    def estimate_relative_cost_factors(cls, parameters):
        """
        Return a three-length array containing the relative cost per:
            - task,
            - data product, and
            - size of the data product.

        Here 'relative cost' is relative to other tasks of this type. For example, if one parameter
        makes the cost of this task twice as long per data product, this method will take that
        into account. That makes Slurm scheduling more efficient.
        """
        # The cost scales significantly with the number of dimensions being solved for.
        headers, *segment_headers = utils.read_ferre_headers(
            expand_path(parameters["header_path"])
        )
        D = int(headers["N_OF_DIM"] - len(parameters.get("frozen_parameters", {})))

        # some rough scaling from experiments on 20220412
        scales = {6: 1, 7: 2, 8: 10}
        scale = scales.get(D, 1)

        factor_task, factor_data_product, factor_data_product_size = (0, 0, 0)

        # Now we just need to figure out where this scaling should apply.
        # If we are slicing the data products then the scaling should go as number of data products.

        # If we are not slicing the data products then the scaling should go as the size of the
        # data products
        if parameters.get("data_slice", None) is None:
            factor_data_product_size = scale
        else:
            # Estimate the number slicing each time.
            N = np.ptp(np.array(parameters["data_slice"]).flatten())
            factor_data_product = N * scale

        return np.array([factor_task, factor_data_product, factor_data_product_size])

    @classmethod
    def to_name(cls, i, j, k, l, data_product, snr, **kwargs):
        keys = ("cat_id", "obj")
        for key in keys:
            if key in data_product.kwargs:
                obj = data_product.kwargs[key]
                break
        else:
            obj = "NOOBJ"
        return f"{i:.0f}_{j:.0f}_{k:.0f}_{l:.0f}_{snr:.1f}_{obj}"

    @classmethod
    def from_name(cls, name):
        i, j, k, l, snr, *obj = name.split("_")
        return dict(i=int(i), j=int(j), k=int(k), l=int(l), snr=float(snr), obj="_".join(obj))

    @property
    def working_directory(self):
        """ The directory where FERRE is executed. """
        parent_dir = expand_path(self.parent_dir)
        bundle = self.context.get("bundle", None)
        if bundle is None:
            tasks = self.context.get("tasks", None)
            if tasks is not None:
                if len(tasks) == 1:
                    descr = f"task_{tasks[0].id}"
                else:
                    if len(tasks) == 2:
                        first_task, last_task = tasks
                    else:
                        first_task, *_, last_task = tasks
                    descr = f"tasks/task_{first_task.id}_to_{last_task.id}"
                dir = os.path.join(parent_dir, descr)
            else:
                raise ValueError(f"Can't get context to create working directory")
        else:
            dir = os.path.join(parent_dir, f"bundles/{bundle.id % 100:0>2.0f}/{bundle.id}")
        return dir


    def pre_execute(self):

        # Check if the pre-execution has already happened somewhere else.
        if "pre_execute" in self.context:
            return None

        # Create a temporary directory.
        dir = self.working_directory
        os.makedirs(dir, exist_ok=True)

        log.info(f"Created directory for FERRE: {dir}")

        # Validate the control file keywords.
        (
            control_kwds,
            headers,
            segment_headers,
            frozen_parameters,
        ) = utils.validate_ferre_control_keywords(
            header_path=self.header_path,
            frozen_parameters=self.frozen_parameters,
            interpolation_order=self.interpolation_order,
            weight_path=self.weight_path,
            lsf_shape_path=self.lsf_shape_path,
            lsf_shape_flag=self.lsf_shape_flag,
            error_algorithm_flag=self.error_algorithm_flag,
            wavelength_interpolation_flag=self.wavelength_interpolation_flag,
            optimization_algorithm_flag=self.optimization_algorithm_flag,
            continuum_flag=self.continuum_flag,
            continuum_order=self.continuum_order,
            continuum_segment=self.continuum_segment,
            continuum_reject=self.continuum_reject,
            continuum_observations_flag=self.continuum_observations_flag,
            full_covariance=self.full_covariance,
            pca_project=self.pca_project,
            pca_chi=self.pca_chi,
            n_threads=self.n_threads,
            f_access=self.f_access,
            f_format=self.f_format,
        )

        # Write the control file.
        with open(os.path.join(dir, "input.nml"), "w") as fp:
            fp.write(utils.format_ferre_control_keywords(control_kwds))       

        pixel_mask = PixelBitMask()

        # Construct mask to match FERRE model grid.
        model_wavelengths = tuple(map(utils.wavelength_array, segment_headers))

        # Read in the input data products.
        indices, flux, sigma, names, initial_parameters_as_dicts = ([], [], [], [], [])
        for i, (task, data_products, parameters) in enumerate(self.iterable()):
            for j, data_product in enumerate(flatten(data_products)):
                for k, spectrum in enumerate(SpectrumList.read(data_product.path, data_slice=parameters["data_slice"])):
                    if not spectrum_overlaps(spectrum, np.hstack(model_wavelengths)):
                        continue

                    N, P = spectrum.flux.shape
                    wl_ = spectrum.wavelength.value
                    flux_ = spectrum.flux.value
                    sigma_ = spectrum.uncertainty.represent_as(StdDevUncertainty).array
                    
                    # Perform any continuum rectification pre-processing.
                    if parameters["continuum_method"] is not None:
                        f_continuum = executable(parameters["continuum_method"])(**parameters["continuum_kwargs"])
                        f_continuum.fit(spectrum)
                        continuum = f_continuum(spectrum)
                        flux_ /= continuum
                        sigma_ /= continuum
                    else:
                        f_continuum = None     
                    
                    # Inflate errors around skylines, etc.
                    skyline_mask = (
                        spectrum.meta["BITMASK"] & pixel_mask.get_value("SIG_SKYLINE")
                    ) > 0
                    sigma_[skyline_mask] *= parameters["skyline_sigma_multiplier"]
                    
                    # Set bad pixels to have no useful data.
                    if parameters["bad_pixel_flux_value"] is not None or parameters["bad_pixel_sigma_value"] is not None:                            
                        bad = (
                            ~np.isfinite(flux_)
                            | ~np.isfinite(sigma_)
                            | (flux_ < 0)
                            | (sigma_ < 0)
                            | ((spectrum.meta["BITMASK"] & pixel_mask.get_level_value(1)) > 0)
                        )

                        flux_[bad] = parameters["bad_pixel_flux_value"]
                        sigma_[bad] = parameters["bad_pixel_sigma_value"]

                    # Clip the error array. This is a pretty bad idea but I am doing what was done before!
                    if parameters["min_sigma_value"] is not None:
                        sigma_ = np.clip(sigma_, parameters["min_sigma_value"], np.inf)

                    # Retrict to the pixels within the model wavelength grid.
                    mask = _get_ferre_mask(wl_, model_wavelengths)

                    flux_ = flux_[:, mask]
                    sigma_ = sigma_[:, mask]

                    # Sometimes FERRE will run forever.
                    # TODO: rename to spike_threshold_for_bad_pixel
                    if parameters["spike_threshold_to_inflate_uncertainty"] > 0:

                        flux_median = np.median(flux_, axis=1).reshape((-1, 1))
                        flux_stddev = np.std(flux_, axis=1).reshape((-1, 1))
                        sigma_median = np.median(sigma_, axis=1).reshape((-1, 1))

                        delta = (flux_ - flux_median) / flux_stddev
                        is_spike = (delta > parameters["spike_threshold_to_inflate_uncertainty"])
                        #* (
                        #    sigma_ < (parameters["spike_threshold_to_inflate_uncertainty"] * sigma_median)
                        #)
                        if np.any(is_spike):
                            fraction = np.sum(is_spike) / is_spike.size
                            log.warning(
                                f"Inflating uncertainties for {np.sum(is_spike)} pixels ({100 * fraction:.2f}%) that were identified as spikes."
                            )
                            for pi in range(is_spike.shape[0]):
                                n = np.sum(is_spike[pi])
                                if n > 0:
                                    log.debug(f"  {n} pixels on spectrum index {pi}")
                            sigma_[is_spike] = parameters["bad_pixel_sigma_value"]
                            #raise a
                            # interpolate over them too?

                    # Parse initial parameters. Expected types:
                    # - dictionary of single values -> apply single value to all N spectra
                    # - dictionary of lists of length N -> different value per spectrum
                    # - dictionary of lists of single value -> apply single value to all N spectra
                    # TODO: Move this logic elsewhere so it's testable.
                    initial_parameters = parameters["initial_parameters"]
                    # Allow initital parameters to be a dict (applied to all spectra) or a list of dicts (one per spectra)
                    log.debug(
                        f"There are {N} spectra in {task} {data_product} and initial params is {len(initial_parameters)} long"
                    )
                    log.debug(f"And {set(map(type, initial_parameters))}")

                    if len(initial_parameters) == N and all(
                        isinstance(_, dict) for _ in initial_parameters
                    ):
                        log.debug(
                            f"Allowing different initial parameters for each {N} spectra on task {task}"
                        )
                        initial_parameters_as_dicts.extend(initial_parameters)
                    else:
                        if N > 1:
                            log.debug(
                                f"Using same initial parameters {initial_parameters} for all {N} spectra on task {task}"
                            )
                        initial_parameters_as_dicts.extend([initial_parameters] * N)

                    for l in range(N):
                        indices.append((i, j, k, l))
                        names.append(
                            self.to_name(
                                i=i,
                                j=j,
                                k=k,
                                l=l,
                                data_product=data_product,
                                snr=spectrum.meta["SNR"].flatten()[l],
                            )
                        )
                        flux.append(flux_)
                        sigma.append(sigma_)

        # Convert list of dicts of initial parameters to array.
        initial_parameters = utils.validate_initial_and_frozen_parameters(
            headers,
            initial_parameters_as_dicts,
            frozen_parameters,
            clip_initial_parameters_to_boundary_edges=True,
            clip_epsilon_percent=1,
        )

        with open(os.path.join(dir, control_kwds["pfile"]), "w") as fp:
            for name, point in zip(names, initial_parameters):
                fp.write(utils.format_ferre_input_parameters(*point, name=name))

        indices = np.array(indices)
        N, _ = indices.shape
        flux = np.array(flux).reshape((N, -1))
        sigma = np.array(sigma).reshape((N, -1))

        # Write data arrays.
        savetxt_kwds = dict(fmt="%.4e", footer="\n")
        np.savetxt(
            os.path.join(dir, control_kwds["ffile"]), flux, **savetxt_kwds
        )
        np.savetxt(
            os.path.join(dir, control_kwds["erfile"]), sigma, **savetxt_kwds
        )
        return None


    def execute(self):
        """Execute FERRE"""

        dir = self.working_directory

        stdout_path = os.path.join(dir, "stdout")
        stderr_path = os.path.join(dir, "stderr")

        # Set the timeout based on how many spectra there are, and number of threads, and number of degrees of freedom
        N = utils.wc(os.path.join(dir, "parameters.input"))
        N_threads = 1
        with open(os.path.join(dir, "input.nml"), "r") as fp:
            for line in fp.readlines():
                if line.startswith("NTHREADS"):
                    N_threads = int(line.split()[-1])
                elif line.startswith("NOV"):
                    N_dof = int(line.split()[-1])

        # worst case scenario is 5 minutes for every spectrum
        timeout = max(300 * N / N_threads, 1800)
        try:
            with open(stdout_path, "w") as stdout:
                with open(stderr_path, "w") as stderr:
                    process = subprocess.run(
                        ["ferre.x"],
                        cwd=dir,
                        stdout=stdout,
                        stderr=stderr,
                        check=False,
                        timeout=timeout, # a week! # self.timeout
                    )
        except:
            log.exception(f"Exception when calling FERRE in {dir}:")
            log.info(f"Will continue to try and recover what we can")

        else:
            with open(stdout_path, "r") as fp:
                stdout = fp.read()
            with open(stderr_path, "r") as fp:
                stderr = fp.read()

            """
            # Issues with processes hanging forever, which might be related to pipe buffers being full.

            try:
                process = subprocess.Popen(
                    ["ferre.x"],
                    cwd=dir,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=1,
                    encoding="utf-8",
                    close_fds="posix" in sys.builtin_module_names
                )
            except subprocess.CalledProcessError:
                log.exception(f"Exception when calling FERRE in {dir}")
                raise
            else:
                try:
                    stdout, stderr = process.communicate()
                except subprocess.TimeoutExpired:
                    raise
                else:
                    log.info(f"FERRE stdout:\n{stdout}")
                    log.error(f"FERRE stderr:\n{stderr}")
            """

            n_done, n_error, control_kwds, meta = utils.parse_ferre_output(dir, stdout, stderr)
            log.info(f"FERRE finished with {n_done} successful and {n_error} errors.")

        # Write stdout and stderr
        #with open(os.path.join(dir, "stdout"), "w") as fp:
        #    fp.write(stdout)
        #with open(os.path.join(dir, "stderr"), "w") as fp:
        #    fp.write(stderr)

        '''
        # We actually have timings per-spectrum but we aggregate this to per-task.
        # We might want to store the per-data-product and per-spectrum timing elsewhere.
        try:
            # Update internal timings with those from FERRE.
            timings = utils.get_processing_times(stdout)
            """
            names = np.loadtxt(os.path.join(dir, control_kwds["PFILE"]), usecols=0, dtype=str)
            time_execute_per_task = np.zeros(len(self.context["tasks"]))
            for name, t in zip(names, timings["time_per_spectrum"]):
                time_execute_per_task[self.from_name(name)["i"]] += t

            # And store the FERRE load time as the bundle overhead.
            # TODO: The only other way around this is to somehow take the number of threads used
            #       into account when timing a task, but that becomes pretty tricky for all tasks.
            self.context["timing"]["time_execute_per_task"] = list(time_execute_per_task)
            self.context["timing"]["time_execute_bundle_overhead"] = timings["time_load"]
            """
        except:
            log.exception(
                f"Exception when trying to update internal task timings from FERRE."
            )
        else:
            log.debug(f"Timing information from FERRE stdout:")
            for key, value in timings.items():
                log.debug(f"\t{key}: {value}")
        '''


    def post_execute(self):
        """
        Post-execute hook after FERRE is complete.

        Read in the output files, create rows in the database, and produce output data products.
        """
        dir = self.working_directory

        with open(os.path.join(dir, "stdout"), "r") as fp:
            stdout = fp.read()
        with open(os.path.join(dir, "stderr"), "r") as fp:
            stderr = fp.read()

        n_done, n_error, control_kwds, ferre_meta = utils.parse_ferre_output(dir, stdout, stderr)
        timings = utils.get_processing_times(stdout)

        path = os.path.join(dir, control_kwds["PFILE"])
        input_names = np.atleast_1d(np.loadtxt(path, usecols=(0, ), dtype=str))
    
        # FFILE and ERFILE are inputs, so they will always be the right shape.
        try:
            path = os.path.join(dir, control_kwds["FFILE"])
            flux = np.atleast_2d(np.loadtxt(path))
        except:
            log.exception(f"Failed to load input flux from {path}")
        try:
            path = os.path.join(dir, control_kwds["ERFILE"])
            flux_sigma = np.atleast_2d(np.loadtxt(path))
        except:
            log.exception(f"Failed to load flux sigma from {path}")
            raise

        # Now parse the outputs from the FERRE run.
        path = os.path.join(dir, control_kwds["OPFILE"])
        try:
            output_names, output_params, output_param_errs, meta = utils.read_output_parameter_file(
                path,
                n_dimensions=control_kwds["NDIM"],
                full_covariance=control_kwds["COVPRINT"],
            )
        except:
            log.exception(f"Exception when parsing FERRE output parameter file {path}")
            raise

        if len(input_names) > len(output_names):
            log.warning(f"Number of input parameters does not match output parameters ({len(input_names)} > {len(output_names)}). FERRE may have failed. We will pick up the pieces..")

        # Which entries are missing?
        missing_names = list(set(input_names).difference(output_names))
        missing_indices = [np.where(input_names == mn)[0][0] for mn in missing_names]
        for i in np.argsort(missing_indices):
            missing_name, missing_index = (missing_names[i], missing_indices[i])
            log.warning(f"Missing parameters for spectrum named {missing_name} (index {missing_index}; row {missing_index+1})")        

        # We will fill the missing parameters with nans, and missing fluxes with nans too
        N, P = flux.shape
        D = int(control_kwds["NDIM"]) 
        params = np.nan * np.ones((N, D), dtype=float)
        param_errs = np.nan * np.ones((N, D), dtype=float)
        log_chisq_fit = np.nan * np.ones(N)
        log_snr_sq = np.nan * np.ones(N)
        frac_phot_data_points = np.nan * np.ones(N)


        indices = []
        for i, name in enumerate(output_names):
            index, = np.where(input_names == name)
            assert len(index) == 1, f"Name {name} (index {i}) appears more than once in the input parameter file!"
            indices.append(index[0])
        indices = np.array(indices)

        params[indices] = output_params
        param_errs[indices] = output_param_errs
        log_chisq_fit[indices] = meta["log_chisq_fit"]
        log_snr_sq[indices] = meta["log_snr_sq"]
        frac_phot_data_points[indices] = meta["frac_phot_data_points"]

        # Now get outputs.
        if ferre_meta.get("ferre_version", None) == "v4.8.9":
            path = os.path.join(dir, control_kwds["OFFILE"])
            _model_flux = np.atleast_2d(np.loadtxt(path, usecols=1 + np.arange(P)))
            _model_flux_names = np.atleast_1d(np.loadtxt(path, usecols=(0, ), dtype=str))
            model_indices = []
            for i, name in enumerate(_model_flux_names):
                index, = np.where(input_names == name)
                model_indices.append(index[0])
            model_indices = np.array(model_indices)

            model_flux = np.nan * np.ones((N, P), dtype=float)
            model_flux[model_indices] = _model_flux

            if "SFFILE" in control_kwds:
                try:
                    path = os.path.join(dir, control_kwds["SFFILE"])
                    _normalized_flux = np.atleast_2d(np.loadtxt(path, usecols=1 + np.arange(P)))
                    _normalized_flux_names = np.atleast_1d(np.loadtxt(path, usecols=(0, ), dtype=str))
                except:
                    log.exception(f"Failed to load normalized observed flux from {path}")
                    raise
                else:
                    # Order the normalized flux to be the same as the inputs
                    normalized_flux_indices = []
                    for i, name in enumerate(_normalized_flux_names):
                        index, = np.where(input_names == name)
                        normalized_flux_indices.append(index[0])
                    normalized_flux_indices = np.array(normalized_flux_indices)

                    normalized_flux = np.nan * np.ones((N, P), dtype=float)
                    normalized_flux[normalized_flux_indices] = _normalized_flux

                    continuum = flux / normalized_flux
            else:
                continuum = np.ones_like(flux)
                normalized_flux = flux

        else:
            if any(missing_names):
                raise RuntimeError(f"Missing names and FERRE version is not v4.8.9: {missing_names}")
            try:
                path = os.path.join(dir, control_kwds["OFFILE"])
                model_flux = np.atleast_2d(np.loadtxt(path))
            except:
                log.exception(f"Failed to load model flux from {path}")
                raise

            if "SFFILE" in control_kwds:
                try:
                    path = os.path.join(dir, control_kwds["SFFILE"])
                    normalized_flux = np.atleast_2d(np.loadtxt(path))
                except:
                    log.exception(f"Failed to load normalized observed flux from {path}")
                    raise
                else:
                    continuum = flux / normalized_flux
            else:
                continuum = np.ones_like(flux)
                normalized_flux = flux

        has_complete_results = (
            np.any(np.isfinite(params), axis=1)
        *   np.any(np.isfinite(model_flux), axis=1)
        )
        # If we only have some things (eg params but no model flux) we should make it all nan,
        # ebcause we dont want to rely on this downstream
        params[~has_complete_results] = np.nan
        model_flux[~has_complete_results] = np.nan
        normalized_flux[~has_complete_results] = np.nan
        continuum[~has_complete_results] = np.nan
        
        headers, *segment_headers = utils.read_ferre_headers(
            utils.expand_path(self.header_path)
        )
        parameter_names = utils.sanitise(headers["LABEL"])

        # Flag things.
        param_bitmask = bitmask.ParamBitMask()
        param_bitmask_flags = np.zeros(params.shape, dtype=np.int64)

        bad_lower = headers["LLIMITS"] + headers["STEPS"] / 8
        bad_upper = headers["ULIMITS"] - headers["STEPS"] / 8
        param_bitmask_flags[
            (params < bad_lower) | (params > bad_upper)
        ] |= param_bitmask.get_value("GRIDEDGE_BAD")

        warn_lower = headers["LLIMITS"] + headers["STEPS"]
        warn_upper = headers["ULIMITS"] - headers["STEPS"]
        param_bitmask_flags[
            (params < warn_lower) | (params > warn_upper)
        ] |= param_bitmask.get_value("GRIDEDGE_WARN")
        param_bitmask_flags[
            (params == -999) | (param_errs < -0.01) | ~np.isfinite(params)
        ] |= param_bitmask.get_value("FERRE_FAIL")

        # Check for any erroneous outputs
        if np.any(param_bitmask_flags & param_bitmask.get_value("FERRE_FAIL")):
            v = param_bitmask_flags & param_bitmask.get_value("FERRE_FAIL")
            idx = np.where(
                np.any(
                    param_bitmask_flags & param_bitmask.get_value("FERRE_FAIL"), axis=1
                )
            )
            log.warning(f"FERRE returned all erroneous values for an entry: {idx} {v}")

        model_wavelengths = tuple(map(utils.wavelength_array, segment_headers))
        label_results = {}
        spectral_results = {}
        for z, (name, param, param_err, bitmask_flag) in enumerate(
            zip(input_names, params, param_errs, param_bitmask_flags)
        ):
            parsed = self.from_name(name)

            result = OrderedDict(zip(reversed(parameter_names), reversed(param)))
            result.update(dict(zip([f"e_{pn}" for pn in reversed(parameter_names)], reversed(param_err))))
            result.update(
                dict(zip([f"bitmask_{pn}" for pn in reversed(parameter_names)], reversed(bitmask_flag)))
            )
            result.update(
                dict(
                    log_chisq_fit=log_chisq_fit[z],#meta["log_chisq_fit"][z],
                    log_snr_sq=log_snr_sq[z], #meta["log_snr_sq"][z],
                    frac_phot_data_points=frac_phot_data_points[z],#meta["frac_phot_data_points"][z],
                    snr=parsed["snr"],
                )
            )

            i, j, k = (int(parsed[_]) for _ in "ijk")

            label_results.setdefault((i, j, k), [])
            label_results[(i, j, k)].append(result)
            spectral_results.setdefault((i, j, k), [])
            
            # TODO: These need to be resampled to the observed pixels!
            spectral_results[(i, j, k)].append(dict(
                model_flux=model_flux[z],
                continuum=continuum[z],
                # FERRE_flux is what we actually gave to FERRE. Store it here just in case?
                ferre_flux=flux[z],
                e_ferre_flux=flux_sigma[z],
            ))
        
        # Create outputs in the database.
        failed_status = Status.get(description="failed-post-execution")
        failed_task_ids = []
        for i, (task, (data_product, ), parameters) in enumerate(self.iterable()):
            hdu_results = {}
            task_results = []
            header_groups = {}
            write_data_products = True
            for k, spectrum in enumerate(SpectrumList.read(data_product.path, data_slice=parameters["data_slice"])):
                if not spectrum_overlaps(spectrum, np.hstack(model_wavelengths)):
                    continue
                
                index = (i, 0, k)
                N, P = spectrum.flux.shape

                extname = get_extname(spectrum, data_product)

                # TODO: Put in the initial parameters?
                hdu_result = list_to_dict(label_results[index])
                # If FERRE failed entirely, mark this task as failed.
                if not np.all(np.isfinite(hdu_result["log_chisq_fit"])):
                    log.warning(f"FERRE failed for {task} {data_product}")
                    task.status = failed_status
                    task.save()
                    write_data_products = False
                    t = Task.get(id=task.id)
                    print(t, t.status)
                    failed_task_ids.append(task.id)
                    break

                # TODO: Check above works correctly for visits
                if N > 1:
                    raise a
            
                spectral_results_ = list_to_dict(spectral_results[index])
                mask = _get_ferre_mask(spectrum.wavelength.value, model_wavelengths)
                spectral_results_ = _de_mask_values(spectral_results_, mask)

                # TODO: Store this in a meta file instead of doing it in pre_ and post_??
                if parameters["continuum_method"] is not None:
                    f_continuum = executable(parameters["continuum_method"])(**parameters["continuum_kwargs"])
                    f_continuum.fit(spectrum)
                    pre_continuum = f_continuum(spectrum)
                else:
                    pre_continuum = 1                     

                spectral_results_["continuum"] *= pre_continuum
                spectral_results_["model_flux"] *= spectral_results_["continuum"]

                hdu_result.update(spectral_results_)
                hdu_results[extname] = hdu_result
                header_groups[extname] = [
                    ("TEFF", "STELLAR LABELS"),
                    ("BITMASK_TEFF", "BITMASK FLAGS"),
                    ("LOG_CHISQ_FIT", "SUMMARY STATISTICS"),
                    ("MODEL_FLUX", "MODEL SPECTRA")
                ]

                # Update task results to include data product ID and source ID.
                source_id = spectrum.meta.get("CAT_ID", None)
                parent_data_product_id = spectrum.meta.get("DATA_PRODUCT_ID", None)
                if not parent_data_product_id:
                    parent_data_product_id = data_product.id
                
                data_product_results = []
                for label_result in label_results[index]:
                    result = label_result.copy()
                    result.update(
                        source_id=source_id,
                        parent_data_product_id=parent_data_product_id                    
                    )          
                    data_product_results.append(result)

                task_results.extend(data_product_results)
            
            if write_data_products:        
                create_pipeline_product(task, data_product, hdu_results, header_groups=header_groups)
                task.create_or_update_outputs(FerreOutput, task_results)
        
        recursion_level = getattr(self, "__recursion_level__", 0)
        if failed_task_ids and recursion_level < 5 and len(failed_task_ids) > self.n_threads:
            log.info(f"Creating a new bundle for {len(failed_task_ids)} failed tasks at recursion level {recursion_level}")

            sub_bundle = Bundle.create()
            for task_id in failed_task_ids[::-1]:
                TaskBundle.create(task_id=task_id, bundle_id=sub_bundle.id)
            
            log.info(f"Sub-bundle is {sub_bundle}")
            sbi = Bundle.get(sub_bundle.id).instance()
            sbi.__recursion_level__ = recursion_level + 1
            sbi.execute()
            log.info(f"Sub-bundle done or failed?")


        return None


def _get_ferre_mask(observed_wavelength, model_wavelengths):
    P = observed_wavelength.size
    mask = np.zeros(P, dtype=bool)
    for model_wavelength in model_wavelengths:
        s_index, e_index = observed_wavelength.searchsorted(model_wavelength[[0, -1]])
        if (e_index - s_index) != model_wavelength.size:
            log.warn(f"Model wavelength grid does not precisely match data product ({e_index - s_index} vs {model_wavelength.size} on {model_wavelength[[0, -1]]})")
            e_index = s_index + model_wavelength.size
        mask[s_index:e_index] = True
    return mask


def _de_mask_values(spectral_dict, mask, fill_value=np.nan):
    P = mask.size
    updated = {}
    for k, v in spectral_dict.items():
        N, O = np.atleast_2d(v).shape
        updated_v = fill_value * np.ones((N, P))
        updated_v[:, mask] = np.array(v)
        updated[k] = updated_v
    return updated