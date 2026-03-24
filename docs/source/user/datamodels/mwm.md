# MWM Combined Models

**Module:** `astra.models.mwm`

The MWM (Milky Way Mapper) spectrum models unify APOGEE and BOSS spectra into a common framework. They resample all spectra onto standardized wavelength grids in the source rest frame, making them ready for scientific analysis.

## MWM Mixins

### MWMStarMixin

Base mixin for co-added (star-level) MWM spectrum models. Provides a `path` property that generates the `mwmStar` file path.

#### `path` (property)

```python
# Returns path like:
# $MWM_ASTRA/<v_astra>/spectra/star/<sdss_id_groups>/mwmStar-<v_astra>-<sdss_id>.fits
```

### MWMVisitMixin

Base mixin for visit-level MWM spectrum models. Provides a `path` property that generates the `mwmVisit` file path.

#### `path` (property)

```python
# Returns path like:
# $MWM_ASTRA/<v_astra>/spectra/visit/<sdss_id_groups>/mwmVisit-<v_astra>-<sdss_id>.fits
```

## MWMSpectrumProductStatus

Tracks whether MWM spectrum products have been created for a given source.

| Field | Type | Description |
|-------|------|-------------|
| `source_pk` | ForeignKeyField | Link to the Source |
| `task_pk` | AutoField | Primary key |
| `v_astra` | IntegerField | Astra version |
| `flags` | BitField | Processing status flags |

**Status flags:**

| Flag | Description |
|------|-------------|
| `flag_skipped_because_no_sdss_id` | Source has no SDSS ID |
| `flag_skipped_because_not_stellar_like` | Source is not stellar-like |
| `flag_attempted_but_exception` | Exception occurred during processing |
| `flag_created_mwm_visit` | mwmVisit file created successfully |
| `flag_created_mwm_star` | mwmStar file created successfully |


## BossRestFrameVisitSpectrum

A BOSS visit spectrum that has been resampled onto a common log-lambda wavelength grid and shifted to the source rest frame. Stored in `mwmVisit` files. Inherits from `MWMVisitMixin`.

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `spectrum_pk` | ForeignKeyField | Unique spectrum identifier |
| `source` | ForeignKeyField | Foreign key to Source |
| `drp_spectrum_pk` | ForeignKeyField | Link to the original `BossVisitSpectrum` |
| `sdss_id` | BigIntegerField | SDSS-V unique identifier |
| `release` | TextField | Data release |
| `run2d` | TextField | BOSS reduction pipeline version |
| `mjd` | IntegerField | Modified Julian Date |
| `fieldid` | IntegerField | Field identifier |
| `catalogid` | BigIntegerField | SDSS catalog identifier |
| `telescope` | TextField | Telescope used |

**Spectral data (source rest frame):**

| Field | Type | Description |
|-------|------|-------------|
| `wavelength` | PixelArray | Log-lambda grid (4648 pixels, crval=3.5523, cdelt=1e-4) |
| `flux` | PixelArray | Flux array |
| `ivar` | PixelArray | Inverse variance array |
| `pixel_flags` | PixelArray | Per-pixel quality flags |

**Quality and radial velocity:**

| Field | Type | Description |
|-------|------|-------------|
| `snr` | FloatField | Signal-to-noise ratio |
| `in_stack` | BooleanField | Whether this visit was used in the combined spectrum |
| `xcsao_v_rad` | FloatField | Radial velocity from XCSAO (km/s) |
| `xcsao_teff` | FloatField | Effective temperature from XCSAO |
| `xcsao_logg` | FloatField | Surface gravity from XCSAO |
| `xcsao_fe_h` | FloatField | Metallicity from XCSAO |

**NMF continuum model:**

| Field | Type | Description |
|-------|------|-------------|
| `continuum` | PixelArray | NMF continuum model |
| `nmf_rchi2` | FloatField | Reduced chi-squared of NMF fit |
| `nmf_flags` | BitField | NMF continuum method flags |

### Methods and Properties

#### `path` (property)

Inherited from `MWMVisitMixin`. Returns the `mwmVisit` file path.

#### `e_flux` (property)

Returns flux uncertainty as `ivar**-0.5`.


## BossCombinedSpectrum

A co-added BOSS spectrum created by stacking all good rest-frame visit spectra for a source. This fills the gap left by the BOSS DRP, which does not produce stacked spectra. Stored in `mwmStar` files. Inherits from `MWMStarMixin`.

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `spectrum_pk` | ForeignKeyField | Unique spectrum identifier |
| `source` | ForeignKeyField | Foreign key to Source |
| `sdss_id` | BigIntegerField | SDSS-V unique identifier |
| `release` | TextField | Data release |
| `run2d` | TextField | BOSS reduction pipeline version |
| `telescope` | TextField | Telescope used |

**Observation summary:**

| Field | Type | Description |
|-------|------|-------------|
| `n_visits` | IntegerField | Number of BOSS visits |
| `n_good_visits` | IntegerField | Number of good visits |
| `n_good_rvs` | IntegerField | Number of good RV measurements |
| `min_mjd` | IntegerField | Minimum MJD of contributing visits |
| `max_mjd` | IntegerField | Maximum MJD of contributing visits |

**Radial velocity:**

| Field | Type | Description |
|-------|------|-------------|
| `v_rad` | FloatField | Mean radial velocity (km/s) |
| `e_v_rad` | FloatField | Uncertainty on mean radial velocity (km/s) |
| `std_v_rad` | FloatField | Standard deviation of visit radial velocities (km/s) |
| `median_e_v_rad` | FloatField | Median per-visit RV uncertainty (km/s) |
| `xcsao_teff` | FloatField | Effective temperature from XCSAO |
| `xcsao_logg` | FloatField | Surface gravity from XCSAO |
| `xcsao_fe_h` | FloatField | Metallicity from XCSAO |

**Spectral data:**

| Field | Type | Description |
|-------|------|-------------|
| `wavelength` | PixelArray | Log-lambda grid (4648 pixels, crval=3.5523, cdelt=1e-4) |
| `flux` | PixelArray | Co-added flux |
| `ivar` | PixelArray | Co-added inverse variance |
| `pixel_flags` | PixelArray | Per-pixel quality flags |
| `snr` | FloatField | Signal-to-noise ratio of co-added spectrum |

**NMF continuum model:**

| Field | Type | Description |
|-------|------|-------------|
| `continuum` | PixelArray | NMF continuum model |
| `nmf_rectified_model_flux` | PixelArray | NMF rectified model flux |
| `nmf_rchi2` | FloatField | Reduced chi-squared of NMF fit |
| `nmf_flags` | BitField | NMF continuum method flags |

### Methods and Properties

#### `path` (property)

Inherited from `MWMStarMixin`. Returns the `mwmStar` file path.


## ApogeeCombinedSpectrum

A co-added APOGEE spectrum in the MWM framework. Similar in structure to `BossCombinedSpectrum` but for APOGEE data, using the APOGEE log-lambda grid (8575 pixels, crval=4.179, cdelt=6e-6). Stored in `mwmStar` files. Inherits from `MWMStarMixin`.

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `spectrum_pk` | ForeignKeyField | Unique spectrum identifier |
| `source` | ForeignKeyField | Foreign key to Source |
| `sdss_id` | BigIntegerField | SDSS-V unique identifier |
| `release` | TextField | Data release |
| `apred` | TextField | APOGEE reduction pipeline version |
| `obj` | TextField | Object name |
| `telescope` | TextField | Telescope used |

**Observation summary:**

| Field | Type | Description |
|-------|------|-------------|
| `n_entries` | IntegerField | Number of apStar entries for this object |
| `n_visits` | IntegerField | Number of APOGEE visits |
| `n_good_visits` | IntegerField | Number of good visits |
| `n_good_rvs` | IntegerField | Number of good RV measurements |
| `min_mjd` | IntegerField | Minimum MJD of contributing visits |
| `max_mjd` | IntegerField | Maximum MJD of contributing visits |

**Summary statistics and radial velocity:**

| Field | Type | Description |
|-------|------|-------------|
| `snr` | FloatField | Signal-to-noise ratio |
| `mean_fiber` | FloatField | S/N-weighted mean visit fiber number |
| `std_fiber` | FloatField | Standard deviation of visit fiber numbers |
| `v_rad` | FloatField | Mean radial velocity (km/s) |
| `e_v_rad` | FloatField | Uncertainty on mean radial velocity (km/s) |
| `std_v_rad` | FloatField | Standard deviation of visit radial velocities (km/s) |
| `doppler_teff` | FloatField | Effective temperature from Doppler |
| `doppler_logg` | FloatField | Surface gravity from Doppler |
| `doppler_fe_h` | FloatField | Metallicity from Doppler |

**Spectral data:**

| Field | Type | Description |
|-------|------|-------------|
| `wavelength` | PixelArray | Log-lambda grid (8575 pixels, crval=4.179, cdelt=6e-6) |
| `flux` | PixelArray | Co-added flux |
| `ivar` | PixelArray | Co-added inverse variance |
| `pixel_flags` | PixelArray | Per-pixel quality flags |

**NMF continuum model:**

| Field | Type | Description |
|-------|------|-------------|
| `continuum` | PixelArray | NMF continuum model |
| `nmf_rectified_model_flux` | PixelArray | NMF rectified model flux |
| `nmf_rchi2` | FloatField | Reduced chi-squared of NMF fit |
| `nmf_flags` | BitField | NMF continuum method flags |

### Methods and Properties

#### `path` (property)

Inherited from `MWMStarMixin`. Returns the `mwmStar` file path.


## ApogeeRestFrameVisitSpectrum

An APOGEE visit spectrum resampled onto the common APOGEE log-lambda grid and shifted to the source rest frame. The APOGEE analogue of `BossRestFrameVisitSpectrum`. Stored in `mwmVisit` files. Inherits from `MWMVisitMixin`.

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `spectrum_pk` | ForeignKeyField | Unique spectrum identifier |
| `source` | ForeignKeyField | Foreign key to Source |
| `sdss_id` | BigIntegerField | SDSS-V unique identifier |
| `release` | TextField | Data release |
| `apred` | TextField | APOGEE reduction pipeline version |
| `telescope` | TextField | Telescope used |
| `plate` | TextField | Plate identifier |
| `fiber` | IntegerField | Fiber number |
| `mjd` | IntegerField | Modified Julian Date |
| `field` | TextField | Field identifier |
| `obj` | TextField | Object name |

**Quality and radial velocity:**

| Field | Type | Description |
|-------|------|-------------|
| `snr` | FloatField | Signal-to-noise ratio |
| `in_stack` | BooleanField | Whether this visit was used in the combined spectrum |
| `spectrum_flags` | BitField | Quality flags (same bit definitions as `ApogeeVisitSpectrum`) |
| `v_rad` | FloatField | Absolute radial velocity (km/s) |
| `v_rel` | FloatField | Relative radial velocity (km/s) |
| `e_v_rel` | FloatField | Uncertainty on relative RV (km/s) |
| `doppler_teff` | FloatField | Effective temperature from Doppler |
| `doppler_logg` | FloatField | Surface gravity from Doppler |
| `doppler_fe_h` | FloatField | Metallicity from Doppler |

**Spectral data (source rest frame):**

| Field | Type | Description |
|-------|------|-------------|
| `wavelength` | PixelArray | Log-lambda grid (8575 pixels, crval=4.179, cdelt=6e-6) |
| `flux` | PixelArray | Flux array |
| `ivar` | PixelArray | Inverse variance array |
| `pixel_flags` | PixelArray | Per-pixel quality flags |
| `continuum` | PixelArray | NMF continuum model |
| `nmf_rchi2` | FloatField | Reduced chi-squared of NMF fit |

### Methods and Properties

#### `path` (property)

Inherited from `MWMVisitMixin`. Returns the `mwmVisit` file path.

#### `flag_bad` (hybrid property)

Returns `True` if any critical quality flags are set. Can be used in database queries.

#### `flag_warn` (hybrid property)

Returns `True` if any spectrum flag is set. Can be used in database queries.
