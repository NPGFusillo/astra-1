# Pipeline Output Base

**Module:** `astra.models.pipeline`

All analysis pipeline output models inherit from `PipelineOutputMixin`. This mixin provides a standardized set of metadata fields that every pipeline result carries, along with a uniqueness constraint and convenience methods for creating results.

## PipelineOutputMixin

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `task_pk` | AutoField | Auto-incrementing primary key for the pipeline task |
| `source_pk` | ForeignKeyField | Foreign key linking to the `Source` |
| `spectrum_pk` | ForeignKeyField | Foreign key linking to the `Spectrum` that was analyzed |
| `v_astra` | IntegerField | Astra version (as an integer) that produced the result |
| `created` | DateTimeField | Timestamp when the result was created |
| `modified` | DateTimeField | Timestamp when the result was last modified |
| `t_elapsed` | FloatField | Execution time in seconds |
| `t_overhead` | FloatField | Overhead time in seconds |
| `tag` | TextField | Optional text tag for organizing results |

### Uniqueness Constraint

A generated column `v_astra_major_minor` is computed as `v_astra / 1000` (integer division), giving the major.minor version without the patch number. A uniqueness constraint ensures that each spectrum is analyzed at most once per major.minor Astra version:

```sql
UNIQUE (spectrum_pk, v_astra_major_minor)
```

This means if you re-run a pipeline at the same major.minor version, the existing result will be replaced (upserted). Bumping the patch version will not create a new row, but bumping the minor or major version will.

### Methods

#### `from_spectrum(spectrum, **kwargs)` (classmethod)

A convenience method for creating a pipeline result record from a spectrum object. It automatically extracts `spectrum_pk` and `source_pk` from the given spectrum, and validates that any explicitly provided `source_pk` or `spectrum_pk` values match those on the spectrum.

```python
from astra.models.apogee import ApogeeCoaddedSpectrumInApStar

spectrum = ApogeeCoaddedSpectrumInApStar.get_by_id(1)
result = MyPipeline.from_spectrum(
    spectrum,
    teff=5000.0,
    logg=2.5,
    fe_h=-0.3,
)
result.save()
```

**Parameters:**
- `spectrum` -- A spectrum model instance (e.g., `ApogeeCoaddedSpectrumInApStar`, `BossVisitSpectrum`).
- `**kwargs` -- Additional keyword arguments to set on the pipeline result (e.g., derived stellar parameters).

**Raises:**
- `ValueError` if an explicitly provided `source_pk` or `spectrum_pk` does not match the one on the spectrum.

### How Upserts Work

Because of the `UNIQUE (spectrum_pk, v_astra_major_minor)` constraint, pipeline results can be upserted. When a pipeline runs on a spectrum that already has a result at the same major.minor Astra version, the database will enforce the constraint. Pipeline code can handle this by using Peewee's `on_conflict_replace()` or similar mechanisms to update the existing row instead of raising an error.

### Extending PipelineOutputMixin

Individual pipeline models (e.g., ASPCAP, The Cannon, Snow White) extend `PipelineOutputMixin` with their own result fields (stellar parameters, abundances, flags, etc.). See the individual pipeline documentation pages for details on specific pipeline output models.

```python
class MyPipeline(PipelineOutputMixin):
    teff = FloatField(null=True)
    logg = FloatField(null=True)
    fe_h = FloatField(null=True)
    my_flag = BitField(default=0)
```
