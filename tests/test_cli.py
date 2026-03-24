"""Tests for the astra CLI module."""

import os

# Set up in-memory database before importing astra modules.
os.environ["ASTRA_DATABASE_PATH"] = ":memory:"

import pytest
from typer.testing import CliRunner

from astra.cli.astra import (
    app,
    config_app,
    _get_nested_value,
    _set_nested_value,
    _format_config,
    Product,
    USER_CONFIG_FILE,
)


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestGetNestedValue:
    def test_simple_key(self):
        d = {"a": 1, "b": 2}
        assert _get_nested_value(d, "a") == 1

    def test_nested_key(self):
        d = {"database": {"host": "localhost", "port": 5432}}
        assert _get_nested_value(d, "database.host") == "localhost"
        assert _get_nested_value(d, "database.port") == 5432

    def test_deeply_nested_key(self):
        d = {"a": {"b": {"c": {"d": 42}}}}
        assert _get_nested_value(d, "a.b.c.d") == 42

    def test_missing_key_returns_none(self):
        d = {"a": 1}
        assert _get_nested_value(d, "b") is None

    def test_missing_nested_key_returns_none(self):
        d = {"a": {"b": 1}}
        assert _get_nested_value(d, "a.c") is None

    def test_partial_path_missing(self):
        d = {"a": 1}
        assert _get_nested_value(d, "a.b") is None

    def test_returns_sub_dict(self):
        d = {"a": {"b": 1, "c": 2}}
        assert _get_nested_value(d, "a") == {"b": 1, "c": 2}

    def test_empty_dict(self):
        assert _get_nested_value({}, "a") is None


class TestSetNestedValue:
    def test_simple_key(self):
        d = {}
        _set_nested_value(d, "a", 1)
        assert d == {"a": 1}

    def test_nested_key(self):
        d = {}
        _set_nested_value(d, "database.host", "localhost")
        assert d == {"database": {"host": "localhost"}}

    def test_deeply_nested_key(self):
        d = {}
        _set_nested_value(d, "a.b.c.d", 42)
        assert d == {"a": {"b": {"c": {"d": 42}}}}

    def test_overwrite_existing(self):
        d = {"a": {"b": 1}}
        _set_nested_value(d, "a.b", 2)
        assert d["a"]["b"] == 2

    def test_add_to_existing(self):
        d = {"a": {"b": 1}}
        _set_nested_value(d, "a.c", 2)
        assert d == {"a": {"b": 1, "c": 2}}


class TestFormatConfig:
    def test_flat_dict(self):
        d = {"host": "localhost", "port": 5432}
        result = _format_config(d)
        assert "host: localhost" in result
        assert "port: 5432" in result

    def test_nested_dict(self):
        d = {"database": {"host": "localhost"}}
        result = _format_config(d)
        assert "database:" in result
        assert "  host: localhost" in result

    def test_empty_dict(self):
        assert _format_config({}) == ""

    def test_indentation(self):
        d = {"a": {"b": {"c": "val"}}}
        result = _format_config(d)
        lines = result.split("\n")
        assert lines[0] == "a:"
        assert lines[1] == "  b:"
        assert lines[2] == "    c: val"


# ---------------------------------------------------------------------------
# Tests for the Product enum
# ---------------------------------------------------------------------------


class TestProductEnum:
    def test_product_values(self):
        assert Product.mwmTargets.value == "mwmTargets"
        assert Product.mwmAllStar.value == "mwmAllStar"

    def test_product_is_string_enum(self):
        assert isinstance(Product.mwmTargets, str)

    def test_all_products_have_unique_values(self):
        values = [p.value for p in Product]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# CLI command tests using CliRunner
# ---------------------------------------------------------------------------


class TestVersionCommand:
    def test_version_output(self, runner):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Astra version:" in result.output

    def test_version_contains_digits(self, runner):
        result = runner.invoke(app, ["version"])
        # Version string should contain at least one digit.
        version_str = result.output.split(":")[-1].strip()
        assert any(c.isdigit() for c in version_str)


class TestConfigCommands:
    def test_config_show(self, runner):
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0

    def test_config_path(self, runner):
        result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        assert "User config file:" in result.output
        assert "astra.yml" in result.output

    def test_config_get_missing_key(self, runner):
        result = runner.invoke(app, ["config", "get", "nonexistent.key.here"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_config_get_no_arg(self, runner):
        result = runner.invoke(app, ["config", "get"])
        assert result.exit_code != 0


class TestHelpOutput:
    def test_main_help(self, runner):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "version" in result.output
        assert "config" in result.output
        assert "create" in result.output

    def test_config_help(self, runner):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "show" in result.output
        assert "get" in result.output
        assert "set" in result.output
        assert "path" in result.output

    def test_version_help(self, runner):
        result = runner.invoke(app, ["version", "--help"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()

    def test_create_help(self, runner):
        result = runner.invoke(app, ["create", "--help"])
        assert result.exit_code == 0
        assert "product" in result.output.lower()


class TestAppStructure:
    def test_app_is_typer_instance(self):
        import typer
        assert isinstance(app, typer.Typer)

    def test_config_app_is_typer_instance(self):
        import typer
        assert isinstance(config_app, typer.Typer)

    def test_app_has_registered_commands(self):
        # Typer stores registered commands/groups; verify key ones exist.
        command_names = []
        for info in app.registered_commands:
            if info.name:
                command_names.append(info.name)
            elif info.callback:
                command_names.append(info.callback.__name__)
        assert "version" in command_names

    def test_config_subcommands(self):
        command_names = []
        for info in config_app.registered_commands:
            if info.name:
                command_names.append(info.name)
            elif info.callback:
                command_names.append(info.callback.__name__)
        assert "show" in command_names
        assert "get" in command_names
        assert "set" in command_names
        assert "path" in command_names


# ---------------------------------------------------------------------------
# Test the casload CLI module can be imported
# ---------------------------------------------------------------------------


class TestCasloadImport:
    def test_casload_app_exists(self):
        from astra.cli.casload import app as casload_app
        import typer
        assert isinstance(casload_app, typer.Typer)

    def test_casload_help(self):
        from astra.cli.casload import app as casload_app
        runner = CliRunner()
        result = runner.invoke(casload_app, ["--help"])
        assert result.exit_code == 0
        assert "FITS" in result.output or "CasJobs" in result.output or "table" in result.output.lower()
