"""Operations shared by the FTT:Power and FTT:Transport integrations."""

from pathlib import Path
import pickle


def solve_and_store(ftt_model, year, y):
    """Solve an FTT year and store its variables in the run's output arrays."""
    ftt_model.variables, ftt_model.lags = ftt_model.solve_year(year, y, ftt_model.scenarios)
    out = ftt_model.output[ftt_model.scenarios]
    for var, val in ftt_model.variables.items():
        if 'TIME' in ftt_model.dims[var]:
            out[var][:, :, :, y] = val
        else:
            out[var][:, :, :, 0] = val


def export_ftt_results(ftt_model, output_dir):
    """Write the run's full output (Results.pickle) to output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / 'Results.pickle', 'wb') as f:
        pickle.dump(ftt_model.output, f)
