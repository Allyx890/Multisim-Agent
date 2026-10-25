"""Functional gate for the 5 kHz demonstration, in addition to simulator agreement.

Reject insufficient output, harmonic distortion and failure to recover the known input tone.
THD here covers harmonics 2 through 5; it is not a voice-band or hardware specification.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import msenv


def assess(t, v, frequency=5000):
    k = (t >= 1.2e-3) & (t <= 2e-3)
    t, v = t[k], v[k]
    if len(t) < 100:
        raise ValueError('Need the 1.2-2.0 ms comparison window.')
    x = np.column_stack([np.ones(len(t))] +
                        [fn(2*np.pi*frequency*n*t) for n in range(1, 6) for fn in (np.sin, np.cos)])
    c = np.linalg.lstsq(x, v, rcond=None)[0]
    harmonics = np.hypot(c[1::2], c[2::2])
    thd = float(np.linalg.norm(harmonics[1:]) / max(harmonics[0], 1e-15))
    residual = float(np.std(v - x[:, :3] @ c[:3]) / max(np.std(v), 1e-15))
    lo, hi = np.percentile(v, [.5, 99.5])
    result = {'vpp': float(hi-lo), 'thd_harmonics_2_to_5': thd,
              'residual_to_5khz_sine': residual,
              'limits': {'vpp_min': 1.0, 'thd_max': .03, 'residual_max': .05}}
    result['pass'] = result['vpp'] >= 1 and thd <= .03 and residual <= .05
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir', type=Path, default=Path(msenv.OUT))
    args = ap.parse_args()
    a = np.loadtxt(args.data_dir/'am_link_V_PR4.csv', delimiter=',')
    result = assess(a[:, 0], a[:, 1])
    (args.data_dir/'am_link_verify/recovery.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
