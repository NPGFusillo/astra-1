
import os
os.environ["ASTRA_DATABASE_PATH"] = ":memory:"

import numpy as np
from queue import Queue
import pytest


# ---------------------------------------------------------------------------
# Tests for boss.py parsing utilities
# ---------------------------------------------------------------------------

def test_parse_space_separated_floats_mean_single_value():
    from astra.migrations.boss import _parse_space_separated_floats_mean
    result = _parse_space_separated_floats_mean(["3.14"])
    assert result.shape == (1,)
    assert np.isclose(result[0], 3.14)


def test_parse_space_separated_floats_mean_multiple_values():
    from astra.migrations.boss import _parse_space_separated_floats_mean
    result = _parse_space_separated_floats_mean(["1.0 3.0"])
    assert np.isclose(result[0], 2.0)


def test_parse_space_separated_floats_mean_empty_string():
    from astra.migrations.boss import _parse_space_separated_floats_mean
    result = _parse_space_separated_floats_mean([""])
    assert result.shape == (1,)
    assert np.isnan(result[0])


def test_parse_space_separated_floats_mean_batch():
    from astra.migrations.boss import _parse_space_separated_floats_mean
    arr = ["1.0 2.0 3.0", "10.0", "", "4.0 6.0"]
    result = _parse_space_separated_floats_mean(arr)
    assert result.shape == (4,)
    assert np.isclose(result[0], 2.0)
    assert np.isclose(result[1], 10.0)
    assert np.isnan(result[2])
    assert np.isclose(result[3], 5.0)


def test_parse_space_separated_floats_list_basic():
    from astra.migrations.boss import _parse_space_separated_floats_list
    result = _parse_space_separated_floats_list(["1.0 2.0 3.0"])
    assert result == [[1.0, 2.0, 3.0]]


def test_parse_space_separated_floats_list_empty():
    from astra.migrations.boss import _parse_space_separated_floats_list
    result = _parse_space_separated_floats_list([""])
    assert result == [[]]


def test_parse_space_separated_floats_list_single():
    from astra.migrations.boss import _parse_space_separated_floats_list
    result = _parse_space_separated_floats_list(["42.5"])
    assert result == [[42.5]]


def test_parse_space_separated_floats_list_batch():
    from astra.migrations.boss import _parse_space_separated_floats_list
    arr = ["1.0 2.0", "", "3.5"]
    result = _parse_space_separated_floats_list(arr)
    assert len(result) == 3
    assert result[0] == [1.0, 2.0]
    assert result[1] == []
    assert result[2] == [3.5]


# ---------------------------------------------------------------------------
# Tests for utils.py ProgressContext
# ---------------------------------------------------------------------------

def test_progress_context_no_queue_is_noop():
    from astra.migrations.utils import ProgressContext
    ctx = ProgressContext()
    assert not ctx.is_active
    # Should not raise even without a queue
    ctx.update(description="test", total=100, advance=1)


def test_progress_context_with_queue():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="task0")
    assert ctx.is_active
    ctx.update(description="working", total=50)
    msg = q.get(block=False)
    assert msg == ("update", "task0", {"description": "working", "total": 50})


def test_progress_context_update_advance():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="t1")
    ctx.update(advance=5)
    msg = q.get(block=False)
    assert msg == ("update", "t1", {"advance": 5})


def test_progress_context_update_completed():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="t1")
    ctx.update(completed=42)
    msg = q.get(block=False)
    assert msg == ("update", "t1", {"completed": 42})


def test_progress_context_update_empty_is_noop():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="t1")
    ctx.update()  # no args
    assert q.empty()


def test_progress_context_put_dict():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="t1")
    ctx.put({"description": "hi", "total": 10})
    msg = q.get(block=False)
    assert msg == ("update", "t1", {"description": "hi", "total": 10})


def test_progress_context_put_ellipsis():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="t1")
    ctx.put(Ellipsis)
    msg = q.get(block=False)
    assert msg is Ellipsis


def test_progress_context_put_noop_without_queue():
    from astra.migrations.utils import ProgressContext
    ctx = ProgressContext()
    ctx.put({"advance": 1})
    ctx.put(Ellipsis)
    # No error raised


def test_subtask_context_manager():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="main")

    with ctx.subtask("phase1", total=10) as sub:
        sub.update(advance=3)
        sub.update(advance=7)

    messages = []
    while not q.empty():
        messages.append(q.get(block=False))

    # First message: add_subtask
    assert messages[0][0] == "add_subtask"
    assert messages[0][1] == "main.0"  # subtask_id
    assert messages[0][2] == "main"  # parent_id
    assert messages[0][3]["description"] == "phase1"
    assert messages[0][3]["total"] == 10

    # Next two: updates
    assert messages[1] == ("update", "main.0", {"advance": 3})
    assert messages[2] == ("update", "main.0", {"advance": 7})

    # Last: complete_subtask
    assert messages[3] == ("complete_subtask", "main.0")


def test_subtask_ids_increment():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="t")

    with ctx.subtask("a", total=1) as s1:
        pass
    with ctx.subtask("b", total=2) as s2:
        pass

    messages = []
    while not q.empty():
        messages.append(q.get(block=False))

    # First subtask gets id "t.0", second gets "t.1"
    add_msgs = [m for m in messages if m[0] == "add_subtask"]
    assert add_msgs[0][1] == "t.0"
    assert add_msgs[1][1] == "t.1"


def test_subtask_explicit_complete():
    from astra.migrations.utils import ProgressContext
    q = Queue()
    ctx = ProgressContext(queue=q, task_id="t")

    with ctx.subtask("x", total=5) as sub:
        sub.complete()
        # __exit__ should NOT send another complete_subtask

    messages = []
    while not q.empty():
        messages.append(q.get(block=False))

    complete_msgs = [m for m in messages if m[0] == "complete_subtask"]
    assert len(complete_msgs) == 1


def test_subtask_inactive_is_noop():
    from astra.migrations.utils import ProgressContext
    ctx = ProgressContext()  # no queue
    with ctx.subtask("x", total=5) as sub:
        assert not sub.is_active
        sub.update(advance=1)
        sub.complete()


def test_noqueue_alias():
    from astra.migrations.utils import NoQueue, ProgressContext
    assert NoQueue is ProgressContext


# ---------------------------------------------------------------------------
# Tests for scheduler.py pure functions
# ---------------------------------------------------------------------------

def test_migration_task_dataclass():
    from astra.migrations.scheduler import MigrationTask
    task = MigrationTask(
        name="test",
        func=lambda: None,
        description="A test task",
        depends_on={"other"},
        writes_to={"table_a"},
    )
    assert task.name == "test"
    assert task.depends_on == {"other"}
    assert task.writes_to == {"table_a"}
    assert task.exclusive is False
    assert task.args == ()
    assert task.kwargs == {}


def test_migration_task_defaults():
    from astra.migrations.scheduler import MigrationTask
    task = MigrationTask(name="t", func=lambda: None, description="d")
    assert task.depends_on == set()
    assert task.writes_to == set()
    assert task.exclusive is False
    assert task.args == ()
    assert task.kwargs == {}


def test_get_satisfiable_tasks_all_satisfiable():
    from astra.migrations.scheduler import MigrationTask, get_satisfiable_tasks
    tasks = {
        "a": MigrationTask(name="a", func=lambda: None, description="A"),
        "b": MigrationTask(name="b", func=lambda: None, description="B", depends_on={"a"}),
    }
    result = get_satisfiable_tasks(tasks)
    assert set(result.keys()) == {"a", "b"}


def test_get_satisfiable_tasks_removes_unsatisfiable():
    from astra.migrations.scheduler import MigrationTask, get_satisfiable_tasks
    tasks = {
        "a": MigrationTask(name="a", func=lambda: None, description="A"),
        "b": MigrationTask(name="b", func=lambda: None, description="B", depends_on={"missing"}),
    }
    result = get_satisfiable_tasks(tasks)
    assert set(result.keys()) == {"a"}


def test_get_satisfiable_tasks_cascading_removal():
    from astra.migrations.scheduler import MigrationTask, get_satisfiable_tasks
    tasks = {
        "a": MigrationTask(name="a", func=lambda: None, description="A"),
        "b": MigrationTask(name="b", func=lambda: None, description="B", depends_on={"missing"}),
        "c": MigrationTask(name="c", func=lambda: None, description="C", depends_on={"b"}),
    }
    result = get_satisfiable_tasks(tasks)
    # b depends on missing, c depends on b, so both removed
    assert set(result.keys()) == {"a"}


def test_get_satisfiable_tasks_empty():
    from astra.migrations.scheduler import get_satisfiable_tasks
    assert get_satisfiable_tasks({}) == {}


def test_scheduler_get_ready_tasks_no_deps():
    from astra.migrations.scheduler import MigrationTask, MigrationScheduler
    from unittest.mock import MagicMock
    tasks = {
        "a": MigrationTask(name="a", func=lambda: None, description="A"),
        "b": MigrationTask(name="b", func=lambda: None, description="B"),
    }
    scheduler = MigrationScheduler(tasks, progress=MagicMock(), linger_time=0)
    ready = scheduler.get_ready_tasks()
    assert set(ready) == {"a", "b"}


def test_scheduler_get_ready_tasks_with_deps():
    from astra.migrations.scheduler import MigrationTask, MigrationScheduler
    from unittest.mock import MagicMock
    tasks = {
        "a": MigrationTask(name="a", func=lambda: None, description="A"),
        "b": MigrationTask(name="b", func=lambda: None, description="B", depends_on={"a"}),
    }
    scheduler = MigrationScheduler(tasks, progress=MagicMock(), linger_time=0)
    ready = scheduler.get_ready_tasks()
    assert ready == ["a"]

    # Simulate completing "a"
    scheduler.pending.remove("a")
    scheduler.completed.add("a")
    ready = scheduler.get_ready_tasks()
    assert ready == ["b"]


def test_scheduler_get_ready_tasks_write_conflict():
    from astra.migrations.scheduler import MigrationTask, MigrationScheduler
    from unittest.mock import MagicMock
    tasks = {
        "a": MigrationTask(name="a", func=lambda: None, description="A", writes_to={"table1"}),
        "b": MigrationTask(name="b", func=lambda: None, description="B", writes_to={"table1"}),
    }
    scheduler = MigrationScheduler(tasks, progress=MagicMock(), linger_time=0)
    # Simulate "a" running and writing to table1
    scheduler.pending.remove("a")
    scheduler.running["a"] = (None, None, None)
    scheduler.tables_being_written.add("table1")

    ready = scheduler.get_ready_tasks()
    assert "b" not in ready  # b can't start while table1 is being written


def test_scheduler_get_ready_tasks_exclusive():
    from astra.migrations.scheduler import MigrationTask, MigrationScheduler
    from unittest.mock import MagicMock
    tasks = {
        "a": MigrationTask(name="a", func=lambda: None, description="A"),
        "excl": MigrationTask(name="excl", func=lambda: None, description="Exclusive", exclusive=True),
    }
    scheduler = MigrationScheduler(tasks, progress=MagicMock(), linger_time=0)

    # If something is already running, exclusive task should not be ready
    scheduler.pending.remove("a")
    scheduler.running["a"] = (None, None, None)
    ready = scheduler.get_ready_tasks()
    assert "excl" not in ready


def test_scheduler_exclusive_blocks_others():
    from astra.migrations.scheduler import MigrationTask, MigrationScheduler
    from unittest.mock import MagicMock
    tasks = {
        "a": MigrationTask(name="a", func=lambda: None, description="A"),
        "excl": MigrationTask(name="excl", func=lambda: None, description="Exclusive", exclusive=True),
    }
    scheduler = MigrationScheduler(tasks, progress=MagicMock(), linger_time=0)
    scheduler.exclusive_running = True
    ready = scheduler.get_ready_tasks()
    assert ready == []


# ---------------------------------------------------------------------------
# Tests for von lambda (misc.py / reddening.py)
# ---------------------------------------------------------------------------

def test_von_with_value():
    from astra.migrations.misc import von
    assert von(3.14) == 3.14
    assert von(0) is np.nan  # 0 is falsy, so von returns nan


def test_von_with_none():
    from astra.migrations.misc import von
    assert np.isnan(von(None))


def test_von_with_false():
    from astra.migrations.misc import von
    assert np.isnan(von(False))
