"""Tests for astra.specutils subpackage."""

import os
os.environ["ASTRA_DATABASE_PATH"] = ":memory:"

import numpy as np
import pytest
from scipy import sparse


# ---------------------------------------------------------------------------
# lsf.py tests
# ---------------------------------------------------------------------------
from astra.specutils.lsf import (
    lsf_sigma,
    lsf_sigma_and_bounds,
    instrument_lsf_kernel,
    instrument_lsf_dense_matrix,
    instrument_lsf_sparse_matrix,
    rotational_broadening_sparse_matrix,
    _fwhm_to_sigma,
)


class TestLsfSigma:

    def test_basic(self):
        # sigma = (lambda / R) * fwhm_to_sigma
        result = lsf_sigma(5000.0, 10000)
        expected = (5000.0 / 10000) * _fwhm_to_sigma
        assert result == pytest.approx(expected)

    def test_proportional_to_wavelength(self):
        s1 = lsf_sigma(5000.0, 10000)
        s2 = lsf_sigma(10000.0, 10000)
        assert s2 == pytest.approx(2 * s1)

    def test_inversely_proportional_to_R(self):
        s1 = lsf_sigma(5000.0, 10000)
        s2 = lsf_sigma(5000.0, 20000)
        assert s1 == pytest.approx(2 * s2)


class TestLsfSigmaAndBounds:

    def test_default_window(self):
        sigma, (lower, upper) = lsf_sigma_and_bounds(5000.0, 10000)
        expected_sigma = lsf_sigma(5000.0, 10000)
        assert sigma == pytest.approx(expected_sigma)
        assert lower == pytest.approx(5000.0 - 5 * expected_sigma)
        assert upper == pytest.approx(5000.0 + 5 * expected_sigma)

    def test_custom_window(self):
        sigma, (lower, upper) = lsf_sigma_and_bounds(5000.0, 10000, 3)
        assert lower == pytest.approx(5000.0 - 3 * sigma)
        assert upper == pytest.approx(5000.0 + 3 * sigma)


class TestInstrumentLsfKernel:

    def test_kernel_is_normalised(self):
        wavelength = np.linspace(4900, 5100, 1000)
        mask, kernel = instrument_lsf_kernel(wavelength, 5000.0, 10000)
        assert kernel.sum() == pytest.approx(1.0, abs=1e-10)

    def test_kernel_centered_on_lambda(self):
        wavelength = np.linspace(4900, 5100, 1000)
        mask, kernel = instrument_lsf_kernel(wavelength, 5000.0, 10000)
        # Peak should be near the centre wavelength
        peak_idx = np.argmax(kernel)
        peak_wavelength = wavelength[mask][peak_idx]
        assert peak_wavelength == pytest.approx(5000.0, abs=1.0)

    def test_mask_bounds(self):
        wavelength = np.linspace(4000, 6000, 5000)
        mask, kernel = instrument_lsf_kernel(wavelength, 5000.0, 10000)
        _, (lower, upper) = lsf_sigma_and_bounds(5000.0, 10000)
        masked_wl = wavelength[mask]
        assert masked_wl.min() >= lower - 1
        assert masked_wl.max() <= upper + 1


class TestInstrumentLsfDenseMatrix:

    def test_shape(self):
        wl_in = np.linspace(4900, 5100, 200)
        wl_out = np.linspace(4950, 5050, 50)
        K = instrument_lsf_dense_matrix(wl_in, wl_out, 10000)
        assert K.shape == (wl_in.size, wl_out.size)

    def test_nonzero_entries_exist(self):
        # The dense matrix uses np.empty and only fills where the kernel contributes,
        # so we just verify the non-garbage entries are sensible.
        wl_in = np.linspace(4900, 5100, 500)
        wl_out = np.array([5000.0])
        K = instrument_lsf_dense_matrix(wl_in, wl_out, 10000)
        # The column for the single output pixel should have a kernel that sums to ~1
        col = K[:, 0]
        # Find the kernel entries by checking which were actually set (matching the mask)
        mask, phi = instrument_lsf_kernel(wl_in, 5000.0, 10000)
        np.testing.assert_allclose(col[mask], phi, atol=1e-12)


class TestInstrumentLsfSparseMatrix:

    def test_sparse_is_sparse(self):
        wl_in = np.linspace(4900, 5100, 200)
        wl_out = np.linspace(4950, 5050, 30)
        K_sparse = instrument_lsf_sparse_matrix(wl_in, wl_out, 10000)
        assert sparse.issparse(K_sparse)
        assert K_sparse.shape == (wl_in.size, wl_out.size)

    def test_sparse_kernel_per_output(self):
        # For each output wavelength, the sparse matrix should contain the same
        # kernel values as instrument_lsf_kernel
        wl_in = np.linspace(4900, 5100, 200)
        wl_out = np.array([5000.0, 5020.0])
        K_sparse = instrument_lsf_sparse_matrix(wl_in, wl_out, 10000)
        for o, wl_o in enumerate(wl_out):
            mask, phi = instrument_lsf_kernel(wl_in, wl_o, 10000)
            col = K_sparse[:, [o]].toarray().flatten()
            np.testing.assert_allclose(col[mask], phi, atol=1e-12)


class TestRotationalBroadening:

    def test_shape(self):
        wl = np.linspace(5000, 5100, 500)
        K = rotational_broadening_sparse_matrix(wl, 10.0, 0.6)
        assert K.shape == (wl.size, wl.size)

    def test_columns_normalised(self):
        wl = np.linspace(5000, 5100, 500)
        K = rotational_broadening_sparse_matrix(wl, 10.0, 0.6)
        col_sums = np.array(K.sum(axis=0)).flatten()
        # Interior columns should be ~1 (edges may differ due to truncation)
        interior = col_sums[50:-50]
        np.testing.assert_allclose(interior, 1.0, atol=1e-10)

    def test_flat_spectrum_unchanged(self):
        wl = np.linspace(5000, 5100, 500)
        flux = np.ones(wl.size)
        K = rotational_broadening_sparse_matrix(wl, 20.0, 0.6)
        result = K.T @ flux
        # Interior should remain ~1
        np.testing.assert_allclose(result[50:-50], 1.0, atol=1e-10)

    def test_zero_vsini_is_identity_like(self):
        # With very small vsini the kernel should approach identity
        wl = np.linspace(5000, 5100, 200)
        flux = np.sin(np.linspace(0, 4 * np.pi, 200))
        K = rotational_broadening_sparse_matrix(wl, 0.01, 0.6)
        result = K.T @ flux
        np.testing.assert_allclose(result[10:-10], flux[10:-10], atol=1e-3)


# ---------------------------------------------------------------------------
# resampling.py tests
# ---------------------------------------------------------------------------
from astra.specutils.resampling import (
    wave_to_pixel,
    sincint,
    design_matrix,
    separate_bitmasks,
    pixel_weighted_spectrum,
)


class TestWaveToPixel:

    def test_identity_mapping(self):
        # If the wavelength grid is linear, pixel positions should match indices
        wave0 = np.linspace(5000, 6000, 100)
        pixels = wave_to_pixel(wave0, wave0)
        np.testing.assert_allclose(pixels, np.arange(100), atol=0.1)

    def test_out_of_bounds_is_nan(self):
        wave0 = np.linspace(5000, 6000, 100)
        query = np.array([4000.0, 7000.0])
        pixels = wave_to_pixel(query, wave0)
        assert np.all(np.isnan(pixels))

    def test_interior_interpolation(self):
        # Use a wavelength grid that starts well above zero to avoid numerical issues
        # in the baseline polynomial fit
        wave0 = 10**(3.5 + 6e-6 * np.arange(1000))  # log-linear wavelength grid
        mid_idx = 500
        query = np.array([wave0[mid_idx]])
        pixels = wave_to_pixel(query, wave0)
        assert pixels[0] == pytest.approx(float(mid_idx), abs=1.0)


class TestSincint:

    def test_identity_at_integer_positions(self):
        # Requesting values at integer pixel positions should return the original values
        flux = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        x = np.arange(len(flux), dtype=float)
        nres = 2.0
        result = sincint(x, nres, [[flux, None]])
        resampled = result[0][0]
        np.testing.assert_allclose(resampled, flux, atol=0.1)

    def test_variance_propagation(self):
        flux = np.ones(20)
        var = 0.01 * np.ones(20)
        x = np.arange(20, dtype=float)
        result = sincint(x, 2.0, [[flux, var]])
        # Should return errors (sqrt of propagated variance)
        errors = result[0][1]
        assert np.all(errors > 0)
        assert np.all(np.isfinite(errors))


class TestDesignMatrix:

    def test_shape(self):
        xs = np.linspace(0, 10, 50)
        P = 7
        A = design_matrix(xs, P)
        assert A.shape == (50, P)

    def test_first_column_is_ones(self):
        xs = np.linspace(0, 10, 30)
        A = design_matrix(xs, P=5)
        np.testing.assert_allclose(A[:, 0], 1.0)

    def test_columns_are_trig(self):
        xs = np.linspace(0, 10, 50)
        L = np.max(xs) - np.min(xs)
        A = design_matrix(xs, P=5, L=L)
        # Column 1 should be sin(2 pi x / L)  (j=1, odd -> sin with j+1=2)
        expected = np.sin(np.pi * 2 * xs / L)
        np.testing.assert_allclose(A[:, 1], expected, atol=1e-12)
        # Column 2 should be cos(2 pi x / L)  (j=2, even -> cos with j=2)
        expected_cos = np.cos(np.pi * 2 * xs / L)
        np.testing.assert_allclose(A[:, 2], expected_cos, atol=1e-12)

    def test_default_P_equals_size(self):
        xs = np.linspace(0, 10, 20)
        A = design_matrix(xs)
        assert A.shape == (20, 20)


class TestSeparateBitmasks:

    def test_single_bit(self):
        bitmask = np.array([1, 0, 1, 0])
        result = separate_bitmasks([bitmask])
        assert 0 in result
        np.testing.assert_array_equal(result[0][0], [1.0, 0.0, 1.0, 0.0])

    def test_multiple_bits(self):
        # bit 0 = 1, bit 1 = 2
        bitmask = np.array([3, 2, 1, 0])
        result = separate_bitmasks([bitmask])
        np.testing.assert_array_equal(result[0][0], [1.0, 0.0, 1.0, 0.0])
        np.testing.assert_array_equal(result[1][0], [1.0, 1.0, 0.0, 0.0])


class TestPixelWeightedSpectrum:

    def test_single_visit(self):
        flux = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
        ivar = np.array([[1.0, 1.0, 1.0, 1.0, 1.0]])
        bitmask = np.array([[0, 0, 0, 0, 0]])
        stacked_flux, stacked_ivar, stacked_bitmask, continuum, meta = pixel_weighted_spectrum(flux, ivar, bitmask)
        np.testing.assert_allclose(stacked_flux, flux[0])
        np.testing.assert_allclose(stacked_ivar, ivar[0])

    def test_two_visits_equal_weight(self):
        flux = np.array([[2.0, 4.0], [4.0, 6.0]])
        ivar = np.array([[1.0, 1.0], [1.0, 1.0]])
        bitmask = np.array([[0, 0], [0, 0]])
        stacked_flux, stacked_ivar, stacked_bitmask, continuum, meta = pixel_weighted_spectrum(flux, ivar, bitmask)
        np.testing.assert_allclose(stacked_flux, [3.0, 5.0])
        np.testing.assert_allclose(stacked_ivar, [2.0, 2.0])

    def test_bitmask_or(self):
        flux = np.array([[1.0, 2.0], [3.0, 4.0]])
        ivar = np.array([[1.0, 1.0], [1.0, 1.0]])
        bitmask = np.array([[1, 0], [0, 2]])
        _, _, stacked_bitmask, _, _ = pixel_weighted_spectrum(flux, ivar, bitmask)
        np.testing.assert_array_equal(stacked_bitmask, [1, 2])

    def test_empty_flux(self):
        flux = np.array([]).reshape(0, 0)
        ivar = np.array([]).reshape(0, 0)
        bitmask = np.array([]).reshape(0, 0)
        result = pixel_weighted_spectrum(flux, ivar, bitmask)
        assert result[0] is None


# ---------------------------------------------------------------------------
# continuum/base.py tests
# ---------------------------------------------------------------------------
from astra.specutils.continuum.base import Continuum, _pixel_slice_and_mask


class TestPixelSliceAndMask:

    def test_no_regions_no_mask(self):
        wl = np.linspace(5000, 6000, 100)
        slices, masks = _pixel_slice_and_mask(wl, None, None)
        assert slices == [(0, 100)]
        assert len(masks) == 1
        np.testing.assert_array_equal(masks[0], np.arange(100))

    def test_with_regions(self):
        wl = np.linspace(5000, 6000, 100)
        regions = [(5200, 5400), (5600, 5800)]
        slices, masks = _pixel_slice_and_mask(wl, regions, None)
        assert len(slices) == 2
        assert len(masks) == 2
        # All pixels in each region should be included (no mask)
        for (lower, upper), m in zip(slices, masks):
            np.testing.assert_array_equal(m, np.arange(lower, upper))

    def test_with_boolean_mask(self):
        wl = np.linspace(5000, 6000, 100)
        mask = np.zeros(100, dtype=bool)
        mask[10:20] = True  # mask out pixels 10-19
        slices, masks = _pixel_slice_and_mask(wl, None, mask)
        assert 10 not in masks[0]
        assert 15 not in masks[0]
        assert 0 in masks[0]
        assert 50 in masks[0]


class TestContinuumBase:

    def test_num_regions_none(self):
        c = Continuum()
        assert c.num_regions == 1

    def test_num_regions_with_regions(self):
        c = Continuum(regions=[(5000, 5500), (5500, 6000)])
        assert c.num_regions == 2

    def test_fill_value_default(self):
        c = Continuum()
        assert np.isnan(c.fill_value)

    def test_fit_not_implemented(self):
        c = Continuum()
        with pytest.raises(NotImplementedError):
            c.fit(None)


# ---------------------------------------------------------------------------
# continuum/chebyshev.py tests
# ---------------------------------------------------------------------------
from astra.specutils.continuum.chebyshev import Chebyshev


class _FakeSpectrum:
    """Minimal spectrum-like object for testing Chebyshev.fit()."""
    def __init__(self, wavelength, flux, ivar=None):
        self.wavelength = np.asarray(wavelength)
        self.flux = np.asarray(flux)
        if ivar is None:
            self.ivar = np.ones_like(self.flux)
        else:
            self.ivar = np.asarray(ivar)


class TestChebyshevContinuum:

    def test_fit_constant_spectrum(self):
        wl = np.linspace(5000, 6000, 200)
        flux = 5.0 * np.ones(200)
        spec = _FakeSpectrum(wl, flux)
        cheb = Chebyshev(deg=3)
        continuum = cheb.fit(spec)
        np.testing.assert_allclose(continuum, 5.0, atol=1e-8)

    def test_fit_linear_spectrum(self):
        wl = np.linspace(5000, 6000, 200)
        flux = np.linspace(1.0, 2.0, 200)
        spec = _FakeSpectrum(wl, flux)
        cheb = Chebyshev(deg=3)
        continuum = cheb.fit(spec)
        np.testing.assert_allclose(continuum, flux, atol=1e-8)

    def test_theta_shape(self):
        wl = np.linspace(5000, 6000, 100)
        flux = np.ones(100)
        spec = _FakeSpectrum(wl, flux)
        cheb = Chebyshev(deg=4)
        cheb.fit(spec)
        # theta should be (N=1, num_regions=1, deg+1=5)
        assert cheb.theta.shape == (1, 1, 5)

    def test_fit_with_regions(self):
        wl = np.linspace(5000, 6000, 200)
        flux = np.ones(200) * 3.0
        spec = _FakeSpectrum(wl, flux)
        cheb = Chebyshev(deg=2, regions=[(5000, 5500), (5500, 6000)])
        continuum = cheb.fit(spec)
        # Interior pixels should be fit correctly; boundary pixels may be fill_value
        finite = np.isfinite(continuum)
        assert finite.sum() > 190  # most pixels should be finite
        np.testing.assert_allclose(continuum[finite], 3.0, atol=1e-6)

    def test_fit_2d_spectrum(self):
        wl = np.linspace(5000, 6000, 100)
        flux = np.vstack([np.ones(100) * 2.0, np.ones(100) * 4.0])
        ivar = np.ones_like(flux)
        spec = _FakeSpectrum(wl, flux, ivar)
        cheb = Chebyshev(deg=3)
        continuum = cheb.fit(spec)
        assert continuum.shape == (2, 100)
        np.testing.assert_allclose(continuum[0], 2.0, atol=1e-8)
        np.testing.assert_allclose(continuum[1], 4.0, atol=1e-8)


# ---------------------------------------------------------------------------
# continuum/scalar.py tests
# ---------------------------------------------------------------------------
from astra.specutils.continuum.scalar import Scalar


class _FakeSpectrumForScalar:
    """Minimal spectrum-like object for testing Scalar.fit()."""
    def __init__(self, wavelength, flux):
        self.wavelength = np.asarray(wavelength)
        self.flux = np.asarray(flux)


class TestScalarContinuum:

    def test_mean(self):
        wl = np.linspace(5000, 6000, 100)
        flux = np.arange(100, dtype=float)
        spec = _FakeSpectrumForScalar(wl, flux)
        s = Scalar(method="mean")
        continuum = s.fit(spec)
        np.testing.assert_allclose(continuum, np.mean(flux))

    def test_median(self):
        wl = np.linspace(5000, 6000, 100)
        flux = np.arange(100, dtype=float)
        spec = _FakeSpectrumForScalar(wl, flux)
        s = Scalar(method="median")
        continuum = s.fit(spec)
        np.testing.assert_allclose(continuum, np.median(flux))

    def test_max(self):
        wl = np.linspace(5000, 6000, 50)
        flux = np.random.RandomState(42).rand(50)
        spec = _FakeSpectrumForScalar(wl, flux)
        s = Scalar(method="max")
        continuum = s.fit(spec)
        np.testing.assert_allclose(continuum, np.max(flux))

    def test_min(self):
        wl = np.linspace(5000, 6000, 50)
        flux = np.random.RandomState(42).rand(50)
        spec = _FakeSpectrumForScalar(wl, flux)
        s = Scalar(method="min")
        continuum = s.fit(spec)
        np.testing.assert_allclose(continuum, np.min(flux))

    def test_invalid_method(self):
        with pytest.raises(ValueError):
            Scalar(method="bogus")

    def test_with_regions(self):
        wl = np.linspace(5000, 6000, 100)
        flux = np.ones(100, dtype=float)
        flux[:50] = 2.0
        flux[50:] = 8.0
        spec = _FakeSpectrumForScalar(wl, flux)
        s = Scalar(method="mean", regions=[(5000, 5500), (5500, 6000)])
        continuum = s.fit(spec)
        # First half should be ~2, second half ~8
        assert continuum[0] == pytest.approx(2.0, abs=0.5)
        assert continuum[-1] == pytest.approx(8.0, abs=0.5)


# ---------------------------------------------------------------------------
# continuum/nmf/base.py tests
# ---------------------------------------------------------------------------
from astra.specutils.continuum.nmf.base import (
    design_matrix as nmf_design_matrix,
    region_slices,
    _check_and_reshape_flux_ivar,
    _check_dispersion_components_shape,
)


class TestNMFDesignMatrix:

    def test_shape(self):
        wl = np.linspace(5000, 6000, 100)
        M = nmf_design_matrix(wl, deg=3, L=1400.0)
        # Should be (2*deg+1, P)
        assert M.shape == (7, 100)

    def test_first_row_ones(self):
        wl = np.linspace(5000, 6000, 50)
        M = nmf_design_matrix(wl, deg=2, L=1000.0)
        np.testing.assert_allclose(M[0], 1.0)

    def test_trig_values(self):
        wl = np.linspace(5000, 6000, 50)
        L = 1000.0
        M = nmf_design_matrix(wl, deg=1, L=L)
        scale = 2 * np.pi / L
        # Row 1 should be cos(scale * wl), row 2 should be sin(scale * wl)
        np.testing.assert_allclose(M[1], np.cos(scale * wl), atol=1e-12)
        np.testing.assert_allclose(M[2], np.sin(scale * wl), atol=1e-12)


class TestRegionSlices:

    def test_basic(self):
        wl = np.linspace(5000, 6000, 1000)
        regions = [(5200, 5400)]
        slices = region_slices(wl, regions)
        assert len(slices) == 1
        # All wavelengths in the slice should be within the region
        assert wl[slices[0]].min() >= 5200
        assert wl[slices[0]].max() <= 5400

    def test_multiple_regions(self):
        wl = np.linspace(5000, 6000, 1000)
        regions = [(5100, 5300), (5700, 5900)]
        slices = region_slices(wl, regions)
        assert len(slices) == 2


class TestCheckAndReshapeFluxIvar:

    def test_1d_to_2d(self):
        wl = np.linspace(5000, 6000, 100)
        flux = np.ones(100)
        ivar = np.ones(100)
        f, i = _check_and_reshape_flux_ivar(wl, flux, ivar)
        assert f.ndim == 2
        assert i.ndim == 2

    def test_bad_pixels_zeroed(self):
        wl = np.linspace(5000, 6000, 10)
        flux = np.ones(10)
        flux[3] = np.nan
        flux[5] = -1.0
        ivar = np.ones(10)
        f, i = _check_and_reshape_flux_ivar(wl, flux, ivar)
        assert f[0, 3] == 0
        assert i[0, 3] == 0
        assert f[0, 5] == 0
        assert i[0, 5] == 0

    def test_shape_mismatch_raises(self):
        wl = np.linspace(5000, 6000, 100)
        flux = np.ones(50)
        ivar = np.ones(50)
        with pytest.raises(AssertionError):
            _check_and_reshape_flux_ivar(wl, flux, ivar)


class TestCheckDispersionComponentsShape:

    def test_valid(self):
        wl = np.linspace(5000, 6000, 100)
        components = np.ones((3, 100))
        _check_dispersion_components_shape(wl, components)  # should not raise

    def test_mismatch(self):
        wl = np.linspace(5000, 6000, 100)
        components = np.ones((3, 50))
        with pytest.raises(AssertionError):
            _check_dispersion_components_shape(wl, components)


# ---------------------------------------------------------------------------
# frizzle.py tests (utility functions only - avoid heavy dependencies)
# ---------------------------------------------------------------------------
# frizzle.py imports finufft at module level, which may not be installed.
# We import the specific utility functions we need by loading the module source.
import importlib
import types

def _import_frizzle_utils():
    """Import utility functions from frizzle.py without triggering the finufft import."""
    import sys
    # Temporarily stub finufft and pylops so the module can be imported
    stubs = {}
    for mod_name in ("finufft", "pylops"):
        if mod_name not in sys.modules:
            stub = types.ModuleType(mod_name)
            if mod_name == "pylops":
                # pylops.LinearOperator is used as a base class
                stub.LinearOperator = type("LinearOperator", (), {})
                stub.MatrixMult = None
                stub.Diagonal = None
                stub.Identity = None
            sys.modules[mod_name] = stub
            stubs[mod_name] = stub
    try:
        from astra.specutils.frizzle import ensure_dict, check_inputs, separate_flags, combine_flags
    finally:
        for mod_name, stub in stubs.items():
            if sys.modules.get(mod_name) is stub:
                del sys.modules[mod_name]
    return ensure_dict, check_inputs, separate_flags, combine_flags

ensure_dict, check_inputs, separate_flags, combine_flags = _import_frizzle_utils()


class TestEnsureDict:

    def test_none_returns_defaults(self):
        result = ensure_dict(None, a=1, b=2)
        assert result == {"a": 1, "b": 2}

    def test_overrides_defaults(self):
        result = ensure_dict({"a": 10}, a=1, b=2)
        assert result == {"a": 10, "b": 2}

    def test_empty_dict(self):
        result = ensure_dict({})
        assert result == {}


class TestCheckInputs:

    def test_basic(self):
        wl_out = np.linspace(5000, 6000, 50)
        wl = np.linspace(5000, 6000, 100)
        flux = np.ones(100)
        wl_out_r, wl_r, flux_r, ivar_r, mask_r = check_inputs(wl_out, wl, flux, None, None)
        assert ivar_r.shape == flux_r.shape
        np.testing.assert_allclose(ivar_r, 1.0)
        assert mask_r.dtype == bool

    def test_mask_applied(self):
        wl_out = np.linspace(5000, 6000, 50)
        wl = np.linspace(5000, 6000, 100)
        flux = np.ones(100)
        mask = np.zeros(100, dtype=bool)
        mask[:10] = True
        _, _, _, _, mask_r = check_inputs(wl_out, wl, flux, None, mask)
        assert mask_r.sum() >= 10  # at least the ones we set


class TestSeparateFlags:

    def test_empty(self):
        result = separate_flags(None)
        assert result == {}

    def test_single_bit(self):
        flags = np.array([1, 0, 1, 0])
        result = separate_flags(flags)
        assert 0 in result
        np.testing.assert_array_equal(result[0], [True, False, True, False])

    def test_two_bits(self):
        flags = np.array([3, 2, 1, 0])
        result = separate_flags(flags)
        np.testing.assert_array_equal(result[0], [True, False, True, False])
        np.testing.assert_array_equal(result[1], [True, True, False, False])


class TestCombineFlags:

    def test_no_flags(self):
        wl_out = np.linspace(5000, 6000, 50)
        wl = np.linspace(5000, 6000, 100)
        result = combine_flags(wl_out, wl, None)
        np.testing.assert_array_equal(result, 0)

    def test_propagates_flags(self):
        wl_out = np.linspace(5000, 6000, 50)
        wl = np.linspace(5000, 6000, 100)
        # Flag all input pixels with bit 0
        flags = np.ones(100, dtype=int)
        result = combine_flags(wl_out, wl, flags)
        # At least some output pixels should be flagged
        assert np.any(result > 0)
