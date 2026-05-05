from __future__ import annotations
# -----------------------------------------------------------------------------
# CLI/output bootstrap added for launcher compatibility
# -----------------------------------------------------------------------------
import argparse as _launcher_argparse
import atexit as _launcher_atexit
import builtins as _launcher_builtins
import io as _launcher_io
from pathlib import Path as _LauncherPath

import pandas as _launcher_pd

_LAUNCHER_SCRIPT_STEM = 'table1_partA'
_LAUNCHER_EXPECTED_PRIMARY_NAME = 'Table1_PartA.txt'
_LAUNCHER_SPECIAL_MULTI_OUTPUT = False

_launcher_parser = _launcher_argparse.ArgumentParser(add_help=False)
_launcher_parser.add_argument('datasets', nargs='*')
_launcher_parser.add_argument('--output-dir', dest='output_dir', default='.')
_launcher_args, _launcher_unknown = _launcher_parser.parse_known_args()

_LAUNCHER_DATASET_PATHS = [
    _LauncherPath(p).expanduser().resolve()
    for p in (_launcher_args.datasets or [])
]
_LAUNCHER_OUTPUT_DIR = _LauncherPath(_launcher_args.output_dir).expanduser().resolve()
_LAUNCHER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_LAUNCHER_EXPECTED_PRIMARY_PATH = _LAUNCHER_OUTPUT_DIR / _LAUNCHER_EXPECTED_PRIMARY_NAME

if _LAUNCHER_EXPECTED_PRIMARY_PATH.exists():
    try:
        _LAUNCHER_EXPECTED_PRIMARY_PATH.unlink()
    except OSError:
        pass

_LAUNCHER_DATASET_BY_BASENAME = {p.name: p for p in _LAUNCHER_DATASET_PATHS}
_LAUNCHER_DATASET_DIRS = []
for _p in _LAUNCHER_DATASET_PATHS:
    if _p.parent not in _LAUNCHER_DATASET_DIRS:
        _LAUNCHER_DATASET_DIRS.append(_p.parent)

_LAUNCHER_READ_INDEX = 0
_LAUNCHER_WRITTEN_OUTPUTS = []
_LAUNCHER_STDOUT_BUFFER = _launcher_io.StringIO()
_LAUNCHER_ORIG_PRINT = _launcher_builtins.print
_LAUNCHER_ORIG_OPEN = _launcher_builtins.open
_LAUNCHER_ORIG_READ_STATA = _launcher_pd.read_stata
_LAUNCHER_ORIG_READ_CSV = getattr(_launcher_pd, 'read_csv', None)
_LAUNCHER_ORIG_TO_STRING = _launcher_pd.DataFrame.to_string
_LAUNCHER_ORIG_TO_CSV = _launcher_pd.DataFrame.to_csv
_LAUNCHER_ORIG_TO_EXCEL = _launcher_pd.DataFrame.to_excel


def _launcher_resolve_input_path(requested):
    global _LAUNCHER_READ_INDEX
    requested_path = _LauncherPath(str(requested))
    basename = requested_path.name

    if basename in _LAUNCHER_DATASET_BY_BASENAME:
        return _LAUNCHER_DATASET_BY_BASENAME[basename]

    for dataset_dir in _LAUNCHER_DATASET_DIRS:
        candidate = dataset_dir / basename
        if candidate.exists():
            return candidate

    if _LAUNCHER_READ_INDEX < len(_LAUNCHER_DATASET_PATHS):
        candidate = _LAUNCHER_DATASET_PATHS[_LAUNCHER_READ_INDEX]
        _LAUNCHER_READ_INDEX += 1
        return candidate

    return requested


def _launcher_redirect_output_path(path_like):
    path_obj = _LauncherPath(path_like)
    if path_obj.is_absolute():
        resolved = path_obj
    else:
        resolved = _LAUNCHER_OUTPUT_DIR / path_obj.name
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _launcher_track_output(path_obj):
    resolved = _LauncherPath(path_obj).resolve()
    if resolved not in _LAUNCHER_WRITTEN_OUTPUTS:
        _LAUNCHER_WRITTEN_OUTPUTS.append(resolved)
    return resolved


def _launcher_print(*args, **kwargs):
    _LAUNCHER_ORIG_PRINT(*args, **kwargs)
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    text = sep.join(str(arg) for arg in args) + end
    _LAUNCHER_STDOUT_BUFFER.write(text)


def display(*args, **kwargs):
    for arg in args:
        _launcher_print(arg)


def _launcher_open(file, mode='r', *args, **kwargs):
    if any(flag in mode for flag in ('w', 'a', 'x')) and isinstance(file, (str, _LauncherPath)):
        suffix = _LauncherPath(str(file)).suffix.lower()
        if suffix in {'.txt', '.csv', '.xlsx', '.xls'}:
            redirected = _launcher_track_output(_launcher_redirect_output_path(file))
            return _LAUNCHER_ORIG_OPEN(redirected, mode, *args, **kwargs)
    return _LAUNCHER_ORIG_OPEN(file, mode, *args, **kwargs)


def _launcher_read_stata(*args, **kwargs):
    if args:
        resolved = _launcher_resolve_input_path(args[0])
        args = (resolved, *args[1:])
    elif 'filepath_or_buffer' in kwargs:
        kwargs['filepath_or_buffer'] = _launcher_resolve_input_path(kwargs['filepath_or_buffer'])
    return _LAUNCHER_ORIG_READ_STATA(*args, **kwargs)


def _launcher_read_csv(*args, **kwargs):
    if args:
        resolved = _launcher_resolve_input_path(args[0])
        args = (resolved, *args[1:])
    elif 'filepath_or_buffer' in kwargs:
        kwargs['filepath_or_buffer'] = _launcher_resolve_input_path(kwargs['filepath_or_buffer'])
    return _LAUNCHER_ORIG_READ_CSV(*args, **kwargs)


def _launcher_to_string(self, buf=None, *args, **kwargs):
    if isinstance(buf, (str, _LauncherPath)):
        redirected = _launcher_track_output(_launcher_redirect_output_path(buf))
        encoding = kwargs.pop('encoding', 'utf-8')
        with _LAUNCHER_ORIG_OPEN(redirected, 'w', encoding=encoding) as fh:
            return _LAUNCHER_ORIG_TO_STRING(self, buf=fh, *args, **kwargs)
    return _LAUNCHER_ORIG_TO_STRING(self, buf=buf, *args, **kwargs)


def _launcher_to_csv(self, path_or_buf=None, *args, **kwargs):
    if isinstance(path_or_buf, (str, _LauncherPath)):
        redirected = _launcher_track_output(_launcher_redirect_output_path(path_or_buf))
        return _LAUNCHER_ORIG_TO_CSV(self, path_or_buf=redirected, *args, **kwargs)
    return _LAUNCHER_ORIG_TO_CSV(self, path_or_buf=path_or_buf, *args, **kwargs)


def _launcher_to_excel(self, excel_writer, *args, **kwargs):
    if isinstance(excel_writer, (str, _LauncherPath)):
        redirected = _launcher_track_output(_launcher_redirect_output_path(excel_writer))
        return _LAUNCHER_ORIG_TO_EXCEL(self, excel_writer=redirected, *args, **kwargs)
    return _LAUNCHER_ORIG_TO_EXCEL(self, excel_writer, *args, **kwargs)


def _launcher_finalize_expected_output():
    if _LAUNCHER_EXPECTED_PRIMARY_PATH.exists():
        return

    txt_outputs = [p for p in _LAUNCHER_WRITTEN_OUTPUTS if p.suffix.lower() == '.txt' and p.exists()]

    for candidate in txt_outputs:
        if candidate.name.lower() == _LAUNCHER_EXPECTED_PRIMARY_NAME.lower():
            _LAUNCHER_EXPECTED_PRIMARY_PATH.write_text(candidate.read_text(encoding='utf-8'), encoding='utf-8')
            return

    if len(txt_outputs) == 1:
        _LAUNCHER_EXPECTED_PRIMARY_PATH.write_text(txt_outputs[0].read_text(encoding='utf-8'), encoding='utf-8')
        return

    stdout_text = _LAUNCHER_STDOUT_BUFFER.getvalue()
    if stdout_text.strip():
        _LAUNCHER_EXPECTED_PRIMARY_PATH.write_text(stdout_text, encoding='utf-8')


_launcher_builtins.print = _launcher_print
_launcher_builtins.open = _launcher_open
_launcher_pd.read_stata = _launcher_read_stata
if _LAUNCHER_ORIG_READ_CSV is not None:
    _launcher_pd.read_csv = _launcher_read_csv
_launcher_pd.DataFrame.to_string = _launcher_to_string
_launcher_pd.DataFrame.to_csv = _launcher_to_csv
_launcher_pd.DataFrame.to_excel = _launcher_to_excel
_launcher_atexit.register(_launcher_finalize_expected_output)
# -----------------------------------------------------------------------------

import pandas as pd

# -----------------------------
# 1. Load the dataset
# -----------------------------
df = pd.read_stata("../../../data/raw/main_dataset.dta")

# -----------------------------
# 2. Variables
# -----------------------------
variables = [
    "gewinn_norm",
    "listenplatz_norm",
    "age",
    "non_university_phd",
    "university",
    "phd",
    "architect",
    "businessmanwoman",
    "engineer",
    "lawyer",
    "civil_administration",
    "teacher",
    "employed",
    "selfemployed",
    "student",
    "retired",
    "housewifehusband",
]

labels = {
    "gewinn_norm": "Rank change (normalized)",
    "listenplatz_norm": "Initial list rank (normalized)",
    "age": "Age",
    "non_university_phd": "High school",
    "university": "University",
    "phd": "Phd",
    "architect": "Architect",
    "businessmanwoman": "Businesswoman/-man",
    "engineer": "Engineer",
    "lawyer": "Lawyer",
    "civil_administration": "Civil administration",
    "teacher": "Teacher",
    "employed": "Employed",
    "selfemployed": "Self-employed",
    "student": "Student",
    "retired": "Retired",
    "housewifehusband": "Housewife/-husband",
}

# -----------------------------
# 3. Descriptive statistics
# -----------------------------
table = df[variables].describe().T
table = table[["count", "mean", "std", "min", "max"]]
table.columns = ["N", "Mean", "Std.Dev", "Min", "Max"]
table["Variable"] = table.index.map(labels)
table = table[["Variable", "N", "Mean", "Std.Dev", "Min", "Max"]]
table = table.round(3)

# -----------------------------
# 4. Add final row: total N
# -----------------------------
final_row = pd.DataFrame([{
    "Variable": "N",
    "N": len(df),
    "Mean": "",
    "Std.Dev": "",
    "Min": "",
    "Max": "",
}])

table = pd.concat([table, final_row], ignore_index=True)

# -----------------------------
# 5. Show table
# -----------------------------
table

# -----------------------------
# 6. Save the table
# -----------------------------
table.to_string("Table1_PartA.txt", index=False)