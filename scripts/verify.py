"""Verify a generated Multisim schematic against its reference SPICE netlist (.cir, simulated by ngspice).

python verify.py DESIGN.xml|.ms14 --cir DESIGN.cir [--alias VCC=V1 ...] [--probe PR1=out ...]
                 [--tran 300e-6] [--dt 1e-8] [--window 0.5] [--fmax 3e6] [--no-op]

Layers (any FAIL -> non-zero exit code):
  A connectivity  Multisim opens the file; its own netlist report == .cir (polarised parts compared pin-by-pin)
  B values        R/C/L/DC/SIN source values == .cir
  C settings      TMAX stored for the interactive sim (F5) and the Transient analysis is fine enough
                  (<= 1/(20 f), f = fastest signal). Checked statically because the COM simulation ignores
                  both — a "calculate" TMAX is exactly what makes a user's Grapher waveform look garbled.
  D DC op point   Multisim probe voltages == ngspice .op
  E transient     both simulators, same span: DC level, p-p, frequency, envelope (modulation index, trough,
                  shape correlation). Initial conditions follow the file (zero_ic -> ngspice uic).
Probe -> .cir node map: from DESIGN.meta.json written by msgen (d.probe(..., node="out")), or --probe.
Output: DESIGN_verify/report.md + compare.png, and a console summary.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msenv
import msxml
import netcheck
import ngs
import render
import sim
import simset

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def hz(f):
    for unit, m in (("GHz", 1e9), ("MHz", 1e6), ("kHz", 1e3)):
        if f >= m:
            return f"{f / m:.5g} {unit}"
    return f"{f:.5g} Hz"


class Report:
    def __init__(self):
        self.rows = []

    def add(self, layer, item, status, detail=""):
        self.rows.append((layer, item, status, detail))
        print(f"[{status}] {layer} {item}  {detail}")

    def fails(self):
        return sum(r[2] == FAIL for r in self.rows)


# ---------------- 波形指标 ----------------
def metrics(t, v, t0, t1):
    import numpy as np
    m = (t >= t0) & (t <= t1)
    t, v = t[m], v[m]
    if len(t) < 10:
        return None
    dt = max(np.median(np.diff(t)), (t1 - t0) / 400000)
    tt = np.arange(t[0], t[-1], dt)
    vv = np.interp(tt, t, v)
    # 峰峰值用 0.5%/99.5% 分位数：ngspice 偶有单点数值尖峰，直接 max-min 会误判（曾差 5.0% 误报）
    lo, hi = np.percentile(vv, [0.5, 99.5])
    r = {"t": tt, "v": vv, "mean": vv.mean(), "vpp": hi - lo, "f": None, "env": None}
    x = vv - vv.mean()
    hyst = 0.05 * np.ptp(x)
    if hyst > 1e-9:
        # 带回差的上升过零点，避免噪声误计数
        state, cross = x[0] > 0, []
        for i in range(1, len(x)):
            if not state and x[i] > hyst:
                state = True
                # 线性插值回到真正过零的时刻
                j = i
                while j > 0 and x[j] > 0:
                    j -= 1
                cross.append(tt[j] + dt * (-x[j]) / (x[j + 1] - x[j] + 1e-30))
            elif state and x[i] < -hyst:
                state = False
        if len(cross) >= 4:
            r["f"] = (len(cross) - 1) / (cross[-1] - cross[0])
            r["cross"] = np.array(cross)
    if r["f"] and r["f"] * (t1 - t0) >= 30:
        c = r["cross"]
        et, ev = [], []
        for a, b in zip(c[:-1], c[1:]):
            k = (tt >= a) & (tt < b)
            if k.sum() > 2:
                et.append((a + b) / 2); ev.append(np.ptp(vv[k]))
        et, ev = np.array(et), np.array(ev)
        # 逐周期峰峰值再做 5 点中值滤波，去掉单周期尖峰
        if len(ev) >= 5:
            ev = np.median(np.lib.stride_tricks.sliding_window_view(np.pad(ev, 2, mode="edge"), 5), axis=1)
        r["env"] = (et, ev)
        r["emax"], r["emin"] = ev.max(), ev.min()
        r["ma"] = (ev.max() - ev.min()) / (ev.max() + ev.min() + 1e-30)
    return r


def compare_wave(name, a, b, rep, tol):
    """a = Multisim，b = ngspice。"""
    import numpy as np
    def rel(x, y):
        return abs(x - y) / max(abs(y), 1e-12)
    dmean = abs(a["mean"] - b["mean"])
    st = PASS if dmean <= max(tol["v_abs"], tol["v_rel"] * abs(b["mean"])) else FAIL
    rep.add("E", f"{name} DC level", st, f"Multisim {a['mean']:.4g} V / ngspice {b['mean']:.4g} V")
    st = PASS if abs(a["vpp"] - b["vpp"]) <= max(tol["v_abs"], tol["vpp_rel"] * b["vpp"]) else FAIL
    rep.add("E", f"{name} peak-to-peak", st, f"Multisim {a['vpp']:.4g} V / ngspice {b['vpp']:.4g} V")
    if a["f"] or b["f"]:
        if a["f"] and b["f"]:
            st = PASS if rel(a["f"], b["f"]) <= tol["f_rel"] else FAIL
            rep.add("E", f"{name} frequency", st, f"Multisim {hz(a['f'])} / ngspice {hz(b['f'])} (diff {rel(a['f'], b['f'])*100:.2f}%)")
        else:
            rep.add("E", f"{name} frequency", FAIL, f"periodic on one side only: Multisim {a['f']} / ngspice {b['f']}")
    if a.get("env") is not None and b.get("env") is not None and b["ma"] > 0.03:
        st = PASS if abs(a["ma"] - b["ma"]) <= tol["ma_abs"] else FAIL
        rep.add("E", f"{name} modulation index", st, f"Multisim {a['ma']*100:.1f}% / ngspice {b['ma']*100:.1f}%")
        st = PASS if abs(a["emin"] - b["emin"]) <= max(tol["v_abs"], tol["vpp_rel"] * b["emin"]) else FAIL
        rep.add("E", f"{name} envelope trough Vpp", st, f"Multisim {a['emin']:.4g} V / ngspice {b['emin']:.4g} V")
        # 包络形状：插值到同一时间轴求相关系数（抓“包络很怪”——锯齿、拍频、缺口）
        et = b["env"][0]
        ea = np.interp(et, *a["env"])
        eb = b["env"][1]
        cc = np.corrcoef(ea, eb)[0, 1] if np.std(ea) > 0 and np.std(eb) > 0 else 0
        st = PASS if cc >= tol["env_corr"] else FAIL
        rep.add("E", f"{name} envelope shape correlation", st, f"r = {cc:.3f} (need >= {tol['env_corr']})")


def plot(pairs, path, t0, t1):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    n = len(pairs)
    fig, ax = plt.subplots(n, 3, figsize=(16, 3.4 * n), squeeze=False)
    for i, (name, a, b, fa, fb) in enumerate(pairs):
        ax[i][0].plot(fb[0] * 1e6, fb[1], lw=0.5, color="tab:orange", label="ngspice")
        ax[i][0].plot(fa[0] * 1e6, fa[1], lw=0.5, color="tab:blue", alpha=0.7, label="Multisim")
        ax[i][0].axvspan(t0 * 1e6, t1 * 1e6, color="0.9", zorder=0)
        ax[i][0].set_title(f"{name}  full run (grey = compared window)"); ax[i][0].legend(fontsize=8); ax[i][0].set_xlabel("t / us")
        if a and b:
            f = b["f"] or a["f"]
            span = 5 / f if f else (t1 - t0) / 10
            ka = a["t"] >= a["t"][-1] - span
            kb = b["t"] >= b["t"][-1] - span
            shift = 0.0
            if f and a.get("cross") is not None and b.get("cross") is not None:
                shift = ((a["cross"][-1] - b["cross"][-1]) + 0.5 / f) % (1 / f) - 0.5 / f   # phase-align (oscillator phase is arbitrary)
            ax[i][1].plot((b["t"][kb] + shift) * 1e6, b["v"][kb], color="tab:orange", label="ngspice (phase-aligned)")
            ax[i][1].plot(a["t"][ka] * 1e6, a["v"][ka], "--", color="tab:blue", label="Multisim")
            ax[i][1].set_title("last cycles"); ax[i][1].legend(fontsize=8); ax[i][1].set_xlabel("t / us")
            if b.get("env") is not None and a.get("env") is not None:
                ax[i][2].plot(b["env"][0] * 1e6, b["env"][1], color="tab:orange", label="ngspice")
                ax[i][2].plot(a["env"][0] * 1e6, a["env"][1], "--", color="tab:blue", label="Multisim")
                ax[i][2].set_title(f"envelope (per-cycle p-p)  ma: {a['ma']*100:.1f}% / {b['ma']*100:.1f}%")
            else:
                for r, c, lab in ((b, "tab:orange", "ngspice"), (a, "tab:blue", "Multisim")):
                    x = r["v"] - r["mean"]
                    sp = np.abs(np.fft.rfft(x * np.hanning(len(x))))
                    fr = np.fft.rfftfreq(len(x), r["t"][1] - r["t"][0])
                    ax[i][2].semilogy(fr / 1e6, sp / (sp.max() + 1e-30) + 1e-9, color=c, label=lab, lw=0.8)
                ax[i][2].set_title("spectrum (normalised)"); ax[i][2].set_xlabel("f / MHz")
                if b["f"]:
                    ax[i][2].set_xlim(0, b["f"] * 5 / 1e6)
            ax[i][2].legend(fontsize=8)
        for x in ax[i]:
            x.grid(alpha=.3)
    try:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
    except Exception:
        pass
    plt.tight_layout(); plt.savefig(path, dpi=100)


# ---------------- 主流程 ----------------
def ms_values(root):
    """{位号: 主值}：R/C/L/直流源取 CiaParamList doubles[1]。"""
    d = next(root.iter("CIITDiagram"))
    out = {}
    for it in d.find("Elements"):
        if it.get("Class") != "CiComponent":
            continue
        c = it.find("CiComponent")
        name = c.get("LocalName", "").replace("&ASC", "")
        pl = c.find(".//CiaParamList")
        if pl is None:
            continue
        dbl = [float(x.get("Value")) for x in pl.find("doubles")]
        fam = " ".join(x.get("Value", "") for x in c.iter("Item") if x.get("Value", "").startswith("&ASCAC_VOLTAGE"))
        if fam and len(dbl) > 5:
            out[name] = ("sin", dbl[1], dbl[5])      # sine source: peak, frequency
        elif len(dbl) > 1:
            out[name] = dbl[1]
    return out


def same_value(a, b):
    if isinstance(a, tuple) or isinstance(b, tuple):
        return isinstance(a, tuple) and isinstance(b, tuple) and a[0] == b[0] and all(
            abs(x - y) <= 1e-6 * max(abs(y), 1e-15) for x, y in zip(a[1:], b[1:]))
    return abs(a - b) <= 1e-6 * max(abs(b), 1e-15)


def fmt_value(v):
    return f"SIN {v[1]:g} V {v[2]:g} Hz" if isinstance(v, tuple) else f"{v:g}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design"); ap.add_argument("--cir", required=True)
    ap.add_argument("--alias", nargs="*", default=[], help=".cir name=Multisim refdes, e.g. VCC=V1 (better: use identical names)")
    ap.add_argument("--probe", nargs="*", default=[], help="probe=.cir node, e.g. PR1=out (default: from .meta.json)")
    ap.add_argument("--tran", type=float, help="transient span in seconds; omit to skip layer E")
    ap.add_argument("--dt", type=float, default=1e-8, help="sample interval = max step, same for both simulators")
    ap.add_argument("--window", type=float, default=0.5, help="compare the last fraction of the run (skip start-up)")
    ap.add_argument("--fmax", type=float, help="fastest signal frequency for layer C (default: measured / SIN sources)")
    ap.add_argument("--no-op", action="store_true")
    ap.add_argument("--f-tol", type=float, default=0.01, help="relative frequency tolerance")
    a = ap.parse_args()
    tol = dict(v_abs=0.02, v_rel=0.03, vpp_rel=0.05, f_rel=a.f_tol, ma_abs=0.03, env_corr=0.95, op_abs=0.02, op_rel=0.02)

    design = os.path.abspath(a.design)
    base = os.path.splitext(design)[0]
    outdir = base + "_verify"
    os.makedirs(outdir, exist_ok=True)
    alias = dict(x.split("=") for x in a.alias)
    rep = Report()

    # ---- A 连接 ----
    log = render.render(design)
    ms14 = base + ".ms14"
    if "opened" not in log:
        rep.add("A", "Multisim opens the file", FAIL, log.strip()[:200])
        return finish(rep, outdir)
    rep.add("A", "Multisim opens the file", PASS, os.path.basename(ms14))
    bad, lines = netcheck.check(log, a.cir, alias)
    rep.add("A", "netlist vs .cir", PASS if bad == 0 else FAIL, f"{bad} mismatch(es)" + ("" if bad == 0 else "\n    " + "\n    ".join(l for l in lines if l.startswith("XX"))))

    # ---- B 数值 ----
    root = msxml.parse(ms14)
    msv = ms_values(root)
    nb, nchk = 0, 0
    for name, kind, nodes, val, line in netcheck.parse_cir(a.cir):
        if val is None or kind not in "RCLV":
            continue
        ms_name = alias.get(name, name)
        if ms_name not in msv:
            rep.add("B", f"{name} value", WARN, "no Multisim part with this reference designator")
            continue
        nchk += 1
        if not same_value(msv[ms_name], val):
            nb += 1
            rep.add("B", f"{name} value", FAIL, f"Multisim {fmt_value(msv[ms_name])} / .cir {fmt_value(val)}")
    rep.add("B", f"part values ({nchk} checked)", PASS if nb == 0 else FAIL, f"{nb} mismatch(es)")

    # ---- 探针映射 ----
    probes = {}
    meta = base + ".meta.json"
    if os.path.exists(meta):
        probes = {k: v for k, v in json.load(open(meta, encoding="utf-8")).get("probes", {}).items() if v}
    probes.update(dict(x.split("=") for x in a.probe))
    if not probes:
        rep.add("D/E", "probe map", WARN, "no probe->node map (d.probe(..., node=...) or --probe): simulation comparison skipped")

    # ---- D 直流工作点 ----
    if probes and not a.no_op:
        mslog = sim.op(ms14)
        msop = {m.group(1): float(m.group(2)) for m in re.finditer(r"V\((\w+)\)\s*=\s*([-+0-9.eE]+)", mslog)}
        ngop, nglog = ngs.op(a.cir, list(probes.values()))
        for p, node in probes.items():
            if p not in msop or node not in ngop:
                rep.add("D", f"{p}({node}) operating point", FAIL, f"no value: Multisim {msop.get(p)} / ngspice {ngop.get(node)} (probe on a wire? node name in .cir?)")
                continue
            x, y = msop[p], ngop[node]
            st = PASS if abs(x - y) <= max(tol["op_abs"], tol["op_rel"] * abs(y)) else FAIL
            rep.add("D", f"{p}({node}) operating point", st, f"Multisim {x:.4g} V / ngspice {y:.4g} V")

    # ---- E 瞬态 ----
    fmax = a.fmax
    if probes and a.tran:
        import numpy as np
        mslog, files = sim.run(ms14, a.tran, a.dt)
        msw = {}
        for f in files:
            nm = os.path.basename(f)[len(os.path.basename(base)) + 3:-4]
            d = np.loadtxt(f, delimiter=",", ndmin=2)
            if d.size:
                msw[nm] = (d[:, 0], d[:, 1])
        # 初始条件要和文件一致：COM 仿真会读瞬态分析的 IC（但不读 TMAX）。zero_ic ↔ ngspice uic
        txt = simset.load_text(ms14)
        tr = {"/".join(p): d for p, d in simset.tran_blocks(simset.parse(txt[slice(*simset.find_info(txt))])[0])}
        ic = tr.get("SIMULATION_INFO/ANALYSES/TRAN/ANALYSIS", {}).get("IC", ("", "auto_ic"))[1]
        rep.add("E", "initial conditions", PASS, f"file IC={ic} -> ngspice {'uic (start from zero)' if ic == 'zero_ic' else 'operating point first'}")
        ngw, nglog = ngs.tran(a.cir, list(probes.values()), a.tran, a.dt, uic=(ic == "zero_ic"))
        t0, t1 = a.tran * (1 - a.window), a.tran
        pairs = []
        for p, node in probes.items():
            fa, fb = msw.get(p), ngw.get(node)
            if fa is None or fb is None:
                rep.add("E", f"{p}({node}) waveform", FAIL, f"missing waveform: Multisim {'ok' if fa else 'none'} / ngspice {'ok' if fb else 'none'}")
                continue
            ma_, mb_ = metrics(*fa, t0, t1), metrics(*fb, t0, t1)
            compare_wave(f"{p}({node})", ma_, mb_, rep, tol)
            pairs.append((f"{p}({node})", ma_, mb_, fa, fb))
            if mb_ and mb_["f"]:
                fmax = max(fmax or 0, mb_["f"])
        if pairs:
            plot(pairs, os.path.join(outdir, "compare.png"), t0, t1)

    # ---- C settings ----
    src_f = [v[2] for _, k, _, v, _ in netcheck.parse_cir(a.cir) if isinstance(v, tuple)]
    if src_f:
        fmax = max([fmax or 0] + src_f)
    text = simset.load_text(ms14)
    tree, _ = simset.parse(text[slice(*simset.find_info(text))])
    blocks = {"/".join(p): d for p, d in simset.tran_blocks(tree)}
    for key, label in (("DEFAULT_INST_SETTINGS/TRAN/ANALYSIS", "interactive sim (F5)"), ("SIMULATION_INFO/ANALYSES/TRAN/ANALYSIS", "transient analysis")):
        d = blocks.get(key)
        if d is None:
            rep.add("C", label, WARN, "settings block not found in file")
            continue
        tstop = float(d["TSTOP"][1]) if d["TSTOP"][0] == "double" else None
        if d["TMAX"][0] == "double":
            tmax, how = float(d["TMAX"][1]), ""
        else:
            tmax = (tstop / 50) if tstop and tstop < 1e29 else None
            how = " (calculate ~ TSTOP/50)"
        if not fmax:
            rep.add("C", f"{label} TMAX", WARN, f"TMAX={d['TMAX'][1]}; signal frequency unknown (give --fmax or --tran)")
            continue
        need = 1 / (20 * fmax)
        ok = tmax is not None and tmax <= need
        rep.add("C", f"{label} TMAX", PASS if ok else FAIL,
                f"TMAX={d['TMAX'][1]}{how}; {hz(fmax)} signal needs <= {need:.2g} s"
                + ("" if ok else f"  -> fix: d.sim_settings(tmax={need/2:.1g}, ...) or msa.py simset FILE.ms14 --tmax {need/2:.1g}" + (f" --tstop {a.tran:g}" if a.tran else "")))
    return finish(rep, outdir)


def finish(rep, outdir):
    lines = ["# Verification report", "", "| layer | check | result | detail |", "|---|---|---|---|"]
    for layer, item, st, detail in rep.rows:
        lines.append(f"| {layer} | {item} | {st} | {detail.splitlines()[0] if detail else ''} |")
    if os.path.exists(os.path.join(outdir, "compare.png")):
        lines += ["", "![Multisim vs ngspice](compare.png)"]
    open(os.path.join(outdir, "report.md"), "w", encoding="utf-8").write("\n".join(lines))
    n = rep.fails()
    print(f"\n==== {'ALL PASS' if n == 0 else f'{n} FAIL(s)'} (report: {os.path.join(outdir, 'report.md')}) ====")
    return n


if __name__ == "__main__":
    sys.exit(min(main(), 100))
