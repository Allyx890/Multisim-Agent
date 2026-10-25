"""Create the README figure from real Multisim probe CSVs and an ngspice run.

Run `msa check build.py --cir circuit.cir --tran 2e-3 --dt 1e-8` first.
The figure uses unshifted time and physical voltage units; no gain or phase fitting.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import msenv
import ngs
import verify
from validate_recovery import assess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir', type=Path, default=Path(msenv.OUT))
    ap.add_argument('--out', type=Path, default=ROOT / 'docs/images/am_link_results.png')
    args = ap.parse_args()
    report = args.data_dir / 'am_link_verify/report.md'
    report_text = report.read_text(encoding='utf-8')
    if '| FAIL |' in report_text or '| E | PR4(audio)' not in report_text:
        raise SystemExit('A passing complete-link verification report is required.')
    data = {}
    sources = {}
    for probe, node in [('PR1', 'out'), ('PR3', 'lpf'), ('PR4', 'audio')]:
        path = args.data_dir / f'am_link_V_{probe}.csv'
        a = np.loadtxt(path, delimiter=',')
        data[node] = (a[:, 0], a[:, 1])
        sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    reference, log = ngs.tran(str(HERE / 'circuit.cir'), list(data), 2e-3, 1e-8)
    if set(reference) != set(data):
        raise RuntimeError('Incomplete ngspice waveforms: ' + log[-2000:])
    scores = {}
    recovery = {}
    for node in data:
        scores[node] = {}
        for label, wave in [('Multisim', data[node]), ('ngspice', reference[node])]:
            m = verify.metrics(*wave, 1e-3, 2e-3)
            scores[node][label] = {key: float(m[key]) if m[key] is not None else None
                                   for key in ('mean', 'vpp', 'f')}
            if node == 'audio':
                recovery[label] = assess(*wave)
                if not recovery[label]['pass']:
                    raise RuntimeError(f'{label} fails audio recovery quality: {recovery[label]}')
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#344054', 'text.color': '#172B4D',
                         'axes.edgecolor': '#D0D5DD', 'xtick.color': '#475467',
                         'ytick.color': '#475467', 'savefig.facecolor': 'white'})
    fig, axs = plt.subplots(3, 1, figsize=(9.5, 9), sharex=True)
    fig.subplots_adjust(left=.105, right=.97, bottom=.10, top=.81, hspace=.42)
    fig.text(.105, .96, 'AM transmission, detection and audio recovery', fontsize=18, weight='bold')
    fig.text(.105, .923, '2.63 MHz carrier  /  5 kHz input  /  71 electrical components', fontsize=11, color='#667085')
    ngcolor, mscolor = '#D38122', '#1565A8'
    titles = [('out', '01  AM transmitter output', 'RF voltage (V)'),
              ('lpf', '02  Filtered envelope detector output', 'Detector voltage (V)'),
              ('audio', '03  Recovered audio across 1 kohm', 'Audio voltage (V)')]
    handles = []
    for ax, (node, title, ylabel) in zip(axs, titles):
        for label, pair, color in [('ngspice', reference[node], ngcolor), ('Multisim', data[node], mscolor)]:
            t, v = pair
            k = (t >= 1.2e-3) & (t <= 2e-3)
            # Preserve all RF samples so envelope minima are not aliases of decimation.
            ax.plot(t[k] * 1e3, v[k], color=color,
                    lw=.25 if node == 'out' else 1.8,
                    linestyle='-' if label == 'ngspice' else '--',
                    alpha=.85 if node == 'out' else 1, label=label)
        ax.set_title(title, loc='left', pad=12, fontsize=12, weight='bold')
        ax.set_ylabel(ylabel, fontsize=10)
        ax.grid(axis='both', color='#E8EDF2', linewidth=.7)
        ax.set_xlim(1.2, 2)
        if node == 'audio':
            handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper left', bbox_to_anchor=(.105, .901), ncol=2, frameon=False,
               borderaxespad=0, handlelength=3)
    axs[-1].set_xlabel('Time (ms)')
    fig.text(.105, .035, 'Actual simulator traces; common time axis, no phase alignment or amplitude normalization.',
             fontsize=9, color='#667085')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=180)
    plt.close(fig)
    summary = {'window_s': [1e-3, 2e-3], 'plotted_window_s': [1.2e-3, 2e-3],
               'max_step_s': 1e-8, 'metrics': scores, 'audio_recovery': recovery, 'Multisim_csv_sha256': sources}
    args.out.with_suffix('.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(args.out)
    print(json.dumps(scores, indent=2))


if __name__ == '__main__':
    main()
