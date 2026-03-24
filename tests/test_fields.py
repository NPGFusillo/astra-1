
import os
os.environ["ASTRA_DATABASE_PATH"] = ":memory:"

import numpy as np


def test_help_text_inheritance_on_fields():
    from peewee import Model
    from astra.fields import FloatField
    from astra.glossary import Glossary

    dec_help_text = "Something I wrpte"

    class DummyModel(Model):
        ra = FloatField()
        some_field_that_is_not_in_glossary = FloatField()
        dec = FloatField(help_text=dec_help_text)

    assert DummyModel.ra.help_text == Glossary.ra
    assert DummyModel.some_field_that_is_not_in_glossary.help_text == None
    assert DummyModel.dec.help_text == dec_help_text


def test_help_text_inheritance_on_flags():

    from peewee import Model
    from astra.fields import BitField
    from astra.glossary import Glossary

    class DummyModel(Model):
        flags = BitField()
        flag_sdss4_apogee_faint = flags.flag()

    overwrite_help_text = "MOO"
    class DummyModel2(Model):
        flags = BitField()
        flag_sdss4_apogee_faint = flags.flag(help_text=overwrite_help_text)

    assert DummyModel2.flag_sdss4_apogee_faint.help_text == overwrite_help_text


def test_glossary_mixin_all_field_types():
    """All custom field types should inherit GlossaryFieldMixin behavior."""
    from peewee import Model
    from astra.fields import (
        IntegerField, FloatField, TextField, BooleanField,
        BigIntegerField, SmallIntegerField, DateTimeField, AutoField,
    )
    from astra.glossary import Glossary

    class FieldTypesModel(Model):
        teff = FloatField()
        snr = FloatField()
        mjd = IntegerField()
        release = TextField()

    # All of these are in the Glossary, so help_text should be auto-populated
    assert FieldTypesModel.teff.help_text == Glossary.teff
    assert FieldTypesModel.snr.help_text == Glossary.snr
    assert FieldTypesModel.mjd.help_text == Glossary.mjd
    assert FieldTypesModel.release.help_text == Glossary.release


def test_bitfield_flag_auto_increment():
    """BitField.flag() should auto-increment flag values as powers of 2."""
    from peewee import Model
    from astra.fields import BitField

    class FlagModel(Model):
        flags = BitField(default=0)
        flag_a = flags.flag()
        flag_b = flags.flag()
        flag_c = flags.flag()

    assert FlagModel.flag_a._value == 1
    assert FlagModel.flag_b._value == 2
    assert FlagModel.flag_c._value == 4


def test_bitfield_flag_explicit_value():
    """BitField.flag() should accept explicit values and continue from there."""
    from peewee import Model
    from astra.fields import BitField

    class FlagModel(Model):
        flags = BitField(default=0)
        flag_a = flags.flag(value=8)
        flag_b = flags.flag()  # should be 16 (8 << 1)

    assert FlagModel.flag_a._value == 8
    assert FlagModel.flag_b._value == 16


def test_bitfield_default_zero():
    """BitField should default to 0."""
    from peewee import Model
    from astra.fields import BitField

    class FlagModel(Model):
        flags = BitField()

    assert FlagModel.flags.default == 0


def test_base_pixel_array_accessor_init():
    """BasePixelArrayAccessor should store all init parameters."""
    from astra.fields import BasePixelArrayAccessor

    class DummyModel:
        pass

    class DummyField:
        pass

    accessor = BasePixelArrayAccessor(
        model=DummyModel,
        field=DummyField,
        name="flux",
        ext=1,
        column_name="FLUX",
        transform=lambda x: x * 2,
        help_text="Test flux",
    )

    assert accessor.model is DummyModel
    assert accessor.field is DummyField
    assert accessor.name == "flux"
    assert accessor.ext == 1
    assert accessor.column_name == "FLUX"
    assert accessor.help_text == "Test flux"
    assert accessor.transform is not None


def test_base_pixel_array_accessor_initialise():
    """_initialise_pixel_array should create __pixel_data__ if missing."""
    from astra.fields import BasePixelArrayAccessor

    accessor = BasePixelArrayAccessor(
        model=None, field=None, name="test", ext=None, column_name="test"
    )

    class Instance:
        pass

    inst = Instance()
    assert not hasattr(inst, "__pixel_data__")
    accessor._initialise_pixel_array(inst)
    assert hasattr(inst, "__pixel_data__")
    assert inst.__pixel_data__ == {}

    # Calling again should not reset existing data
    inst.__pixel_data__["key"] = "value"
    accessor._initialise_pixel_array(inst)
    assert inst.__pixel_data__["key"] == "value"


def test_base_pixel_array_accessor_set():
    """BasePixelArrayAccessor.__set__ should store values in __pixel_data__."""
    from astra.fields import BasePixelArrayAccessor

    accessor = BasePixelArrayAccessor(
        model=None, field=None, name="flux", ext=None, column_name="flux"
    )

    class Instance:
        pass

    inst = Instance()
    accessor.__set__(inst, np.array([1.0, 2.0, 3.0]))
    assert "flux" in inst.__pixel_data__
    np.testing.assert_array_equal(inst.__pixel_data__["flux"], [1.0, 2.0, 3.0])


def test_log_lambda_array_accessor_wavelength():
    """LogLambdaArrayAccessor should compute 10**(crval + cdelt * arange(naxis))."""
    from astra.fields import LogLambdaArrayAccessor

    crval = 3.5
    cdelt = 0.0001
    naxis = 100

    accessor = LogLambdaArrayAccessor(
        model=None,
        field=None,
        name="wavelength",
        ext=None,
        column_name="wavelength",
        crval=crval,
        cdelt=cdelt,
        naxis=naxis,
    )

    class Instance:
        pass

    inst = Instance()
    result = accessor.__get__(inst, type(inst))

    expected = 10 ** (crval + cdelt * np.arange(naxis))
    np.testing.assert_array_almost_equal(result, expected)
    assert len(result) == naxis


def test_log_lambda_array_accessor_caching():
    """LogLambdaArrayAccessor should cache the computed wavelength array."""
    from astra.fields import LogLambdaArrayAccessor

    accessor = LogLambdaArrayAccessor(
        model=None,
        field=None,
        name="wavelength",
        ext=None,
        column_name="wavelength",
        crval=3.5,
        cdelt=0.0001,
        naxis=10,
    )

    class Instance:
        pass

    inst = Instance()
    result1 = accessor.__get__(inst, type(inst))
    result2 = accessor.__get__(inst, type(inst))
    # Should be the exact same object (cached)
    assert result1 is result2


def test_log_lambda_array_accessor_returns_field_when_no_instance():
    """LogLambdaArrayAccessor should return the field when instance is None."""
    from astra.fields import LogLambdaArrayAccessor

    sentinel = object()
    accessor = LogLambdaArrayAccessor(
        model=None,
        field=sentinel,
        name="wavelength",
        ext=None,
        column_name="wavelength",
        crval=3.5,
        cdelt=0.0001,
        naxis=10,
    )

    result = accessor.__get__(None, None)
    assert result is sentinel


def test_pixel_array_accessor_fits_returns_field_when_no_instance():
    """PixelArrayAccessorFITS should return the field when instance is None."""
    from astra.fields import PixelArrayAccessorFITS

    sentinel = object()
    accessor = PixelArrayAccessorFITS(
        model=None, field=sentinel, name="flux", ext=1, column_name="FLUX"
    )
    result = accessor.__get__(None, None)
    assert result is sentinel


def test_pixel_array_accessor_hdf_returns_field_when_no_instance():
    """PixelArrayAccessorHDF should return the field when instance is None."""
    from astra.fields import PixelArrayAccessorHDF

    sentinel = object()
    accessor = PixelArrayAccessorHDF(
        model=None, field=sentinel, name="flux", ext=None, column_name="FLUX"
    )
    result = accessor.__get__(None, None)
    assert result is sentinel


def test_pickled_pixel_array_accessor_returns_field_when_no_instance():
    """PickledPixelArrayAccessor should return the field when instance is None."""
    from astra.fields import PickledPixelArrayAccessor

    sentinel = object()
    accessor = PickledPixelArrayAccessor(
        model=None, field=sentinel, name="flux", ext=None, column_name="flux"
    )
    result = accessor.__get__(None, None)
    assert result is sentinel


def test_flag_descriptor_clear():
    """FlagDescriptor.clear() should return a bin_and expression to clear the flag."""
    from peewee import Model, SqliteDatabase
    from astra.fields import BitField

    db = SqliteDatabase(":memory:")

    class FlagModel(Model):
        flags = BitField(default=0)
        flag_a = flags.flag()

        class Meta:
            database = db

    # clear() returns a SQL expression (bin_and with ~value)
    result = FlagModel.flag_a.clear()
    assert result is not None


def test_flag_descriptor_set():
    """FlagDescriptor.set() should return a bin_or expression to set the flag."""
    from peewee import Model, SqliteDatabase
    from astra.fields import BitField

    db = SqliteDatabase(":memory:")

    class FlagModel(Model):
        flags = BitField(default=0)
        flag_a = flags.flag()

        class Meta:
            database = db

    # set() returns a SQL expression (bin_or with value)
    result = FlagModel.flag_a.set()
    assert result is not None


def test_flag_descriptor_set_invalid_value():
    """FlagDescriptor.__set__ should raise ValueError for non-boolean values."""
    import pytest
    from peewee import Model, SqliteDatabase
    from astra.fields import BitField

    db = SqliteDatabase(":memory:")

    class FlagModel(Model):
        flags = BitField(default=0)
        flag_a = flags.flag()

        class Meta:
            database = db

    db.create_tables([FlagModel])
    instance = FlagModel.create(flags=0)

    with pytest.raises(ValueError, match="Value must be either True or False"):
        FlagModel.flag_a.__set__(instance, "not_a_bool")


def test_flag_descriptor_sql():
    """FlagDescriptor.__sql__ should produce a SQL context."""
    from peewee import Model, SqliteDatabase
    from astra.fields import BitField

    db = SqliteDatabase(":memory:")

    class FlagModel(Model):
        flags = BitField(default=0)
        flag_a = flags.flag()

        class Meta:
            database = db

    db.create_tables([FlagModel])

    # Use it in a query to exercise __sql__
    query = FlagModel.select().where(FlagModel.flag_a)
    sql_string = query.sql()
    assert sql_string is not None


def test_flag_descriptor_except_in_init():
    """FlagDescriptor should handle exceptions in inspect gracefully (lines 95-96)."""
    from unittest.mock import patch
    from astra.fields import BitField

    bf = BitField(default=0)

    # Force inspect.getouterframes to raise so the except branch is hit
    with patch("inspect.currentframe", side_effect=RuntimeError("mock error")):
        descriptor = bf.flag()

    # Should not raise, help_text should be None since inspect failed
    assert descriptor is not None
    assert descriptor.help_text is None


def test_flag_descriptor_get_and_set_on_instance():
    """FlagDescriptor.__get__ and __set__ should read/write flag bits on instances."""
    from peewee import Model, SqliteDatabase
    from astra.fields import BitField

    db = SqliteDatabase(":memory:")

    class FlagModel(Model):
        flags = BitField(default=0)
        flag_a = flags.flag()
        flag_b = flags.flag()

        class Meta:
            database = db

    db.create_tables([FlagModel])
    instance = FlagModel.create(flags=0)

    # __get__: flags should be False initially
    assert FlagModel.flag_a.__get__(instance, FlagModel) == False
    assert FlagModel.flag_b.__get__(instance, FlagModel) == False

    # __set__: set flag_a to True
    FlagModel.flag_a.__set__(instance, True)
    assert FlagModel.flag_a.__get__(instance, FlagModel) == True
    assert FlagModel.flag_b.__get__(instance, FlagModel) == False

    # __set__: set flag_a to False
    FlagModel.flag_a.__set__(instance, False)
    assert FlagModel.flag_a.__get__(instance, FlagModel) == False


def test_pixel_array_accessor_fits_exception_logging():
    """PixelArrayAccessorFITS should log and re-raise on file errors (lines 217-219)."""
    import pytest
    from astra.fields import PixelArrayAccessorFITS
    from unittest.mock import patch

    accessor = PixelArrayAccessorFITS(
        model=None, field=None, name="flux", ext=1, column_name="FLUX"
    )

    class Meta:
        pixel_fields = {"flux": accessor}

    class Instance:
        path = "/nonexistent/path/to/file.fits"
        _meta = Meta()

        def __repr__(self):
            return "Instance()"

    inst = Instance()

    with patch("astra.fields.expand_path", return_value="/nonexistent/path/to/file.fits"):
        with pytest.raises(Exception):
            accessor.__get__(inst, type(inst))


def test_pixel_array_bind():
    """PixelArray.bind should create accessor and register in pixel_fields."""
    from astra.fields import PixelArray, PixelArrayAccessorFITS

    pa = PixelArray(ext=1, column_name="FLUX", help_text="test flux")

    class Meta:
        pass

    class DummyModel:
        _meta = Meta()

    # bind should set the attribute and create pixel_fields
    pa.bind(DummyModel, "flux", set_attribute=True)

    assert hasattr(DummyModel, "flux")
    assert "flux" in DummyModel._meta.pixel_fields
    assert isinstance(DummyModel._meta.pixel_fields["flux"], PixelArrayAccessorFITS)


def test_pixel_array_bind_existing_pixel_fields():
    """PixelArray.bind should add to existing pixel_fields dict."""
    from astra.fields import PixelArray, PixelArrayAccessorFITS

    pa1 = PixelArray(ext=1, column_name="FLUX")
    pa2 = PixelArray(ext=2, column_name="IVAR")

    class Meta:
        pass

    class DummyModel:
        _meta = Meta()

    pa1.bind(DummyModel, "flux", set_attribute=True)
    pa2.bind(DummyModel, "ivar", set_attribute=True)

    assert "flux" in DummyModel._meta.pixel_fields
    assert "ivar" in DummyModel._meta.pixel_fields


def test_pixel_array_init():
    """PixelArray.__init__ should store all parameters."""
    from astra.fields import PixelArray, PixelArrayAccessorFITS

    transform_fn = lambda x, img, inst: x * 2
    pa = PixelArray(
        ext=1, column_name="FLUX", transform=transform_fn,
        accessor_class=PixelArrayAccessorFITS, help_text="flux help",
        accessor_kwargs={"extra": "value"}
    )

    assert pa.ext == 1
    assert pa.column_name == "FLUX"
    assert pa.transform is transform_fn
    assert pa.accessor_class is PixelArrayAccessorFITS
    assert pa.help_text == "flux help"
    assert pa.accessor_kwargs == {"extra": "value"}


def test_pickled_pixel_array_accessor_get_with_instance():
    """PickledPixelArrayAccessor.__get__ should load data from a pickle file."""
    import pickle
    import tempfile
    from unittest.mock import patch
    from astra.fields import PickledPixelArrayAccessor

    # Create a temporary pickle file
    data = {"flux": np.array([1.0, 2.0, 3.0]), "ivar": np.array([0.1, 0.2, 0.3])}
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        pickle.dump(data, f)
        pkl_path = f.name

    try:
        accessor_flux = PickledPixelArrayAccessor(
            model=None, field=None, name="flux", ext=None, column_name="flux"
        )

        class Instance:
            path = pkl_path

        inst = Instance()

        with patch("astra.fields.expand_path", return_value=pkl_path):
            result = accessor_flux.__get__(inst, type(inst))

        np.testing.assert_array_equal(result, data["flux"])

        # Second access should come from cache
        result2 = accessor_flux.__get__(inst, type(inst))
        np.testing.assert_array_equal(result2, data["flux"])
    finally:
        os.unlink(pkl_path)


def test_pixel_array_accessor_fits_get_with_instance_image_ext():
    """PixelArrayAccessorFITS.__get__ should load data from a FITS file (image access)."""
    import tempfile
    from unittest.mock import patch
    from astropy.io import fits
    from astra.fields import PixelArrayAccessorFITS

    flux_data = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)

    # Create a FITS file with an image extension
    hdu_primary = fits.PrimaryHDU()
    hdu_image = fits.ImageHDU(data=flux_data, name="FLUX")
    hdulist = fits.HDUList([hdu_primary, hdu_image])

    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as f:
        fits_path = f.name
        hdulist.writeto(fits_path, overwrite=True)

    try:
        accessor = PixelArrayAccessorFITS(
            model=None, field=None, name="flux", ext=1, column_name="FLUX"
        )

        class Meta:
            pixel_fields = {"flux": accessor}

        class Instance:
            path = fits_path
            _meta = Meta()

        inst = Instance()

        with patch("astra.fields.expand_path", return_value=fits_path):
            result = accessor.__get__(inst, type(inst))

        np.testing.assert_array_equal(result, flux_data)

        # Second call should return cached
        result2 = accessor.__get__(inst, type(inst))
        np.testing.assert_array_equal(result2, flux_data)
    finally:
        os.unlink(fits_path)


def test_pixel_array_accessor_fits_get_with_column_access():
    """PixelArrayAccessorFITS.__get__ should load data from a FITS table column."""
    import tempfile
    from unittest.mock import patch
    from astropy.io import fits
    from astra.fields import PixelArrayAccessorFITS

    flux_data = np.array([1.0, 2.0, 3.0], dtype=np.float32)

    # Create a FITS file with a binary table extension
    hdu_primary = fits.PrimaryHDU()
    col = fits.Column(name="FLUX", format="E", array=flux_data)
    hdu_table = fits.BinTableHDU.from_columns([col])
    hdulist = fits.HDUList([hdu_primary, hdu_table])

    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as f:
        fits_path = f.name
        hdulist.writeto(fits_path, overwrite=True)

    try:
        accessor = PixelArrayAccessorFITS(
            model=None, field=None, name="flux", ext=1, column_name="FLUX"
        )

        class Meta:
            pixel_fields = {"flux": accessor}

        class Instance:
            path = fits_path
            _meta = Meta()

        inst = Instance()

        with patch("astra.fields.expand_path", return_value=fits_path):
            result = accessor.__get__(inst, type(inst))

        np.testing.assert_array_equal(result, flux_data)
    finally:
        os.unlink(fits_path)


def test_pixel_array_accessor_fits_with_callable_ext():
    """PixelArrayAccessorFITS should support callable ext."""
    import tempfile
    from unittest.mock import patch
    from astropy.io import fits
    from astra.fields import PixelArrayAccessorFITS

    flux_data = np.array([10.0, 20.0], dtype=np.float32)

    hdu_primary = fits.PrimaryHDU()
    hdu_image = fits.ImageHDU(data=flux_data, name="FLUX")
    hdulist = fits.HDUList([hdu_primary, hdu_image])

    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as f:
        fits_path = f.name
        hdulist.writeto(fits_path, overwrite=True)

    try:
        accessor = PixelArrayAccessorFITS(
            model=None, field=None, name="flux",
            ext=lambda instance: 1,
            column_name="FLUX"
        )

        class Meta:
            pixel_fields = {"flux": accessor}

        class Instance:
            path = fits_path
            _meta = Meta()

        inst = Instance()

        with patch("astra.fields.expand_path", return_value=fits_path):
            result = accessor.__get__(inst, type(inst))

        np.testing.assert_array_equal(result, flux_data)
    finally:
        os.unlink(fits_path)


def test_pixel_array_accessor_fits_with_none_ext():
    """PixelArrayAccessorFITS should skip fields with ext=None."""
    import tempfile
    from unittest.mock import patch
    from astropy.io import fits
    from astra.fields import PixelArrayAccessorFITS

    flux_data = np.array([5.0, 6.0], dtype=np.float32)

    hdu_primary = fits.PrimaryHDU()
    hdu_image = fits.ImageHDU(data=flux_data, name="FLUX")
    hdulist = fits.HDUList([hdu_primary, hdu_image])

    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as f:
        fits_path = f.name
        hdulist.writeto(fits_path, overwrite=True)

    try:
        accessor_flux = PixelArrayAccessorFITS(
            model=None, field=None, name="flux", ext=1, column_name="FLUX"
        )
        accessor_none = PixelArrayAccessorFITS(
            model=None, field=None, name="other", ext=None, column_name="OTHER"
        )

        class Meta:
            pixel_fields = {"flux": accessor_flux, "other": accessor_none}

        class Instance:
            path = fits_path
            _meta = Meta()

        inst = Instance()

        with patch("astra.fields.expand_path", return_value=fits_path):
            result = accessor_flux.__get__(inst, type(inst))

        np.testing.assert_array_equal(result, flux_data)
        # "other" should not be in pixel_data since ext was None
        assert "other" not in inst.__pixel_data__
    finally:
        os.unlink(fits_path)


def test_pixel_array_accessor_fits_with_transform():
    """PixelArrayAccessorFITS should apply transform function."""
    import tempfile
    from unittest.mock import patch
    from astropy.io import fits
    from astra.fields import PixelArrayAccessorFITS

    flux_data = np.array([1.0, 2.0], dtype=np.float32)

    hdu_primary = fits.PrimaryHDU()
    hdu_image = fits.ImageHDU(data=flux_data, name="FLUX")
    hdulist = fits.HDUList([hdu_primary, hdu_image])

    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as f:
        fits_path = f.name
        hdulist.writeto(fits_path, overwrite=True)

    try:
        def my_transform(value, image, instance):
            return value * 10

        accessor = PixelArrayAccessorFITS(
            model=None, field=None, name="flux", ext=1, column_name="FLUX",
            transform=my_transform
        )

        class Meta:
            pixel_fields = {"flux": accessor}

        class Instance:
            path = fits_path
            _meta = Meta()

        inst = Instance()

        with patch("astra.fields.expand_path", return_value=fits_path):
            result = accessor.__get__(inst, type(inst))

        np.testing.assert_array_equal(result, flux_data * 10)
    finally:
        os.unlink(fits_path)


def test_pixel_array_accessor_hdf_get_with_instance():
    """PixelArrayAccessorHDF.__get__ should load data from an HDF5 file."""
    import tempfile
    import h5py
    from astra.fields import PixelArrayAccessorHDF

    flux_data = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    ivar_data = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as f:
        hdf_path = f.name

    with h5py.File(hdf_path, "w") as fp:
        fp.create_dataset("flux", data=np.array([flux_data, flux_data * 2]))
        fp.create_dataset("ivar", data=np.array([ivar_data, ivar_data * 2]))

    try:
        accessor_flux = PixelArrayAccessorHDF(
            model=None, field=None, name="flux", ext=None, column_name="flux"
        )
        accessor_ivar = PixelArrayAccessorHDF(
            model=None, field=None, name="ivar", ext=None, column_name="ivar"
        )

        class Meta:
            pixel_fields = {"flux": accessor_flux, "ivar": accessor_ivar}

        class Instance:
            path = hdf_path
            row_index = 0
            _meta = Meta()

        inst = Instance()
        result = accessor_flux.__get__(inst, type(inst))
        np.testing.assert_array_equal(result, flux_data)

        # ivar should also be loaded
        assert "ivar" in inst.__pixel_data__
        np.testing.assert_array_equal(inst.__pixel_data__["ivar"], ivar_data)

        # Second access should return cached
        result2 = accessor_flux.__get__(inst, type(inst))
        np.testing.assert_array_equal(result2, flux_data)
    finally:
        os.unlink(hdf_path)


def test_pixel_array_accessor_hdf_with_transform():
    """PixelArrayAccessorHDF should apply transform function."""
    import tempfile
    import h5py
    from astra.fields import PixelArrayAccessorHDF

    flux_data = np.array([1.0, 2.0, 3.0], dtype=np.float32)

    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as f:
        hdf_path = f.name

    with h5py.File(hdf_path, "w") as fp:
        fp.create_dataset("flux", data=np.array([flux_data]))

    try:
        accessor = PixelArrayAccessorHDF(
            model=None, field=None, name="flux", ext=None, column_name="flux",
            transform=lambda x: x * 100
        )

        class Meta:
            pixel_fields = {"flux": accessor}

        class Instance:
            path = hdf_path
            row_index = 0
            _meta = Meta()

        inst = Instance()
        result = accessor.__get__(inst, type(inst))
        np.testing.assert_array_equal(result, flux_data * 100)
    finally:
        os.unlink(hdf_path)
