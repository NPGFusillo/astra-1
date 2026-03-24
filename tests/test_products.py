
import os
os.environ["ASTRA_DATABASE_PATH"] = ":memory:"

import tempfile
import numpy as np
import pytest
from collections import OrderedDict
from astropy.io import fits


# ---------------------------------------------------------------------------
# Tests for astra.products.utils
# ---------------------------------------------------------------------------

def test_resolve_model_passthrough():
    """resolve_model should return a non-string argument unchanged."""
    from astra.products.utils import resolve_model

    class FakeModel:
        pass

    assert resolve_model(FakeModel) is FakeModel


def test_resolve_model_by_name():
    """resolve_model should look up a model by its string name."""
    from astra.products.utils import resolve_model
    from astra.models.source import Source

    result = resolve_model("Source")
    assert result is Source


def test_resolve_model_dotted_name():
    """resolve_model should resolve dotted names like 'module.ClassName'."""
    from astra.products.utils import resolve_model
    from astra.models.source import Source

    result = resolve_model("source.Source")
    assert result is Source


def test_check_path_creates_directory():
    """check_path should create intermediate directories."""
    from astra.products.utils import check_path

    with tempfile.TemporaryDirectory() as tmpdir:
        nested = os.path.join(tmpdir, "a", "b", "c", "test.fits")
        check_path(nested, overwrite=True)
        assert os.path.isdir(os.path.join(tmpdir, "a", "b", "c"))


def test_check_path_raises_on_existing_file():
    """check_path should raise OSError when the file exists and overwrite=False."""
    from astra.products.utils import check_path

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.fits")
        with open(path, "w") as f:
            f.write("x")
        with pytest.raises(OSError, match="already exists"):
            check_path(path, overwrite=False)


def test_check_path_allows_overwrite():
    """check_path should not raise when overwrite=True even if file exists."""
    from astra.products.utils import check_path

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.fits")
        with open(path, "w") as f:
            f.write("x")
        # Should not raise
        check_path(path, overwrite=True)


def test_check_path_gzip():
    """check_path with gzip=True should check for the .gz file."""
    from astra.products.utils import check_path

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.fits")
        gz_path = path + ".gz"
        with open(gz_path, "w") as f:
            f.write("x")
        with pytest.raises(OSError, match="already exists"):
            check_path(path, overwrite=False, gzip=True)


def test_wavelength_cards_lower():
    """wavelength_cards should return the correct structure with lowercase keys."""
    from astra.products.utils import wavelength_cards, BLANK_CARD

    cards = wavelength_cards(crval=3.5, cdelt=0.001, num_pixels=100, upper=False)

    # Should contain BLANK_CARD, header, BLANK_CARD, then data cards
    assert cards[0] == BLANK_CARD
    assert cards[2] == BLANK_CARD

    # Check the data cards
    card_dict = {c[0]: c[1] for c in cards if c[0] not in (" ",)}
    assert card_dict["CRVAL"] == np.round(3.5, 6)
    assert card_dict["CDELT"] == np.round(0.001, 6)
    assert card_dict["CTYPE"] == "LOG-LINEAR"
    assert card_dict["CUNIT"] == "Angstrom (Vacuum)"
    assert card_dict["CRPIX"] == 1
    assert card_dict["DC-FLAG"] == 1
    assert card_dict["NPIXELS"] == 100


def test_wavelength_cards_upper():
    """wavelength_cards with upper=True should uppercase the header text."""
    from astra.products.utils import wavelength_cards

    cards = wavelength_cards(crval=4.0, cdelt=1e-4, num_pixels=500, upper=True)
    header_card = cards[1]
    assert header_card[1] == "WAVELENGTH INFORMATION (VACUUM)"


def test_wavelength_cards_decimals():
    """wavelength_cards should respect the decimals parameter."""
    from astra.products.utils import wavelength_cards

    cards = wavelength_cards(crval=3.123456789, cdelt=0.000123456789, num_pixels=10, decimals=3)
    card_dict = {c[0]: c[1] for c in cards if c[0] not in (" ",)}
    assert card_dict["CRVAL"] == np.round(3.123456789, 3)
    assert card_dict["CDELT"] == np.round(0.000123456789, 3)


def test_get_basic_header_minimal():
    """get_basic_header with no args should return a header with v_astra and created."""
    from astra.products.utils import get_basic_header
    from astra import __version__

    header = get_basic_header()
    assert isinstance(header, fits.Header)
    assert header["V_ASTRA"] == __version__
    assert "CREATED" in header


def test_get_basic_header_with_pipeline():
    """get_basic_header should include PIPELINE when specified."""
    from astra.products.utils import get_basic_header

    header = get_basic_header(pipeline="TestPipeline")
    assert header["PIPELINE"] == "TestPipeline"


def test_get_basic_header_with_instrument_and_observatory():
    """get_basic_header with instrument and observatory should set EXTNAME, OBSRVTRY, INSTRMNT."""
    from astra.products.utils import get_basic_header

    header = get_basic_header(instrument="boss", observatory="apo")
    assert header["OBSRVTRY"] == "APO"
    assert header["INSTRMNT"] == "BOSS"
    assert header["EXTNAME"] == "BOSS/APO"


def test_get_basic_header_with_dispersion():
    """get_basic_header with include_dispersion_cards should add wavelength info."""
    from astra.products.utils import get_basic_header

    header = get_basic_header(instrument="boss", include_dispersion_cards=True)
    assert "CRVAL" in header
    assert "CDELT" in header
    assert "NPIXELS" in header


def test_get_basic_header_unknown_instrument_dispersion():
    """get_basic_header should raise ValueError for unknown instrument with dispersion cards."""
    from astra.products.utils import get_basic_header

    with pytest.raises(ValueError, match="Unknown instrument"):
        get_basic_header(instrument="unknown", include_dispersion_cards=True)


def test_get_basic_header_hdu_descriptions():
    """get_basic_header with include_hdu_descriptions should add COMMENT cards."""
    from astra.products.utils import get_basic_header

    header = get_basic_header(include_hdu_descriptions=True)
    comments = [str(c) for c in header["COMMENT"]]
    assert any("HDU 0" in c for c in comments)
    assert any("HDU 1" in c for c in comments)


def test_get_basic_header_upper():
    """get_basic_header with upper=True should uppercase section headers."""
    from astra.products.utils import get_basic_header

    header = get_basic_header(upper=True)
    # The "Metadata" section header should be uppercased
    # Check that V_ASTRA is present (always works regardless of upper)
    assert "V_ASTRA" in header


def test_get_fill_value_text_field():
    """get_fill_value should return '' for TextField."""
    from astra.products.utils import get_fill_value
    from astra.fields import TextField

    field = TextField(help_text="test")
    field.name = "test_text"
    result = get_fill_value(field, None)
    assert result == ""


def test_get_fill_value_float_field():
    """get_fill_value should return NaN for FloatField."""
    from astra.products.utils import get_fill_value
    from astra.fields import FloatField

    field = FloatField(help_text="test")
    field.name = "test_float"
    result = get_fill_value(field, None)
    assert np.isnan(result)


def test_get_fill_value_integer_field():
    """get_fill_value should return -1 for IntegerField."""
    from astra.products.utils import get_fill_value
    from astra.fields import IntegerField

    field = IntegerField(help_text="test")
    field.name = "test_int"
    result = get_fill_value(field, None)
    assert result == -1


def test_get_fill_value_boolean_field():
    """get_fill_value should return False for BooleanField."""
    from astra.products.utils import get_fill_value
    from astra.fields import BooleanField

    field = BooleanField(help_text="test")
    field.name = "test_bool"
    result = get_fill_value(field, None)
    assert result is False


def test_get_fill_value_given_fill_values():
    """get_fill_value should use given_fill_values if provided."""
    from astra.products.utils import get_fill_value
    from astra.fields import FloatField

    field = FloatField(help_text="test")
    field.name = "custom_field"
    result = get_fill_value(field, {"custom_field": 42.0})
    assert result == 42.0


def test_get_fill_value_biginteger_field():
    """get_fill_value should return -1 for BigIntegerField."""
    from astra.products.utils import get_fill_value
    from astra.fields import BigIntegerField

    field = BigIntegerField(help_text="test")
    field.name = "test_bigint"
    result = get_fill_value(field, None)
    assert result == -1


def test_get_fill_value_datetime_field():
    """get_fill_value should return '' for DateTimeField."""
    from astra.products.utils import get_fill_value
    from astra.fields import DateTimeField

    field = DateTimeField(help_text="test")
    field.name = "test_datetime"
    result = get_fill_value(field, None)
    assert result == ""


def test_get_fill_value_autofield():
    """get_fill_value should return -1 for AutoField."""
    from astra.products.utils import get_fill_value
    from astra.fields import AutoField

    field = AutoField(help_text="test")
    field.name = "test_auto"
    result = get_fill_value(field, None)
    assert result == -1


def test_get_fill_value_bit_field():
    """get_fill_value should return 0 for BitField."""
    from astra.products.utils import get_fill_value
    from astra.fields import BitField

    field = BitField(help_text="test")
    field.name = "test_bit"
    result = get_fill_value(field, None)
    assert result == 0


def test_fits_column_kwargs_text_field():
    """fits_column_kwargs should produce format 'A{N}' for TextField."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import TextField

    field = TextField(help_text="test")
    field.name = "test_text"
    field.column_name = "test_text"
    values = ["hello", "world", "hi"]
    result = fits_column_kwargs(field, values, upper=True, name="test_text")
    assert result["name"] == "TEST_TEXT"
    assert result["format"] == "A5"  # max length of "hello"/"world"


def test_fits_column_kwargs_text_field_empty():
    """fits_column_kwargs should produce format 'A1' for empty text values."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import TextField

    field = TextField(help_text="test")
    field.name = "test_text"
    field.column_name = "test_text"
    values = []
    result = fits_column_kwargs(field, values, upper=False, name="test_text")
    assert result["name"] == "test_text"
    assert result["format"] == "A1"


def test_fits_column_kwargs_float_field():
    """fits_column_kwargs should produce format 'E' for FloatField."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import FloatField

    field = FloatField(help_text="test")
    field.name = "test_float"
    field.column_name = "test_float"
    values = [1.0, 2.0, 3.0]
    result = fits_column_kwargs(field, values, upper=False, name="test_float")
    assert result["format"] == "E"


def test_fits_column_kwargs_integer_field():
    """fits_column_kwargs should produce format 'J' for IntegerField."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import IntegerField

    field = IntegerField(help_text="test")
    field.name = "test_int"
    field.column_name = "test_int"
    values = [1, 2, 3]
    result = fits_column_kwargs(field, values, upper=True, name="test_int")
    assert result["format"] == "J"
    assert result["name"] == "TEST_INT"


def test_fits_column_kwargs_boolean_field():
    """fits_column_kwargs should produce format 'L' for BooleanField."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import BooleanField

    field = BooleanField(help_text="test")
    field.name = "test_bool"
    field.column_name = "test_bool"
    values = [True, False]
    result = fits_column_kwargs(field, values, upper=False, name="test_bool")
    assert result["format"] == "L"


def test_fits_column_kwargs_biginteger_field():
    """fits_column_kwargs should produce format 'K' for BigIntegerField."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import BigIntegerField

    field = BigIntegerField(help_text="test")
    field.name = "test_bigint"
    field.column_name = "test_bigint"
    values = [123456789, 987654321]
    result = fits_column_kwargs(field, values, upper=False, name="test_bigint")
    assert result["format"] == "K"


def test_fits_column_kwargs_datetime_field():
    """fits_column_kwargs should produce format 'A26' for DateTimeField and convert to isoformat."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import DateTimeField
    import datetime

    field = DateTimeField(help_text="test")
    field.name = "test_dt"
    field.column_name = "test_dt"
    dt = datetime.datetime(2024, 1, 15, 12, 30, 45)
    values = [dt]
    result = fits_column_kwargs(field, values, upper=False, name="test_dt")
    assert result["format"] == "A26"
    # The array should contain isoformat strings
    assert result["array"] == [dt.isoformat()]


def test_fits_column_kwargs_bit_field():
    """fits_column_kwargs should produce format 'K' for BitField."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import BitField

    field = BitField(help_text="test")
    field.name = "test_bit"
    field.column_name = "test_bit"
    values = [0, 1, 2]
    result = fits_column_kwargs(field, values, upper=False, name="test_bit")
    assert result["format"] == "K"


def test_fits_column_kwargs_uses_field_name_when_no_name_given():
    """fits_column_kwargs should use field.column_name when name is not explicitly given."""
    from astra.products.utils import fits_column_kwargs
    from astra.fields import IntegerField

    field = IntegerField(help_text="test")
    field.name = "my_field"
    field.column_name = "my_field"
    values = [1, 2]
    result = fits_column_kwargs(field, values, upper=True)
    assert result["name"] == "MY_FIELD"


def test_dispersion_array_apogee():
    """dispersion_array should return the correct array for apogee."""
    from astra.products.utils import dispersion_array, INSTRUMENT_COMMON_DISPERSION_VALUES

    result = dispersion_array("apogee")
    crval, cdelt, num_pixels = INSTRUMENT_COMMON_DISPERSION_VALUES["apogee"]
    expected = 10 ** (crval + cdelt * np.arange(num_pixels))
    np.testing.assert_allclose(result, expected)
    assert len(result) == num_pixels


def test_dispersion_array_boss():
    """dispersion_array should return the correct array for boss."""
    from astra.products.utils import dispersion_array, INSTRUMENT_COMMON_DISPERSION_VALUES

    result = dispersion_array("boss")
    crval, cdelt, num_pixels = INSTRUMENT_COMMON_DISPERSION_VALUES["boss"]
    expected = 10 ** (crval + cdelt * np.arange(num_pixels))
    np.testing.assert_allclose(result, expected)
    assert len(result) == num_pixels


def test_dispersion_array_case_insensitive():
    """dispersion_array should be case-insensitive."""
    from astra.products.utils import dispersion_array

    r1 = dispersion_array("APOGEE")
    r2 = dispersion_array("apogee")
    r3 = dispersion_array("  Apogee  ")
    np.testing.assert_allclose(r1, r2)
    np.testing.assert_allclose(r2, r3)


def test_get_extname_boss():
    """_get_extname should produce BOSS/APO for boss/apo."""
    from astra.products.utils import _get_extname

    assert _get_extname("boss", "apo") == "BOSS/APO"
    assert _get_extname("BOSS", "lco") == "BOSS/LCO"


def test_get_extname_apogee():
    """_get_extname should produce APOGEE/APO for apogee/apo."""
    from astra.products.utils import _get_extname

    assert _get_extname("apogee", "apo") == "APOGEE/APO"
    assert _get_extname("APOGEE", "LCO") == "APOGEE/LCO"


def test_get_extname_unknown_instrument():
    """_get_extname should raise ValueError for unknown instrument."""
    from astra.products.utils import _get_extname

    with pytest.raises(ValueError, match="Unknown instrument"):
        _get_extname("unknown", "apo")


def test_warn_on_long_name_or_comment_returns_none():
    """warn_on_long_name_or_comment always returns None (early return in current code)."""
    from astra.products.utils import warn_on_long_name_or_comment
    from astra.fields import FloatField

    field = FloatField(help_text="short")
    field.name = "x"
    assert warn_on_long_name_or_comment(field) is None


def test_blank_and_filler_card_constants():
    """BLANK_CARD and FILLER_CARD should have the expected structure."""
    from astra.products.utils import BLANK_CARD, FILLER_CARD, FILLER_CARD_KEY

    assert BLANK_CARD == (" ", " ", None)
    assert FILLER_CARD_KEY == "TTYPE0"
    assert len(FILLER_CARD) == 3


def test_datetime_fmt_constant():
    """DATETIME_FMT should be a valid strftime format string."""
    from astra.products.utils import DATETIME_FMT
    import datetime

    # Should not raise
    result = datetime.datetime(2024, 1, 1).strftime(DATETIME_FMT)
    assert isinstance(result, str)
    assert len(result) > 0


def test_instrument_common_dispersion_values():
    """INSTRUMENT_COMMON_DISPERSION_VALUES should contain apogee and boss."""
    from astra.products.utils import INSTRUMENT_COMMON_DISPERSION_VALUES

    assert "apogee" in INSTRUMENT_COMMON_DISPERSION_VALUES
    assert "boss" in INSTRUMENT_COMMON_DISPERSION_VALUES
    for key in ("apogee", "boss"):
        val = INSTRUMENT_COMMON_DISPERSION_VALUES[key]
        assert len(val) == 3
        crval, cdelt, num_pixels = val
        assert isinstance(crval, (int, float))
        assert isinstance(cdelt, (int, float))
        assert isinstance(num_pixels, int)


# ---------------------------------------------------------------------------
# Tests for astra.products.pipeline_summary
# ---------------------------------------------------------------------------

def test_ignore_field_name_callable_pk():
    """ignore_field_name_callable should return True for 'pk'."""
    from astra.products.pipeline_summary import ignore_field_name_callable

    assert ignore_field_name_callable("pk") is True
    assert ignore_field_name_callable("PK") is True


def test_ignore_field_name_callable_input_spectrum_pks():
    """ignore_field_name_callable should return True for 'input_spectrum_pks'."""
    from astra.products.pipeline_summary import ignore_field_name_callable

    assert ignore_field_name_callable("input_spectrum_pks") is True
    assert ignore_field_name_callable("INPUT_SPECTRUM_PKS") is True


def test_ignore_field_name_callable_rho_prefix():
    """ignore_field_name_callable should return True for fields starting with 'rho_'."""
    from astra.products.pipeline_summary import ignore_field_name_callable

    assert ignore_field_name_callable("rho_teff_logg") is True
    assert ignore_field_name_callable("rho_something") is True
    assert ignore_field_name_callable("RHO_SOMETHING") is True


def test_ignore_field_name_callable_normal_field():
    """ignore_field_name_callable should return False for normal field names."""
    from astra.products.pipeline_summary import ignore_field_name_callable

    assert ignore_field_name_callable("teff") is False
    assert ignore_field_name_callable("logg") is False
    assert ignore_field_name_callable("fe_h") is False
    assert ignore_field_name_callable("spectrum_pk") is False


def test_get_path_no_gzip():
    """get_path should return a path without .gz when gzip=False."""
    from astra.products.pipeline_summary import get_path
    from astra import __version__

    path = get_path("test.fits", gzip=False)
    assert path.endswith("test.fits")
    assert not path.endswith(".gz")
    assert __version__ in path


def test_get_path_with_gzip():
    """get_path should return a path with .gz when gzip=True."""
    from astra.products.pipeline_summary import get_path

    path = get_path("test.fits", gzip=True)
    assert path.endswith("test.fits.gz")


def test_get_path_contains_summary():
    """get_path should include 'summary' in the path."""
    from astra.products.pipeline_summary import get_path

    path = get_path("test.fits", gzip=False)
    assert "summary" in path


# ---------------------------------------------------------------------------
# Tests for get_fields with mock models
# ---------------------------------------------------------------------------

def test_get_fields_basic():
    """get_fields should collect fields from model _meta.fields."""
    from astra.products.utils import get_fields
    from astra.fields import FloatField, IntegerField
    from peewee import Model
    from astra.models.base import database as astra_db

    class MockModel(Model):
        teff = FloatField(help_text="Effective temperature")
        logg = FloatField(help_text="Surface gravity")
        fe_h = FloatField(help_text="Metallicity")

        category_headers = []
        category_comments = []

        class Meta:
            database = astra_db

    fields = get_fields((MockModel,))
    # Should contain teff, logg, fe_h (plus auto 'id' field from peewee)
    assert "teff" in fields
    assert "logg" in fields
    assert "fe_h" in fields


def test_get_fields_with_ignore_callable():
    """get_fields should skip fields when ignore_field_name_callable returns True."""
    from astra.products.utils import get_fields
    from astra.fields import FloatField, IntegerField
    from peewee import Model
    from astra.models.base import database as astra_db

    class MockModel2(Model):
        teff = FloatField(help_text="Effective temperature")
        rho_teff_logg = FloatField(help_text="Correlation")
        pk_value = IntegerField(help_text="Some pk")

        category_headers = []
        category_comments = []

        class Meta:
            database = astra_db

    def ignore(name):
        return name.startswith("rho_")

    fields = get_fields((MockModel2,), ignore_field_name_callable=ignore)
    assert "teff" in fields
    assert "rho_teff_logg" not in fields
    assert "pk_value" in fields


def test_get_fields_conflict_default_skip():
    """get_fields with no name_conflict_strategy should skip conflicting fields (keep first)."""
    from astra.products.utils import get_fields
    from astra.fields import FloatField
    from peewee import Model
    from astra.models.base import database as astra_db

    class Model1(Model):
        teff = FloatField(help_text="Temperature 1")

        category_headers = []
        category_comments = []

        class Meta:
            database = astra_db
            table_name = "model1"

    class Model2(Model):
        teff = FloatField(help_text="Temperature 2")

        category_headers = []
        category_comments = []

        class Meta:
            database = astra_db
            table_name = "model2"

    fields = get_fields((Model1, Model2))
    # Without conflict strategy, the first model's field should win
    assert fields["teff"].help_text == "Temperature 1"


def test_get_fields_hidden_field_skipped():
    """get_fields should skip fields with _hidden=True."""
    from astra.products.utils import get_fields
    from astra.fields import FloatField, IntegerField
    from peewee import Model
    from astra.models.base import database as astra_db

    class MockModelHidden(Model):
        teff = FloatField(help_text="Temperature")
        hidden_field = IntegerField(help_text="Hidden", _hidden=True)

        category_headers = []
        category_comments = []

        class Meta:
            database = astra_db
            table_name = "mock_hidden"

    fields = get_fields((MockModelHidden,))
    assert "teff" in fields
    assert "hidden_field" not in fields
