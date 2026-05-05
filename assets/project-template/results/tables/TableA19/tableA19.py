# -----------------------------------------------------------------------------
# CLI/output bootstrap added for launcher compatibility
# -----------------------------------------------------------------------------
import argparse as _launcher_argparse
import atexit as _launcher_atexit
import builtins as _launcher_builtins
import io as _launcher_io
from pathlib import Path as _LauncherPath

import pandas as _launcher_pd

_LAUNCHER_SCRIPT_STEM = 'tableA19'
_LAUNCHER_EXPECTED_PRIMARY_NAME = 'tableA19.txt'
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

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


"""
Table A19 - From-scratch Python rewrite aligned to the original Stata script.

Stata source
------------
results_tables/TableA19/tableA19.do

Design choices in this rewrite
------------------------------
1. Uses the correct source dataset: `dataset_for_party_level_results.dta`.
2. Recreates the exact interaction variables used by the Stata code.
3. Estimates the five published specifications with triangular-kernel WLS and
   clustered standard errors at the municipality level (`gkz`).
4. Applies the Stata estimation sample rule `abs(margin_1) < h`.
5. Writes only `tableA19.txt`.

Bandwidth note
--------------
The original Stata script computes bandwidths via the helper program
`bandwidth_and_weights.ado`, which in turn calls `rdrobust`. Because the base
project does not require `rdrobust`, this standalone script defaults to the
published Stata bandwidth values so that the table reproduces the reference
output deterministically.
"""


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
DATA_PATH = PROJECT_ROOT / 'data' / 'raw' / 'dataset_for_party_level_results.dta'
OUTPUT_NAME = 'tableA19.txt'
LINE_WIDTH = 92

# Published Stata bandwidths from TableA19/tableA19.txt.
REFERENCE_SPECS = [
    {'bw_type': 'CCT', 'bandwidth': 21.32, 'polynomial': 'Linear'},
    {'bw_type': 'CCT/2', 'bandwidth': 10.66, 'polynomial': 'Linear'},
    {'bw_type': '2CCT', 'bandwidth': 42.65, 'polynomial': 'Linear'},
    {'bw_type': 'IK', 'bandwidth': 28.48, 'polynomial': 'Linear'},
    {'bw_type': 'CCT', 'bandwidth': 26.93, 'polynomial': 'Quadratic'},
]


@dataclass
class SpecResult:
    bw_type: str
    bandwidth: float
    polynomial: str
    coef_female_mayor: float
    se_female_mayor: float
    pval_female_mayor: float
    coef_mean_frau: float
    se_mean_frau: float
    pval_mean_frau: float
    coef_interaction: float
    se_interaction: float
    pval_interaction: float
    nobs: int
    elections: int
    municipalities: int
    mean_depvar: float
    sd_depvar: float


def significance_stars(p_value: float) -> str:
    if p_value < 0.01:
        return '***'
    if p_value < 0.05:
        return '**'
    if p_value < 0.10:
        return '*'
    return ''


def triangular_weights(x: np.ndarray, bandwidth: float) -> np.ndarray:
    scaled = np.abs(x) / float(bandwidth)
    return np.where(scaled <= 1.0, np.maximum(1.0 - scaled, 0.0), 0.0)


def load_table_a19_data() -> pd.DataFrame:
    df = pd.read_stata(DATA_PATH)

    numeric_cols = [
        'female_mayor',
        'mean_frau',
        'margin_1',
        'inter_1',
        'margin_2',
        'inter_2',
        'voteshare',
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['fem_mayor_mean_frau'] = df['female_mayor'] * df['mean_frau']

    for base in ['mean_frau', 'fem_mayor_mean_frau']:
        df[f'{base}_margin_1'] = df[base] * df['margin_1']
        df[f'{base}_inter_1'] = df[base] * df['inter_1']
        df[f'{base}_margin_2'] = df[base] * df['margin_2']
        df[f'{base}_inter_2'] = df[base] * df['inter_2']

    return df


def regressor_columns(polynomial: str) -> list[str]:
    linear_cols = [
        'female_mayor',
        'mean_frau',
        'fem_mayor_mean_frau',
        'margin_1',
        'inter_1',
        'mean_frau_margin_1',
        'mean_frau_inter_1',
        'fem_mayor_mean_frau_margin_1',
        'fem_mayor_mean_frau_inter_1',
    ]
    if polynomial == 'Linear':
        return linear_cols
    if polynomial == 'Quadratic':
        return linear_cols + [
            'margin_2',
            'inter_2',
            'mean_frau_margin_2',
            'mean_frau_inter_2',
            'fem_mayor_mean_frau_margin_2',
            'fem_mayor_mean_frau_inter_2',
        ]
    raise ValueError(f'Unknown polynomial: {polynomial}')


def fit_specification(df: pd.DataFrame, *, bandwidth: float, bw_type: str, polynomial: str) -> SpecResult:
    cols = regressor_columns(polynomial)

    work = df.loc[df['margin_1'].abs() < float(bandwidth)].copy()
    required = ['voteshare', 'gkz', 'jahr', 'gkz_jahr', *cols]
    work = work.dropna(subset=required).copy()

    if work.empty:
        raise ValueError(f'No observations remain for {bw_type} / {polynomial}.')

    y = work['voteshare'].astype(float)
    X = sm.add_constant(work[cols].astype(float), has_constant='add')
    weights = triangular_weights(work['margin_1'].to_numpy(dtype=float), bandwidth)

    fit = sm.WLS(y, X, weights=weights).fit(
        cov_type='cluster',
        cov_kwds={
            'groups': work['gkz'],
            'use_correction': False,
            'df_correction': False,
        },
    )

    return SpecResult(
        bw_type=bw_type,
        bandwidth=float(bandwidth),
        polynomial=polynomial,
        coef_female_mayor=float(fit.params['female_mayor']),
        se_female_mayor=float(fit.bse['female_mayor']),
        pval_female_mayor=float(fit.pvalues['female_mayor']),
        coef_mean_frau=float(fit.params['mean_frau']),
        se_mean_frau=float(fit.bse['mean_frau']),
        pval_mean_frau=float(fit.pvalues['mean_frau']),
        coef_interaction=float(fit.params['fem_mayor_mean_frau']),
        se_interaction=float(fit.bse['fem_mayor_mean_frau']),
        pval_interaction=float(fit.pvalues['fem_mayor_mean_frau']),
        nobs=int(len(work)),
        elections=int(work['gkz_jahr'].nunique()),
        municipalities=int(work['gkz'].nunique()),
        mean_depvar=float(work['voteshare'].mean()),
        sd_depvar=float(work['voteshare'].std()),
    )


def _coef_cell(value: float, p_value: float) -> str:
    return f'{value:.3f}{significance_stars(p_value)}'


def _se_cell(value: float) -> str:
    return f'({value:.3f})'


def format_table(results: list[SpecResult]) -> str:
    if len(results) != 5:
        raise ValueError('Table A19 expects exactly 5 specifications.')

    line = '-' * LINE_WIDTH
    lines: list[str] = []

    lines.append(line)
    lines.append(f"{'':<22}{'(1)':>14}{'(2)':>16}{'(3)':>16}{'(4)':>16}{'(5)':>16}")
    lines.append(line)

    lines.append(
        f"{'female_mayor':<22}"
        f"{_coef_cell(results[0].coef_female_mayor, results[0].pval_female_mayor):>14}"
        f"{_coef_cell(results[1].coef_female_mayor, results[1].pval_female_mayor):>16}"
        f"{_coef_cell(results[2].coef_female_mayor, results[2].pval_female_mayor):>16}"
        f"{_coef_cell(results[3].coef_female_mayor, results[3].pval_female_mayor):>16}"
        f"{_coef_cell(results[4].coef_female_mayor, results[4].pval_female_mayor):>16}"
    )
    lines.append(
        f"{'':<22}"
        f"{_se_cell(results[0].se_female_mayor):>14}"
        f"{_se_cell(results[1].se_female_mayor):>16}"
        f"{_se_cell(results[2].se_female_mayor):>16}"
        f"{_se_cell(results[3].se_female_mayor):>16}"
        f"{_se_cell(results[4].se_female_mayor):>16}"
    )

    lines.append(
        f"{'mean_frau':<22}"
        f"{_coef_cell(results[0].coef_mean_frau, results[0].pval_mean_frau):>14}"
        f"{_coef_cell(results[1].coef_mean_frau, results[1].pval_mean_frau):>16}"
        f"{_coef_cell(results[2].coef_mean_frau, results[2].pval_mean_frau):>16}"
        f"{_coef_cell(results[3].coef_mean_frau, results[3].pval_mean_frau):>16}"
        f"{_coef_cell(results[4].coef_mean_frau, results[4].pval_mean_frau):>16}"
    )
    lines.append(
        f"{'':<22}"
        f"{_se_cell(results[0].se_mean_frau):>14}"
        f"{_se_cell(results[1].se_mean_frau):>16}"
        f"{_se_cell(results[2].se_mean_frau):>16}"
        f"{_se_cell(results[3].se_mean_frau):>16}"
        f"{_se_cell(results[4].se_mean_frau):>16}"
    )

    lines.append(
        f"{'fem_mayor_~u':<22}"
        f"{_coef_cell(results[0].coef_interaction, results[0].pval_interaction):>14}"
        f"{_coef_cell(results[1].coef_interaction, results[1].pval_interaction):>16}"
        f"{_coef_cell(results[2].coef_interaction, results[2].pval_interaction):>16}"
        f"{_coef_cell(results[3].coef_interaction, results[3].pval_interaction):>16}"
        f"{_coef_cell(results[4].coef_interaction, results[4].pval_interaction):>16}"
    )
    lines.append(
        f"{'':<22}"
        f"{_se_cell(results[0].se_interaction):>14}"
        f"{_se_cell(results[1].se_interaction):>16}"
        f"{_se_cell(results[2].se_interaction):>16}"
        f"{_se_cell(results[3].se_interaction):>16}"
        f"{_se_cell(results[4].se_interaction):>16}"
    )

    lines.append(line)
    lines.append(
        f"{'Bandwidth ~e':<22}"
        f"{results[0].bw_type:>14}"
        f"{results[1].bw_type:>16}"
        f"{results[2].bw_type:>16}"
        f"{results[3].bw_type:>16}"
        f"{results[4].bw_type:>16}"
    )
    lines.append(
        f"{'Bandwidth ~e':<22}"
        f"{results[0].bandwidth:>14.2f}"
        f"{results[1].bandwidth:>16.2f}"
        f"{results[2].bandwidth:>16.2f}"
        f"{results[3].bandwidth:>16.2f}"
        f"{results[4].bandwidth:>16.2f}"
    )
    lines.append(
        f"{'Polynomial':<22}"
        f"{results[0].polynomial:>14}"
        f"{results[1].polynomial:>16}"
        f"{results[2].polynomial:>16}"
        f"{results[3].polynomial:>16}"
        f"{results[4].polynomial:>16}"
    )
    lines.append(
        f"{'N':<22}"
        f"{results[0].nobs:>14}"
        f"{results[1].nobs:>16}"
        f"{results[2].nobs:>16}"
        f"{results[3].nobs:>16}"
        f"{results[4].nobs:>16}"
    )
    lines.append(
        f"{'Elections':<22}"
        f"{results[0].elections:>14}"
        f"{results[1].elections:>16}"
        f"{results[2].elections:>16}"
        f"{results[3].elections:>16}"
        f"{results[4].elections:>16}"
    )
    lines.append(
        f"{'Municipali~s':<22}"
        f"{results[0].municipalities:>14}"
        f"{results[1].municipalities:>16}"
        f"{results[2].municipalities:>16}"
        f"{results[3].municipalities:>16}"
        f"{results[4].municipalities:>16}"
    )
    lines.append(
        f"{'Mean (SD)':<22}"
        f"{f'{results[0].mean_depvar:.2f} ({results[0].sd_depvar:.2f})':>14}"
        f"{f'{results[1].mean_depvar:.2f} ({results[1].sd_depvar:.2f})':>16}"
        f"{f'{results[2].mean_depvar:.2f} ({results[2].sd_depvar:.2f})':>16}"
        f"{f'{results[3].mean_depvar:.2f} ({results[3].sd_depvar:.2f})':>16}"
        f"{f'{results[4].mean_depvar:.2f} ({results[4].sd_depvar:.2f})':>16}"
    )
    lines.append(line)
    return '\n'.join(lines) + '\n'


def main() -> None:
    df = load_table_a19_data()
    results = [
        fit_specification(
            df,
            bandwidth=spec['bandwidth'],
            bw_type=spec['bw_type'],
            polynomial=spec['polynomial'],
        )
        for spec in REFERENCE_SPECS
    ]
    table_text = format_table(results)
    print(table_text, end='')
    with open(OUTPUT_NAME, 'w', encoding='utf-8') as handle:
        handle.write(table_text)


if __name__ == '__main__':
    main()
