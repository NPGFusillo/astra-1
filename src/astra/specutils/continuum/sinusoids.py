"""Represent the stellar continuum with sine and cosine functions."""

from __future__ import annotations
import numpy as np
from typing import Optional, Union, Tuple, List
from astropy.nddata import InverseVariance
from astra.tools.spectrum import SpectralAxis, Spectrum1D
from astra.tools.continuum.base import Continuum, _pixel_slice_and_mask
from astra.utils import log

class Sinusoids(Continuum):

    """Represent the stellar continuum with sine and cosine functions."""

    def __init__(
        self,
        deg: Optional[int] = 3,
        L: Optional[float] = 1400,
        scalar: Optional[float] = 1e-6,
        spectral_axis: Optional[SpectralAxis] = None,
        regions: Optional[List[Tuple[float, float]]] = None,
        mask: Optional[np.array] = None,
        fill_value: Optional[Union[int, float]] = np.nan,
        **kwargs,
    ) -> None:
        (
            """
        :param deg: [optional]
            The degree of sinusoids to include.

        :param L: [optional]
            The length scale for the sines and cosines.
        """
            + Continuum.__init__.__doc__
        )
        super(Sinusoids, self).__init__(
            spectral_axis=spectral_axis,
            regions=regions,
            mask=mask,
            fill_value=fill_value,
            **kwargs,
        )
        self.deg = int(deg)
        self.L = float(L)
        self.scalar = float(scalar)
        return None

    def fit(self, spectrum: Spectrum1D) -> Sinusoids:
        _initialized_args = self._initialize(spectrum)
        N, P, *_ = _initialized_args
        all_flux = spectrum.flux.value.reshape((N, P))
        all_ivar = spectrum.uncertainty.represent_as(InverseVariance).array.reshape(
            (N, P)
        )
        self.theta = self._fit(all_flux, all_ivar, _initialized_args)

        return self


    def _fit(self, flux, ivar, _initialized_args):
        N, P, *region_args = _initialized_args

        theta = np.empty((N, self.num_regions, 2 * self.deg + 1))
        for i, (flux_, ivar_) in enumerate(zip(flux, ivar)):
            for j, (_, indices, _, M_continuum) in enumerate(zip(*region_args)):
                MTM = M_continuum @ (ivar_[indices][:, None] * M_continuum.T)
                MTy = M_continuum @ (ivar_[indices] * flux_[indices]).T

                eigenvalues = np.linalg.eigvalsh(MTM)
                MTM[np.diag_indices(len(MTM))] += self.scalar * np.max(eigenvalues)
                # eigenvalues = np.linalg.eigvalsh(MTM)
                # condition_number = max(eigenvalues) / min(eigenvalues)
                # TODO: warn on high condition number
                if np.all(ivar_[indices] == 0):
                    log.warning(f"Region {j} is empty. Setting theta to zero.")
                    theta[i, j] = 0.0
                else:
                    theta[i, j] = np.linalg.solve(MTM, MTy)
        return theta


    def _evaluate(self, theta, initialized_args):
        
        N, P, *region_args = initialized_args
        continuum = self.fill_value * np.ones((N, P))
        for i in range(N):
            for j, ((lower, upper), _, M_region, _) in enumerate(zip(*region_args)):
                continuum[i, slice(lower, upper)] = M_region.T @ theta[i, j]
        return continuum


    def __call__(
        self, spectrum: Spectrum1D, theta: Optional[Union[List, np.array, Tuple]] = None, **kwargs
    ) -> np.ndarray:
        if theta is None:
            theta = self.theta

        _initialized_args = self._initialize(spectrum)

        return self._evaluate(theta, _initialized_args)


    def _initialize(self, spectrum: Spectrum1D):
        try:
            self._initialized_args
        except AttributeError:
            N, P = self._get_shape(spectrum)

            region_slices, region_continuum_indices = _pixel_slice_and_mask(
                spectrum.wavelength, self.regions, self.mask
            )
    
            # Create the design matrices.
            M_region = []
            M_continuum = []
            for (lower, upper), indices in zip(region_slices, region_continuum_indices):
                region_pixels = spectrum.wavelength.value[slice(lower, upper)]
                region_continuum = spectrum.wavelength.value[indices]
                M_region.append(self._design_matrix(region_pixels))
                M_continuum.append(self._design_matrix(region_continuum))
            self._initialized_args = (
                N,
                P,
                region_slices,
                region_continuum_indices,
                M_region,
                M_continuum,
            )
        else:
            # If we already have initialized arguments, we just need to update the shape.
            N, P = self._get_shape(spectrum)
            _N, _P, *region_args = self._initialized_args
            self._initialized_args = (N, P, *region_args)

        finally:
            return self._initialized_args

    def _design_matrix(self, dispersion: np.array) -> np.array:
        scale = 2 * (np.pi / self.L)
        return np.vstack(
            [
                np.ones_like(dispersion).reshape((1, -1)),
                np.array(
                    [
                        [np.cos(o * scale * dispersion), np.sin(o * scale * dispersion)]
                        for o in range(1, self.deg + 1)
                    ]
                ).reshape((2 * self.deg, dispersion.size)),
            ]
        )
