"""ngspice 参考仿真：拿用户的 .cir（设计的“标准答案”），换上我们需要的分析，读回结果。

op(cir, nodes)                 → {节点: 电压}
tran(cir, nodes, tstop, tmax)  → {节点: (t数组, v数组)}
cir 里原有的 .tran/.op/.control…/.end 等会被去掉；.include/.lib 按 cir 所在目录解析（在那个目录里运行）。
"""
import os
import re
import subprocess
import tempfile

import msenv

_DROP = re.compile(r"^\s*\.(tran|op|ac|dc|end|print|plot|probe|meas|measure|four|save|width|options?)\b", re.I)


def clean(text):
    out, skip = [], False
    for i, line in enumerate(text.splitlines()):
        low = line.strip().lower()
        if low.startswith(".control"):
            skip = True
            continue
        if low.startswith(".endc"):
            skip = False
            continue
        if skip or (i > 0 and _DROP.match(line)):
            continue
        out.append(line)
    return "\n".join(out)


def _run(cir, tail, timeout=600):
    d = os.path.dirname(os.path.abspath(cir))
    body = clean(open(cir, encoding="utf-8", errors="replace").read()) + "\n" + tail + "\n.end\n"
    fd, tmp = tempfile.mkstemp(suffix=".cir", prefix="_ngs_", dir=d)
    os.close(fd)
    open(tmp, "w", encoding="utf-8").write(body)
    try:
        r = subprocess.run([msenv.NGSPICE, "-b", os.path.basename(tmp)], cwd=d, capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    finally:
        os.remove(tmp)


def op(cir, nodes):
    nodes = [n for n in nodes if n not in ("0", None)]
    if not nodes:
        return {}, ""
    log = _run(cir, ".control\nop\nprint " + " ".join(f"v({n})" for n in nodes) + "\n.endc")
    res = {}
    for n in nodes:
        m = re.search(r"^v\(" + re.escape(n.lower()) + r"\)\s*=\s*([-+0-9.eE]+)", log, re.M)
        if m:
            res[n] = float(m.group(1))
    return res, log


def tran(cir, nodes, tstop, tmax, tstart=0.0, uic=False):
    """uic=True：不算直流工作点、所有电容电压/电感电流从 0 起步（对应 Multisim 的 IC=zero_ic）。"""
    import numpy as np
    nodes = [n for n in nodes if n not in ("0", None)]
    d = os.path.dirname(os.path.abspath(cir))
    fd, out = tempfile.mkstemp(suffix=".txt", prefix="_ngw_", dir=d)
    os.close(fd)
    tail = (f".control\nset filetype=ascii\ntran {tmax:g} {tstop:g} {tstart:g} {tmax:g}{' uic' if uic else ''}\n"
            f"wrdata {os.path.basename(out)} " + " ".join(f"v({n})" for n in nodes) + "\n.endc")
    try:
        log = _run(cir, tail)
        data = np.loadtxt(out) if os.path.getsize(out) else np.zeros((0, 2 * len(nodes)))
    finally:
        os.remove(out)
    res = {}
    for k, n in enumerate(nodes):
        if data.ndim == 2 and data.shape[1] >= 2 * k + 2:
            res[n] = (data[:, 2 * k], data[:, 2 * k + 1])
    return res, log
