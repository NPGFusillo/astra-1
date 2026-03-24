# Summary Data Products

**Module:** `astra.products.pipeline_summary`

Summary products are FITS files that collect pipeline results across all sources into convenient catalog tables. There are several types of summary products.

## astraAllStar

Created by `create_all_star_product()`, these files contain results from a given pipeline run on co-added (star-level) spectra.

**FITS structure:**

| HDU | Contents |
|-----|----------|
| 0 | Primary HDU with metadata header (pipeline name, Astra version, HDU descriptions) |
| 1 | BOSS results -- one row per source with a co-added BOSS spectrum analyzed by the pipeline, joined with `Source` and `BossCombinedSpectrum` fields |
| 2 | APOGEE results -- one row per source with a co-added APOGEE spectrum analyzed by the pipeline, joined with `Source` and `ApogeeCoaddedSpectrumInApStar` fields |

Each row contains:
- Source-level information (identifiers, astrometry, photometry)
- Spectrum-level metadata (SNR, radial velocities)
- All pipeline output fields (stellar parameters, abundances, flags)
- If the pipeline defines `flag_warn` and `flag_bad` properties, these are included as boolean columns

**File naming:** `astraAllStar<Pipeline>-<version>.fits` (optionally gzip-compressed)


## astraAllVisit

Created by `create_all_visit_product()`, these files have the same HDU structure as `astraAllStar` but contain per-visit results instead of per-star results.

**FITS structure:**

| HDU | Contents |
|-----|----------|
| 0 | Primary HDU with metadata header |
| 1 | BOSS visit-level results (using `BossVisitSpectrum`) |
| 2 | APOGEE visit-level results (using `ApogeeVisitSpectrumInApStar`) |

**File naming:** `astraAllVisit<Pipeline>-<version>.fits` (optionally gzip-compressed)


## astraBest

Created by `create_astra_best_product()`, these files contain the "best" result per source across all pipelines. The HDU structure is simpler: a primary HDU and a single binary table extension with one row per source.

**File naming:** `astraFrankenstein-<version>.fits`


## mwmStar

An `mwmStar` file contains the co-added spectra for a source, with one stacked spectrum per telescope/instrument combination.

**FITS structure:**

| HDU | Contents |
|-----|----------|
| 0 | Primary HDU with source information (identifiers, photometry, astrometry) |
| 1 | BOSS co-added spectrum from Apache Point Observatory (`BossCombinedSpectrum`) |
| 2 | BOSS co-added spectrum from Las Campanas Observatory (`BossCombinedSpectrum`) |
| 3 | APOGEE co-added spectrum from Apache Point Observatory (`ApogeeCombinedSpectrum`) |
| 4 | APOGEE co-added spectrum from Las Campanas Observatory (`ApogeeCombinedSpectrum`) |

These represent the best available spectrum for a source and are the primary input to most Astra analysis pipelines.

**File path pattern:** `$MWM_ASTRA/<v_astra>/spectra/star/<sdss_id_groups>/mwmStar-<v_astra>-<sdss_id>.fits`


## mwmVisit

An `mwmVisit` file contains all visit spectra for a source, organized by telescope and instrument.

**FITS structure:**

| HDU | Contents |
|-----|----------|
| 0 | Primary HDU with source information (identifiers, photometry, astrometry) |
| 1 | All BOSS spectra from Apache Point Observatory (`BossRestFrameVisitSpectrum`) |
| 2 | All BOSS spectra from Las Campanas Observatory (`BossRestFrameVisitSpectrum`) |
| 3 | All APOGEE spectra from Apache Point Observatory (`ApogeeRestFrameVisitSpectrum`) |
| 4 | All APOGEE spectra from Las Campanas Observatory (`ApogeeRestFrameVisitSpectrum`) |

**Key properties of mwmVisit spectra:**

- All wavelengths are in **vacuum** and in the **source rest frame** (unlike `apVisit` which is in the observed frame, and `specFull` which is in the barycentric frame).
- All spectra are **resampled onto common wavelength grids** (BOSS: 4648 pixels; APOGEE: 8575 pixels).
- Spectra deemed unreliable are still included (unlike `apStar`), with an `in_stack` boolean column indicating whether each spectrum was used for the co-added product.

**File path pattern:** `$MWM_ASTRA/<v_astra>/spectra/visit/<sdss_id_groups>/mwmVisit-<v_astra>-<sdss_id>.fits`
