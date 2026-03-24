
import os
os.environ["ASTRA_DATABASE_PATH"] = ":memory:"

import json
import pytest


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

def test_import_operators_module():
    from astra.operators import Operator
    assert Operator is not None


def test_import_slurm_module():
    from astra.operators.slurm import SlurmSensor
    assert SlurmSensor is not None


# ---------------------------------------------------------------------------
# Operator.__init__ tests
# ---------------------------------------------------------------------------

def test_operator_default_attributes():
    from astra.operators import Operator
    op = Operator(task_id="t", task_name="my_task")
    assert op.task_name == "my_task"
    assert op.model_name is None
    assert op.task_kwargs == {}
    assert op.where is None
    assert op.limit is None


def test_operator_task_kwargs_default_is_empty_dict():
    """Passing task_kwargs=None should default to an empty dict."""
    from astra.operators import Operator
    op = Operator(task_id="t", task_name="x", task_kwargs=None)
    assert op.task_kwargs == {}


def test_operator_task_kwargs_not_shared_between_instances():
    """Each Operator must get its own dict, not a shared mutable default."""
    from astra.operators import Operator
    op1 = Operator(task_id="t1", task_name="x")
    op2 = Operator(task_id="t2", task_name="x")
    op1.task_kwargs["key"] = "value"
    assert "key" not in op2.task_kwargs


def test_operator_custom_attributes():
    from astra.operators import Operator
    kw = {"a": 1}
    op = Operator(
        task_id="t",
        task_name="task",
        model_name="MyModel",
        task_kwargs=kw,
        where={"flag": 0},
        limit=100,
    )
    assert op.task_name == "task"
    assert op.model_name == "MyModel"
    assert op.task_kwargs == {"a": 1}
    assert op.where == {"flag": 0}
    assert op.limit == 100


def test_operator_template_fields():
    from astra.operators import Operator
    expected = {"task_kwargs", "limit", "model_name", "where"}
    assert set(Operator.template_fields) == expected


# ---------------------------------------------------------------------------
# SlurmSensor.__init__ / template_fields
# ---------------------------------------------------------------------------

def test_slurm_sensor_stores_job_ids():
    from astra.operators.slurm import SlurmSensor
    s = SlurmSensor(task_id="t", job_ids="42 99")
    assert s.job_ids == "42 99"


def test_slurm_sensor_template_fields():
    from astra.operators.slurm import SlurmSensor
    assert "job_ids" in SlurmSensor.template_fields


# ---------------------------------------------------------------------------
# SlurmSensor.poke — job-ID parsing logic
# Only the "no valid IDs" path can be tested without a real Slurm queue.
# ---------------------------------------------------------------------------

def test_slurm_sensor_poke_returns_true_for_invalid_ids():
    """When job_ids cannot be parsed, poke returns True (nothing to wait on)."""
    from astra.operators.slurm import SlurmSensor
    s = SlurmSensor(task_id="t", job_ids="not-a-number")
    assert s.poke(context={}) is True


def test_slurm_sensor_poke_returns_true_for_empty_string():
    from astra.operators.slurm import SlurmSensor
    s = SlurmSensor(task_id="t", job_ids="")
    assert s.poke(context={}) is True


# ---------------------------------------------------------------------------
# Operator.where_by_execution_date edge cases
# ---------------------------------------------------------------------------

def test_where_by_execution_date_returns_none_when_left_key_is_none():
    """If either execution-date bound is None the method should return None."""
    from astra.operators import Operator
    op = Operator(task_id="t", task_name="x")
    ctx = {"prev_execution_date": None, "execution_date": "2024-01-01"}
    result = op.where_by_execution_date(object, ctx)
    assert result is None


def test_where_by_execution_date_returns_none_when_right_key_is_none():
    from astra.operators import Operator
    op = Operator(task_id="t", task_name="x")
    ctx = {"prev_execution_date": "2024-01-01", "execution_date": None}
    result = op.where_by_execution_date(object, ctx)
    assert result is None


def test_where_by_execution_date_returns_none_when_both_none():
    from astra.operators import Operator
    op = Operator(task_id="t", task_name="x")
    ctx = {"prev_execution_date": None, "execution_date": None}
    result = op.where_by_execution_date(object, ctx)
    assert result is None


def test_where_by_execution_date_returns_none_for_model_without_date_attrs():
    """If the model has none of mjd/date_obs/max_mjd, return None."""
    from astra.operators import Operator
    op = Operator(task_id="t", task_name="x")

    class FakeModel:
        pass

    ctx = {"prev_execution_date": "2024-01-01", "execution_date": "2024-01-02"}
    result = op.where_by_execution_date(FakeModel, ctx)
    assert result is None
