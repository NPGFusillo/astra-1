import ast
import os
import glob

import pytest


def _find_task_functions():
    """Find all @task-decorated functions in pipeline __init__.py files using AST parsing."""
    src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
    pattern = os.path.join(src_dir, "astra", "pipelines", "*", "__init__.py")

    # Pipelines to skip (e.g. deprecated or not maintained)
    skip_pipelines = {"slam_20240903"}

    results = []
    for path in sorted(glob.glob(pattern)):
        pipeline = os.path.basename(os.path.dirname(path))
        if pipeline in skip_pipelines:
            continue
        tree = ast.parse(open(path).read(), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            is_task = any(
                (isinstance(d, ast.Name) and d.id == "task")
                or (isinstance(d, ast.Attribute) and d.attr == "task")
                for d in node.decorator_list
            )
            if not is_task:
                continue

            results.append((pipeline, node.name, path, node))

    return results


_TASK_FUNCTIONS = _find_task_functions()


@pytest.mark.parametrize(
    "pipeline,func_name,path,node",
    _TASK_FUNCTIONS,
    ids=[f"{p}/{f}" for p, f, *_ in _TASK_FUNCTIONS],
)
def test_task_accepts_kwargs(pipeline, func_name, path, node):
    assert node.args.kwarg is not None, (
        f"@task function {func_name!r} in {path} must accept **kwargs"
    )
