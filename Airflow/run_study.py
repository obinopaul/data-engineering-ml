"""Execute the study's visible cells without starting a networked Jupyter kernel.

Uses the current shared .venv; saves real rich outputs to a separate notebook.
Run from main: python Airflow/run_study.py
"""
import argparse
import base64
import io
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def execute(output):
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        raise RuntimeError("Use main/.venv/bin/python")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
    os.environ.setdefault("IPYTHONDIR", str(ROOT / ".cache/ipython"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import nbformat
    from IPython.core.interactiveshell import InteractiveShell
    from IPython.display import display, Image
    from IPython.utils.capture import capture_output

    shell = InteractiveShell.instance()
    notebook = nbformat.read(ROOT / "oilfield_ml_case_study.ipynb", as_version=4)
    # Failed executions must not retain successful-looking outputs from an older run.
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    def show(*args, **kwargs):
        for number in plt.get_fignums():
            buffer = io.BytesIO()
            plt.figure(number).savefig(buffer, format="png", dpi=110, bbox_inches="tight")
            display(Image(data=buffer.getvalue()))

    plt.show = show
    count = 0
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        count += 1
        cell.outputs = []
        cell.execution_count = count
        print(f"Executing cell {count}: {cell.source.splitlines()[0][:85]}", flush=True)
        with capture_output() as captured:
            result = shell.run_cell(cell.source, store_history=False)
        for name, value in (("stdout", captured.stdout), ("stderr", captured.stderr)):
            if value:
                cell.outputs.append(nbformat.v4.new_output("stream", name=name, text=value))
        for rich in captured.outputs:
            data = dict(rich.data)
            for key, value in data.items():
                if isinstance(value, bytes):
                    data[key] = base64.b64encode(value).decode("ascii")
            cell.outputs.append(nbformat.v4.new_output("display_data", data=data, metadata=rich.metadata))
        nbformat.write(notebook, output)
        error = result.error_before_exec or result.error_in_exec
        if error:
            raise RuntimeError(f"Study cell {count} failed; outputs saved to {output}") from error
    nbformat.validate(notebook)
    print(f"Executed {count} code cells: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/oilfield_ml/study.executed.ipynb")
    execute(parser.parse_args().output)
