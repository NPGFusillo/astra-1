# BOSS Spectrum Models

**Module:** `astra.models.boss`

## BossVisitSpectrum

An optical BOSS spectrum from a `specFull` file. A BOSS "visit" is defined as all exposures of a source taken on the same MJD. The wavelengths are in vacuum and shifted to the Solar system barycentric rest frame (not the source rest frame).

There is no BOSS equivalent of `apStar` in the upstream BOSS pipeline -- the BOSS DRP does not stack spectra across multiple nights. Astra fills this gap with the `BossCombinedSpectrum` model (see [MWM Models](mwm.md)).

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `spectrum_pk` | ForeignKeyField | Unique spectrum identifier |
| `source` | ForeignKeyField | Foreign key to the `Source` |
| `release` | TextField | Data release |
| `run2d` | TextField | BOSS reduction pipeline version |
| `fieldid` | IntegerField | Field identifier |
| `mjd` | IntegerField | Modified Julian Date of observation |
| `catalogid` | BigIntegerField | SDSS catalog identifier |
| `telescope` | TextField | Telescope used (e.g., `"apo25m"`, `"lco25m"`) |
| `spec_file` | TextField | BOSS specFull basename |

**Spectral data:**

| Field | Type | Description |
|-------|------|-------------|
| `wavelength` | PixelArray | Wavelength array (vacuum, barycentric frame); derived from `loglam` as `10**loglam` |
| `flux` | PixelArray | Flux array |
| `ivar` | PixelArray | Inverse variance array |
| `wresl` | PixelArray | Wavelength resolution array |
| `pixel_flags` | PixelArray | Per-pixel quality flags (from `or_mask`) |

**Observing conditions:**

| Field | Type | Description |
|-------|------|-------------|
| `snr` | FloatField | Signal-to-noise ratio |
| `n_exp` | IntegerField | Number of exposures |
| `exptime` | FloatField | Total exposure time (seconds) |
| `seeing` | FloatField | Seeing (arcseconds) |
| `airmass` | FloatField | Airmass |
| `airtemp` | FloatField | Air temperature |
| `humidity` | FloatField | Humidity |

**Radial velocity (XCSAO):**

| Field | Type | Description |
|-------|------|-------------|
| `xcsao_v_rad` | FloatField | Radial velocity from XCSAO (km/s) |
| `xcsao_e_v_rad` | FloatField | RV uncertainty from XCSAO (km/s) |
| `xcsao_teff` | FloatField | Effective temperature from XCSAO |
| `xcsao_logg` | FloatField | Surface gravity from XCSAO |
| `xcsao_fe_h` | FloatField | Metallicity from XCSAO |
| `xcsao_rxc` | FloatField | Cross-correlation R-value |

**Warning flags:**

| Field | Type | Description |
|-------|------|-------------|
| `zwarning_flags` | BitField | BOSS DRP warning flags |
| `flag_sky_fiber` | bit 0 | Sky fiber |
| `flag_little_wavelength_coverage` | bit 1 | Too little wavelength coverage |
| `flag_small_delta_chi2` | bit 2 | Chi-squared too close to second best |
| `flag_unplugged` | bit 7 | Fiber unplugged or damaged |
| `flag_no_data` | bit 9 | No data for this fiber |
| `gri_gaia_transform_flags` | BitField | Flags for provenance of ugriz photometry |

### Methods and Properties

#### `path` (property)

Returns the file path to the `specFull` FITS file. The path template depends on the `run2d` version.

```python
visit = BossVisitSpectrum.get_by_id(1)
print(visit.path)
```

#### `e_flux` (property)

Returns the flux uncertainty array, computed as `ivar**-0.5`.

#### `field_group` (property)

Returns the field group string (e.g., `"015XXX"` for fieldid 15234), used in the file path.

#### `pad_fieldid` (property)

Returns the zero-padded field ID string. Padding rules depend on the `run2d` version.

#### `isplate` (property)

Returns `"p"` for plate-era `run2d` versions (`v6_0_1` through `v6_0_4`), or `""` otherwise. Used in path construction.
