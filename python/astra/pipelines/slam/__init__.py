import numpy as np
from scipy.interpolate import interp1d
from functools import cache
from typing import Iterable, Optional
from peewee import JOIN
from joblib import load
import pickle
import os
import concurrent.futures
from tqdm import tqdm


from astra import task, __version__
from astra.utils import log, expand_path
from astra.pipelines.slam.slam.normalization import normalize_spectra_block
from astra.models import Spectrum
from astra.models.slam import Slam
from astra.models.spectrum import SpectrumMixin
from astra.models.boss import BossVisitSpectrum
from astra.models.mwm import BossCombinedSpectrum
from astra.models.source import Source
from astra.models.spectrum import SpectrumMixin
from astra.models.slam import Slam
from peewee import fn, ModelSelect

q = (
    BossCombinedSpectrum
    .select()
    .join(Source)
    .switch(BossCombinedSpectrum)
    .join(
        Slam, 
        JOIN.LEFT_OUTER, 
        on=(
            (Slam.spectrum_pk == BossCombinedSpectrum.spectrum_pk)
        &   (Slam.v_astra == __version__)
        )
    )
    .where(
        (                
            (
                # From Zach Way, mwm-astra 413
                Source.g_mag.is_null(False)
            &   Source.rp_mag.is_null(False)
            &   Source.plx.is_null(False)
            &   (Source.plx > 0)
            &   ((Source.g_mag - Source.rp_mag) > 0.56)
            &   ((Source.g_mag + 5 + 5 * fn.log10(Source.plx/1000)) > 5.553)
            )
        |   (
            Source.assigned_to_program("mwm_yso")
        |   Source.assigned_to_program("mwm_snc")
        )
    )
    &   (BossCombinedSpectrum.v_astra == __version__)
    )    
)

@task
def slam(
    spectra: Optional[Iterable[SpectrumMixin]] = (
        BossCombinedSpectrum
        .select()
        .join(Source)
        .switch(BossCombinedSpectrum)
        .join(
            Slam, 
            JOIN.LEFT_OUTER, 
            on=(
                (Slam.spectrum_pk == BossCombinedSpectrum.spectrum_pk)
            &   (Slam.v_astra == __version__)
            )
        )
        .where(
            Slam.spectrum_pk.is_null()
        &   (                
                (
                    # From Zach Way, mwm-astra 413
                    Source.g_mag.is_null(False)
                &   Source.rp_mag.is_null(False)
                &   Source.plx.is_null(False)
                &   (Source.plx > 0)
                &   ((Source.g_mag - Source.rp_mag) > 0.56)
                &   ((Source.g_mag + 5 + 5 * fn.log10(Source.plx/1000)) > 5.553)
                )
            |   (
                Source.assigned_to_program("mwm_yso")
            |   Source.assigned_to_program("mwm_snc")
            )
        )
        &   (BossCombinedSpectrum.v_astra == __version__)
        )
    ),
    #model_path: str = "$MWM_ASTRA/pipelines/slam/ASPCAP_DR16_astra_wbinaryValid.dump",
    model_path: str = "$MWM_ASTRA/pipelines/slam/Train_FGK_LAMOST_M_BOSS_alpha_from_ASPCAP_teff_logg_from_ApogeeNet_nobinaries.dump",
    max_workers: Optional[int] = None,
    page=None,
    limit=None,
) -> Iterable[Slam]:
    """
    Run the Stellar Labels Machine (SLAM) on the given spectra.
    """
    
    model = load_model(model_path)

    if isinstance(spectra, ModelSelect):
        spectra = (
            spectra
            .where(
                (                
                    (
                        # From Zach Way, mwm-astra 413
                        Source.g_mag.is_null(False)
                    &   Source.rp_mag.is_null(False)
                    &   Source.plx.is_null(False)
                    &   (Source.plx > 0)
                    &   ((Source.g_mag - Source.rp_mag) > 0.56)
                    &   ((Source.g_mag + 5 + 5 * fn.log10(Source.plx/1000)) > 5.553)
                    )
                |   (
                    Source.assigned_to_program("mwm_yso")
                |   Source.assigned_to_program("mwm_snc")
                    )
                )                
            )
        )

        if page is not None and limit is not None:
            spectra = spectra.paginate(page, limit)
        
        elif limit is not None:
            spectra = spectra.limit(limit)

    executor = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)

    futures = []
    for spectrum in tqdm(spectra, total=0, desc="Distributing"):
        '''
        try:
            args = (spectrum.source_pk, spectrum.spectrum_pk, spectrum.wavelength, np.atleast_2d(spectrum.flux), np.atleast_2d(spectrum.ivar), model)
        except:
            None
        else:
            futures.append(executor.submit(_slam, *args))
        '''
        futures.append(executor.submit(_slam, spectrum.source_pk, spectrum.spectrum_pk, model))

    with tqdm(total=len(futures), desc="Slamming") as pb:
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            if r is not None:
                yield r
            pb.update()
            


@cache
def load_model(model_path):
    # We have to put this path in otherwise slam wont load. fuck my life.
    import sys
    sys.path.insert(0, "/uufs/chpc.utah.edu/common/home/u6020307/astra/python/astra/pipelines/slam")
    model = load(expand_path(model_path))
    sys.path.pop(0)
    return model


def _slam(
    source_pk,
    spectrum_pk, 
    model,
    dwave: float = 10.0,
    p_min: float = 1e-8,
    p_max: float = 1e-7,
    q: float = 0.7,
    eps: float = 1e-19,
    rsv_frac: float = 2,
    n_jobs: int = 1,
    verbose: int = 0,
):
    spectrum = Spectrum.get(spectrum_pk).resolve()

    try:
        wave = spectrum.wavelength
        fluxs = np.atleast_2d(spectrum.flux)
        ivars = np.atleast_2d(spectrum.ivar)
    except:
        return None

    N, P = fluxs.shape
    R = model.wave.size

    flux_resamp = np.empty((N, R))
    ivar_resamp = np.empty((N, R))
    assert N == 1
    for i in range(N):
        # Note: One non-finite value given to scipy.interpolate.interp1d will cause the
        #       entire interpolated output to be NaN. This is a known issue.
        non_finite = ~np.isfinite(fluxs[i]) + ~np.isfinite(ivars[i])
        _flux = np.copy(fluxs[i])
        _flux[non_finite] = 0.0
        _ivar = np.copy(ivars[i])
        _ivar[non_finite] = 0.0

        f = interp1d(wave, _flux, kind="cubic", bounds_error=None, fill_value=np.nan)
        g = interp1d(wave, _ivar, kind="cubic", bounds_error=None, fill_value=0)
        flux_resamp[i] = f(model.wave)
        ivar_resamp[i] = g(model.wave)

    flux_norm, flux_cont = normalize_spectra_block(
        model.wave,
        flux_resamp,
        #(6147.0, 8910.0),
        (6001.755, 8957.321),
        dwave=dwave,
        p=(p_min, p_max),
        q=q,
        ivar_block=ivar_resamp,
        eps=eps,
        rsv_frac=rsv_frac,
        n_jobs=n_jobs,
        verbose=verbose,
    )
    
    flux_norm[flux_norm > 2] = 1
    flux_norm[flux_norm < 0] = 0

    ivar_norm = flux_cont**2 * ivar_resamp

    ### Initial estimation: get initial estimate of parameters by chi2 best match
    label_init = model.predict_labels_quick(
        flux_norm, ivar_norm, n_jobs=1
    )

    ### SLAM prediction: optimize parameters
    results_pred = model.predict_labels_multi(
        label_init, flux_norm, ivar_norm
    )
    #label_pre[:,0] is the [Fe/H] calibrated from Niu et al.2023.
    #label_pre[:,1] is the [Fe/H] calibrated directly from LAMOST FGK primary stars.
    #label_pre[:,2] is the [alpha/M].
    #label_pre[:,3] is the Teff.
    #label_pre[:,4] is the logg.    
    label_names = ("fe_h_niu", "fe_h", "alpha_fe", "teff", "logg")
    labels = np.array([label["x"] for label in results_pred])

    kwargs = (dict(zip(label_names, labels[0])))
    kwargs.update(
        dict(zip(
            [f"e_{ln}" for ln in label_names],
            np.array([label["pstd"] for label in results_pred])[0]
        ))
    )

    # Add initial values.
    kwargs.update(
        dict(
            zip(
                [f"initial_{ln}" for ln in label_names],
                label_init[0]
            )
        )
    )

    # Add correlation coefficients.
    L = len(label_names)
    j, k = np.triu_indices(L, 1)
    rho = np.array([np.corrcoef(label["pcov"]) for label in results_pred])
    kwargs.update(
        dict(
            zip(
                [f"rho_{label_names[j]}_{label_names[k]}" for j, k in zip(j, k)],
                rho[0, j, k]
            )
        )
    )
    kwargs.update(
        dict(
            zip(
                [f"rho_{label_names[j]}_{label_names[k]}" for j, k in zip(k, j)],
                rho[0, j, k]
            )
        )
    )    

    # Add optimisation keywords
    opt_keys = ("status", "success", "optimality")
    for key in opt_keys:
        kwargs[key] = results_pred[0][key]

    # Add statistics.
    prediction = model.predict_spectra(labels)
    chi2 = np.sum((prediction - flux_norm) ** 2 * ivar_norm)
    R_finite = np.sum(ivar_norm > 0)
    rchi2 = chi2 / (R_finite - L - 1)
    
    # Flags
    flag_teff_outside_bounds = (kwargs["teff"] < 2800 or kwargs["teff"] > 4500)    
    flag_fe_h_outside_bounds = (kwargs['fe_h'] < -1 or kwargs['fe_h'] > 0.5)
    flag_bad_optimizer_status = (kwargs["status"] > 0 and kwargs["status"] != 2) | (kwargs["status"] < 0)
    
    
    kwargs.update(
        chi2=chi2,
        rchi2=rchi2,
        flag_teff_outside_bounds=flag_teff_outside_bounds,
        flag_fe_h_outside_bounds=flag_fe_h_outside_bounds,
        flag_bad_optimizer_status=flag_bad_optimizer_status,
        #warn_flag=warn_flag,
        #bad_flag=bad_flag,
    )

    # Prepare model spectrum for final product.
    model_continuum = flux_resamp / flux_norm

    resampled_continuum = np.nan * np.ones((N, P))
    resampled_rectified_model_flux = np.nan * np.ones((N, P))
    if not np.all(np.isfinite(prediction)):
        log.warning(f"Prediction values not all finite!")
    if not np.all(np.isfinite(model_continuum[i])):
        log.warning(f"Not all model continuum values finite!")

    i = 0

    finite_prediction = np.isfinite(prediction[i])
    finite_model_continuum = np.isfinite(model_continuum[i])
    if any(finite_prediction):

        f = interp1d(
            model.wave[finite_prediction], 
            prediction[i][finite_prediction], 
            kind="cubic", 
            bounds_error=False, 
            fill_value=np.nan
        )
        resampled_rectified_model_flux[i] = f(wave)

    if any(finite_model_continuum): 
        c = interp1d(
            model.wave[finite_model_continuum], 
            model_continuum[i][finite_model_continuum], 
            kind="cubic", 
            bounds_error=False, 
            fill_value=np.nan
        )

        # Re-sample the predicted spectra back to the observed frame.
        resampled_continuum[i] = c(wave)

    result = Slam(
        spectrum_pk=spectrum_pk,
        source_pk=source_pk,
        **kwargs
    )

    path = expand_path(result.intermediate_output_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fp:
        pickle.dump((resampled_continuum, resampled_rectified_model_flux), fp)
        
    return result



