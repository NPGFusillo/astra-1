# Source

**Module:** `astra.models.source`

The `Source` model represents a single astronomical object. Every spectrum and pipeline result in Astra is linked back to a `Source`. Each source has a unique primary key (`pk`) and carries identifiers, astrometry, photometry, targeting information, and reddening estimates.

## Key Fields

### Identifiers

| Field | Type | Description |
|-------|------|-------------|
| `pk` | AutoField | Primary key |
| `sdss_id` | BigIntegerField | Unique SDSS-V identifier |
| `sdss4_apogee_id` | TextField | APOGEE identifier from SDSS-IV (e.g., `2M00000+000000`) |
| `gaia_dr2_source_id` | BigIntegerField | Gaia DR2 source identifier |
| `gaia_dr3_source_id` | BigIntegerField | Gaia DR3 source identifier |
| `tic_v8_id` | BigIntegerField | TESS Input Catalog (v8) identifier |
| `healpix` | IntegerField | HEALPix index for spatial indexing |
| `catalogid` | BigIntegerField | SDSS-V catalog identifier |
| `catalogid21` | BigIntegerField | SDSS-V catalog identifier (v21 cross-match) |
| `catalogid25` | BigIntegerField | SDSS-V catalog identifier (v25 cross-match) |
| `catalogid31` | BigIntegerField | SDSS-V catalog identifier (v31 cross-match) |

### Astrometry

| Field | Type | Description |
|-------|------|-------------|
| `ra` | FloatField | Right ascension (degrees, J2000) |
| `dec` | FloatField | Declination (degrees, J2000) |
| `l` | FloatField | Galactic longitude (degrees) |
| `b` | FloatField | Galactic latitude (degrees) |
| `plx` | FloatField | Parallax (mas), from Gaia |
| `e_plx` | FloatField | Parallax uncertainty (mas) |
| `pmra` | FloatField | Proper motion in RA (mas/yr) |
| `e_pmra` | FloatField | Proper motion in RA uncertainty (mas/yr) |
| `pmde` | FloatField | Proper motion in Dec (mas/yr) |
| `e_pmde` | FloatField | Proper motion in Dec uncertainty (mas/yr) |
| `gaia_v_rad` | FloatField | Radial velocity from Gaia (km/s) |
| `gaia_e_v_rad` | FloatField | Gaia radial velocity uncertainty (km/s) |

### Photometry

The `Source` model stores photometry from several surveys:

| Field | Type | Description |
|-------|------|-------------|
| `g_mag`, `bp_mag`, `rp_mag` | FloatField | Gaia G, BP, RP magnitudes |
| `j_mag`, `h_mag`, `k_mag` | FloatField | 2MASS J, H, K magnitudes |
| `e_j_mag`, `e_h_mag`, `e_k_mag` | FloatField | 2MASS magnitude uncertainties |
| `w1_mag`, `w2_mag` | FloatField | unWISE W1, W2 magnitudes |
| `e_w1_mag`, `e_w2_mag` | FloatField | unWISE magnitude uncertainties |
| `w1_flux`, `w2_flux` | FloatField | unWISE raw fluxes |
| `mag4_5` | FloatField | GLIMPSE (Spitzer 4.5 micron) magnitude |

**Synthetic photometry from Gaia XP spectra:**

| Field | Type | Description |
|-------|------|-------------|
| `u_jkc_mag`, `b_jkc_mag`, `v_jkc_mag`, `r_jkc_mag`, `i_jkc_mag` | FloatField | Johnson-Kron-Cousins magnitudes |
| `u_sdss_mag`, `g_sdss_mag`, `r_sdss_mag`, `i_sdss_mag`, `z_sdss_mag` | FloatField | SDSS magnitudes |
| `y_ps1_mag` | FloatField | Pan-STARRS y-band magnitude |

### Reddening

| Field | Type | Description |
|-------|------|-------------|
| `ebv` | FloatField | Adopted E(B-V) reddening |
| `e_ebv` | FloatField | Uncertainty on adopted E(B-V) |
| `ebv_flags` | BitField | Provenance of adopted E(B-V) |
| `ebv_zhang_2023` | FloatField | E(B-V) from Zhang (2023) |
| `ebv_sfd` | FloatField | E(B-V) from SFD |
| `ebv_bayestar_2019` | FloatField | E(B-V) from Bayestar (2019) |
| `ebv_edenhofer_2023` | FloatField | E(B-V) from Edenhofer (2023) |
| `ebv_rjce_glimpse` | FloatField | E(B-V) from RJCE (GLIMPSE) |
| `ebv_rjce_allwise` | FloatField | E(B-V) from RJCE (AllWISE) |

The `ebv_flags` bit field indicates the provenance of the adopted E(B-V): Zhang (2023), Edenhofer (2023), SFD, RJCE (GLIMPSE or AllWISE), or Bayestar (2019).

### External Stellar Parameter Estimates

| Field | Type | Description |
|-------|------|-------------|
| `zgr_teff` | FloatField | Effective temperature from Zhang, Green & Rix (2023) |
| `zgr_logg` | FloatField | Surface gravity from ZGR (2023) |
| `zgr_fe_h` | FloatField | Metallicity from ZGR (2023) |
| `r_med_geo` | FloatField | Geometric distance from Bailer-Jones (EDR3, 2021) |
| `r_med_photogeo` | FloatField | Photogeometric distance from Bailer-Jones (EDR3, 2021) |

### Observations Summary

| Field | Type | Description |
|-------|------|-------------|
| `n_boss_visits` | IntegerField | Number of BOSS visits |
| `n_apogee_visits` | IntegerField | Number of APOGEE visits |
| `boss_min_mjd`, `boss_max_mjd` | IntegerField | MJD range of BOSS observations |
| `apogee_min_mjd`, `apogee_max_mjd` | IntegerField | MJD range of APOGEE observations |

### Targeting Flags

The `Source` model carries extensive targeting flags from both SDSS-IV (`sdss4_apogee_target1_flags`, `sdss4_apogee2_target1_flags`, etc.) and SDSS-V (`sdss5_target_flags`). These can be queried with the helper methods described below.

## Methods and Properties

### `assigned_to_program(program)`

Check whether this source is assigned to any carton in the given program. Can be used in queries.

```python
# Find all sources in the "mwm_yso" program
sources = Source.select().where(Source.assigned_to_program("mwm_yso"))
```

### `assigned_to_carton_label(label)`

Check whether this source is assigned to the given carton by label.

```python
sources = Source.select().where(Source.assigned_to_carton_label("mwm_yso_disk_apogee"))
```

### `assigned_to_mapper(mapper)`

Check whether this source is assigned to any carton in the given mapper.

```python
sources = Source.select().where(Source.assigned_to_mapper("MWM"))
```

### `assigned_to_carton_pk(pk)`

Check whether this source is assigned to the carton with the given primary key.

### `assigned_to_carton_with_name(name)`

Check whether this source is assigned to any carton with the given name.

### `assigned_to_carton_with_alt_program(alt_program)`

Check whether this source is assigned to any carton with the given alternate program.

### `assigned_to_carton_with_alt_name(alt_name)`

Check whether this source is assigned to any carton with the given alternate name.

### `sdss5_cartons` (property)

Returns the cartons that this source is assigned to, based on the `sdss5_target_flags` bit field.

### `sdss5_target_bits` (property)

Returns a tuple of bit positions of targeting flags that are set for this source.

### `is_sdss5_target_bit_set(bit)`

Check whether a specific carton bit position is set.

### `is_any_sdss5_target_bit_set(*bits)`

Check whether any of the given carton bit positions are set.

### `spectra` (property)

A generator that yields all spectra (across all spectrum types) associated with this source.

```python
source = Source.get(Source.sdss_id == 12345)
for spectrum in source.spectra:
    print(type(spectrum), spectrum.snr)
```
