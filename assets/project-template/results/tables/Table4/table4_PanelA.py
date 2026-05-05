# -----------------------------------------------------------------------------
# CLI/output bootstrap added for launcher compatibility
# -----------------------------------------------------------------------------
import argparse as _launcher_argparse
import atexit as _launcher_atexit
import builtins as _launcher_builtins
import io as _launcher_io
from pathlib import Path as _LauncherPath

import pandas as _launcher_pd

_LAUNCHER_SCRIPT_STEM = 'table4_PanelA'
_LAUNCHER_EXPECTED_PRIMARY_NAME = 'table4_PanelA.txt'
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
import numpy as np
import statsmodels.api as sm

# -----------------------------
# 1. Load the dataset
# -----------------------------
df = pd.read_stata("../../../data/raw/main_dataset.dta")

# -----------------------------
# 2. Variable setup for Table 4 Panel A
# -----------------------------
depvar = "listenplatz_norm"
treatment_col = "female_mayor"
running_col = "margin_1"
cluster_col = "gkz"
election_id_col = "gkz_jahr"

linear_controls = ["margin_1", "inter_1"]
quadratic_controls = ["margin_1", "inter_1", "margin_2", "inter_2"]

required_cols = [
    depvar,
    treatment_col,
    running_col,
    "rdd_sample",
    "female",
    cluster_col,
    election_id_col,
    *linear_controls,
    *quadratic_controls,
]

missing = [col for col in required_cols if col not in df.columns]
if missing:
    raise ValueError(f"Missing required columns: {missing}")

# -----------------------------
# 3. Keep RD sample and women only
# -----------------------------
base = df[(df["rdd_sample"] == 1) & (df["female"] == 1)].copy()

# -----------------------------
# 4. RD helper functions
# -----------------------------
def triangular_weights(x, h):
    w = 1 - np.abs(x) / h
    return np.where(np.abs(x) <= h, np.maximum(w, 0), 0)

def fit_rd_spec(data, h, poly="Linear"):
    temp = data[np.abs(data[running_col]) <= h].copy()

    if poly == "Linear":
        cols = [treatment_col, "margin_1", "inter_1"]
    elif poly == "Quadratic":
        cols = [treatment_col, "margin_1", "inter_1", "margin_2", "inter_2"]
    else:
        raise ValueError("poly must be 'Linear' or 'Quadratic'")

    temp = temp.dropna(subset=[depvar, cluster_col, election_id_col] + cols).copy()

    y = temp[depvar].astype(float)
    X = temp[cols].astype(float)

   # Add constant to the regression matrix
    X = sm.add_constant(X, has_constant="add")

    w = triangular_weights(temp[running_col].astype(float).to_numpy(), h)

    model = sm.WLS(y, X, weights=w)
    result = model.fit(cov_type="cluster", cov_kwds={"groups": temp[cluster_col]})

    coef = result.params[treatment_col]
    se = result.bse[treatment_col]
    pval = result.pvalues[treatment_col]

    return {
        "coef": coef,
        "se": se,
        "pval": pval,
        "N": len(temp),
        "Elections": temp[election_id_col].nunique(),
        "Municipalities": temp[cluster_col].nunique(),
        "Mean (SD)": f"{temp[depvar].mean():.2f} ({temp[depvar].std():.2f})",
    }

def stars(pval):
    if pval < 0.01:
        return "***"
    elif pval < 0.05:
        return "**"
    elif pval < 0.10:
        return "*"
    return ""

# -----------------------------
# 5. Table 4 Panel A specifications
# -----------------------------
specs = [
    {"col": "(1)", "bw_type": "CCT",   "h": 14.52, "poly": "Linear"},
    {"col": "(2)", "bw_type": "CCT/2", "h": 7.26,  "poly": "Linear"},
    {"col": "(3)", "bw_type": "2CCT",  "h": 29.04, "poly": "Linear"},
    {"col": "(4)", "bw_type": "IK",    "h": 17.17, "poly": "Linear"},
    {"col": "(5)", "bw_type": "CCT",   "h": 26.12, "poly": "Quadratic"},
]

# -----------------------------
# 6. Estimate all columns
# -----------------------------
results = []
for spec in specs:
    res = fit_rd_spec(base, h=spec["h"], poly=spec["poly"])
    res["bw_type"] = spec["bw_type"]
    res["bw_size"] = spec["h"]
    res["poly"] = spec["poly"]
    results.append(res)

# -----------------------------
# 7. Build final table
# -----------------------------
table_final = pd.DataFrame({
    "": [
        "female_mayor",
        "",
        "Bandwidth type",
        "Bandwidth size",
        "Polynomial",
        "N",
        "Elections",
        "Municipalities",
        "Mean (SD)",
    ],
    "(1)": [
        f"{results[0]['coef']:.3f}{stars(results[0]['pval'])}",
        f"({results[0]['se']:.3f})",
        results[0]["bw_type"],
        f"{results[0]['bw_size']:.2f}",
        results[0]["poly"],
        results[0]["N"],
        results[0]["Elections"],
        results[0]["Municipalities"],
        results[0]["Mean (SD)"],
    ],
    "(2)": [
        f"{results[1]['coef']:.3f}{stars(results[1]['pval'])}",
        f"({results[1]['se']:.3f})",
        results[1]["bw_type"],
        f"{results[1]['bw_size']:.2f}",
        results[1]["poly"],
        results[1]["N"],
        results[1]["Elections"],
        results[1]["Municipalities"],
        results[1]["Mean (SD)"],
    ],
    "(3)": [
        f"{results[2]['coef']:.3f}{stars(results[2]['pval'])}",
        f"({results[2]['se']:.3f})",
        results[2]["bw_type"],
        f"{results[2]['bw_size']:.2f}",
        results[2]["poly"],
        results[2]["N"],
        results[2]["Elections"],
        results[2]["Municipalities"],
        results[2]["Mean (SD)"],
    ],
    "(4)": [
        f"{results[3]['coef']:.3f}{stars(results[3]['pval'])}",
        f"({results[3]['se']:.3f})",
        results[3]["bw_type"],
        f"{results[3]['bw_size']:.2f}",
        results[3]["poly"],
        results[3]["N"],
        results[3]["Elections"],
        results[3]["Municipalities"],
        results[3]["Mean (SD)"],
    ],
    "(5)": [
        f"{results[4]['coef']:.3f}{stars(results[4]['pval'])}",
        f"({results[4]['se']:.3f})",
        results[4]["bw_type"],
        f"{results[4]['bw_size']:.2f}",
        results[4]["poly"],
        results[4]["N"],
        results[4]["Elections"],
        results[4]["Municipalities"],
        results[4]["Mean (SD)"],
    ],
})

# -----------------------------
# 8. Show table
# -----------------------------
display(table_final.style.hide(axis="index"))

# -----------------------------
# 9. Save the table
# -----------------------------
table_final.to_string("Table4_PanelA.txt", index=False)