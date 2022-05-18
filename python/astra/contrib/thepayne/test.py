# encoding: utf-8


from __future__ import (absolute_import, division, print_function, unicode_literals)

import numpy as np
import sys
import os
from tqdm import trange
import pickle

from astropy.table import Table
from astropy.constants import c
from scipy.optimize import curve_fit
from collections import OrderedDict

from astra.utils import log


LARGE = 1e3

c = c.to("km/s").value

sigmoid = lambda z: 1.0/(1.0 + np.exp(-z))


def _predict_stellar_spectrum(unscaled_labels, weights, biases):

    # This is making extremely strong assumptions about the neural network architecture!
    inside = np.einsum("ij,j->i", weights[0], unscaled_labels) + biases[0]
    outside = np.einsum("ij,j->i", weights[1], sigmoid(inside)) + biases[1]
    spectrum = np.einsum("ij,j->i", weights[2], sigmoid(outside)) + biases[2]
    return spectrum


# TODO: use a specutils.Spectrum1D method.
def _redshift(dispersion, flux, radial_velocity):
    f = np.sqrt((1 - radial_velocity/c)/(1 + radial_velocity/c))
    new_dispersion = f * dispersion 
    return np.interp(new_dispersion, dispersion, flux)


def load_state(path):
    with open(path, "rb") as fp:
        contents = pickle.load(fp)

    state = contents["state"]

    N = len(state["model_state"])
    biases = [state["model_state"][f"{i}.bias"].data.cpu().numpy() for i in (0, 2, 4)]
    weights = [state["model_state"][f"{i}.weight"].data.cpu().numpy() for i in (0, 2, 4)]
    scales = state["scales"]

    return dict(
        neural_network_coefficients=(weights, biases), 
        scales=scales,
        model_wavelength=contents["wavelength"],
        label_names=contents["label_names"]
    )

def load_apogee_mask(model_path):
    '''
    read in the pixel mask with which we will omit bad pixels during spectral fitting
    The mask is made by comparing the tuned Kurucz models to the observed spectra from Arcturus
    and the Sun from APOGEE. We mask out pixels that show more than 2% of deviations.
    '''
    #path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'other_data/apogee_mask.npz')
    path = os.path.join(os.path.dirname(model_path),'apogee_mask.npz')
    tmp = np.load(path)
    mask = tmp['apogee_mask']
    tmp.close()
    return mask



def test(
        wavelength,
        flux,
        ivar,
        mask, 
        neural_network_coefficients, 
        scales, 
        model_wavelength, 
        label_names, 
        initial_labels=None, 
        radial_velocity_tolerance=None, 
        **kwargs
    ):
    r"""
    Use a pre-trained neural network to estimate the stellar labels for the given spectrum.

    :param wavelength:
        The wavelength array of the observed spectrum.
    
    :param flux:
        The observed (or pseudo-continuum-normalised) fluxes.
        
    :param ivar:
        The inverse variances of the fluxes.

    :param neural_network_coefficients:
        A two-length tuple containing the weights of the neural network, and the biases.
    
    :param scales:
        The lower and upper scaling value used for the labels.

    :param initial_labels: [optional]
        The initial labels to optimize from. By default this will be set at the center of the
        training set labels.

    :param radial_velocity_tolerance: [optional]
        Supply a radial velocity tolerance to fit simulatenously with stellar parameters. If `None`
        is given then no radial velocity will be fit. If a float/integer is given then any radial
        velocity +/- that value will be considered. Alternatively, a (lower, upper) bound can be
        given.

    :returns:
        A three-length tuple containing the optimized parameters, the covariance matrix, and a
        metadata dictionary.
    """

    weights, biases = neural_network_coefficients
    K = L = weights[0].shape[1] # number of label names

    fit_radial_velocity = radial_velocity_tolerance is not None
    if fit_radial_velocity:
        L += 1

    if initial_labels is None:
        initial_labels = np.zeros(L)

    # Set bounds.
    bounds = np.zeros((2, L))
    bounds[0, :] = -0.5
    bounds[1, :] = +0.5
    if fit_radial_velocity:
        if isinstance(radial_velocity_tolerance, (int, float)):
            bounds[:, -1] = [
                -abs(radial_velocity_tolerance),
                +abs(radial_velocity_tolerance)
            ]

        else:
            bounds[:, -1] = radial_velocity_tolerance
    
    N, P = flux.shape

    p_opts = np.nan * np.ones((N, L))
    p_covs = np.nan * np.ones((N, L, L))
    model_fluxes = np.nan * np.ones((N, P))
    meta = []

    x_min, x_max = scales

    # Define objective function.
    def objective_function(x, *labels):
        y_pred = _predict_stellar_spectrum(labels[:K], weights, biases)
        if fit_radial_velocity:
            # Here we are shifting the *observed* spectra. That's not the Right Thing to do, but it
            # probably doesn't matter here.
            y_pred = _redshift(x, y_pred, labels[-1])
        return y_pred

    for i in range(N):
        y_original = flux[i].reshape(wavelength.shape)
        # TODO: Assuming an inverse variance array (likely true).
        y_err_original = ivar[i].reshape(wavelength.shape)**-0.5

        # Interpolate data onto model -- not The Right Thing to do!
        y = np.interp(model_wavelength, wavelength, y_original) 
        y_err = np.interp(model_wavelength, wavelength, y_err_original)

        # Fix non-finite pixels and error values.
        non_finite = ~np.isfinite(y * y_err)
        y[non_finite] = 1
        y_err[non_finite] = LARGE

        # set infinity uncertainty to pixels that we want to omit
        y_err[mask] = LARGE

        kwds = kwargs.copy()
        kwds.update(
            xdata=model_wavelength, 
            ydata=y, 
            sigma=y_err, 
            p0=initial_labels, 
            bounds=bounds, 
            absolute_sigma=True, 
            method="trf"
        )

        try:
            p_opt, p_cov = curve_fit(objective_function, **kwds)

        except ValueError:
            log.exception(f"Error occurred fitting spectrum {i}:")
            meta.append(dict(
                chi_sq=np.nan,
                r_chi_sq=np.nan
            ))

        else:
            y_pred = objective_function(model_wavelength, *p_opt)
            
            # Calculate summary statistics.
            chi_sq, r_chi_sq = get_chi_sq(y_pred, y, y_err, L)

            p_opts[i, :] = (x_max - x_min) * (p_opt + 0.5) + x_min
            # TODO: YST does this but I am not yet convinced that it is correct!
            p_covs[i, :, :] = p_cov * (x_max - x_min)
            model_fluxes[i, :] = np.interp(
                wavelength,
                model_wavelength,
                y_pred,
            )

            meta.append(dict(
                chi_sq=chi_sq,
                r_chi_sq=r_chi_sq
            ))    
    
    return (p_opts, p_covs, model_fluxes, meta)



def get_chi_sq(expectation, y, y_err, L):
    P = np.sum(np.isfinite(y * y_err) * (y_err < LARGE))
    chi_sq = np.nansum(((y - expectation)/y_err)**2)
    r_chi_sq = chi_sq / (P - L - 1)
    return (chi_sq, r_chi_sq)
