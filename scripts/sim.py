"""用 Multisim 自己的仿真器跑瞬态，并分析探针波形（频率、峰峰值、起振时间）。

python sim.py 文件.ms14 终止时间 [--dt 1e-8] [--plot 图.png]
python sim.py 文件.ms14 --op          直流工作点：打印每个探针的 V(...)、I(...)，用来和 ngspice .op 对数
电路里必须放了探针（msgen.Doc.probe）。数据存为 <文件>_V_PRx.csv。
只关闭本次自己启动的 Multisim 进程。分析部分需要 numpy；--plot 需要 matplotlib。
"""
import argparse, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msenv
from render import pids, kill_new


def _exec(args, timeout):
    """运行一个 COM 小工具；只关闭本次新启动的 multisim.exe。"""
    before = pids()
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout)
        return r.stdout.decode("gbk", "replace") + r.stderr.decode("gbk", "replace")
    except subprocess.TimeoutExpired:
        return "timeout"
    finally:
        kill_new(before)
        time.sleep(1.5)        # 等进程彻底退出：紧接着启动下一个实例时，COM 偶尔会失败


def _csvs(prefix):
    d, b = os.path.dirname(prefix), os.path.basename(prefix) + "_V_"
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith(b) and f.endswith(".csv"))


def run(ms14_path, tstop, dt=1e-8, tries=3):
    """瞬态仿真。返回 (日志, [csv 路径])。先删旧 CSV（否则失败时会把上次的旧数据当结果），失败自动重试。"""
    exe = os.path.join(msenv.BIN, "msim.exe")
    if not os.path.exists(exe):
        sys.exit("run `msa.py setup` first (compiles msim.exe)")
    prefix = os.path.splitext(os.path.abspath(ms14_path))[0]
    log = ""
    for k in range(tries):
        for f in _csvs(prefix):
            os.remove(f)
        log = _exec([exe, os.path.abspath(ms14_path), repr(tstop), prefix, repr(dt)], 1900)
        files = [f for f in _csvs(prefix) if os.path.getsize(f) > 0]
        if files and "sim time" in log:
            return log, files
        log += f"\n(attempt {k + 1}: no data, retrying)"
    return log, []


def op(ms14_path, tries=3):
    """直流工作点。返回 msop 的输出文本（V(PRx) = ...）。取不到数自动重试。"""
    exe = os.path.join(msenv.BIN, "msop.exe")
    if not os.path.exists(exe):
        sys.exit("run `msa.py setup` first (compiles msop.exe)")
    log = ""
    for k in range(tries):
        log = _exec([exe, os.path.abspath(ms14_path)], 300)
        if re.search(r"^V\(\w+\)\s*=\s*[-+0-9]", log, re.M):
            return log
    return log


def analyze(csv, settle=0.75):
    """返回 dict：频率（后 25% 时间的过零点）、峰峰值、直流、起振到 90% 幅度的时间。"""
    import numpy as np
    d = np.loadtxt(csv, delimiter=",")
    t, v = d[:, 0], d[:, 1]
    w = t >= t[-1] * settle
    x = v[w] - v[w].mean()
    tw = t[w]
    z = tw[1:][(x[:-1] < 0) & (x[1:] >= 0)]
    f = (len(z) - 1) / (z[-1] - z[0]) if len(z) > 2 else float("nan")
    vpp = v[w].max() - v[w].min()
    # 起振：按 1/20 总时长分段的峰峰值首次达到稳态 90%
    seg = max(len(t) // 200, 10)
    env = [(t[i], np.ptp(v[i:i + seg])) for i in range(0, len(t) - seg, seg)]
    t90 = next((ti for ti, e in env if e >= 0.9 * vpp), float("nan"))
    return {"f": f, "vpp": vpp, "vdc": v[w].mean(), "t90": t90, "t": t, "v": v}


def plot(results, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(results)
    fig, ax = plt.subplots(n, 2, figsize=(12, 3.2 * n), squeeze=False)
    for i, (name, r) in enumerate(results.items()):
        t, v = r["t"], r["v"]
        ax[i][0].plot(t * 1e6, v, lw=0.4); ax[i][0].set_title(f"{name}  full"); ax[i][0].set_xlabel("t / us")
        m = t >= t[-1] - 5 / r["f"] if r["f"] == r["f"] else t >= t[-1] * 0.97
        ax[i][1].plot(t[m] * 1e6, v[m]); ax[i][1].set_xlabel("t / us")
        ax[i][1].set_title(f"{name}  f={r['f']/1e6:.4f} MHz  Vpp={r['vpp']:.3f} V")
        for a in ax[i]: a.grid(alpha=.3)
    plt.tight_layout(); plt.savefig(path, dpi=110)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file"); ap.add_argument("tstop", type=float, nargs="?")
    ap.add_argument("--dt", type=float, default=1e-8); ap.add_argument("--plot")
    ap.add_argument("--op", action="store_true", help="只求直流工作点")
    a = ap.parse_args()
    if a.op:
        print(op(a.file).strip()); sys.exit()
    if a.tstop is None:
        ap.error("需要终止时间，或用 --op")
    log, files = run(a.file, a.tstop, a.dt)
    print(log.strip())
    res = {}
    for f in files:
        r = analyze(f)
        name = os.path.basename(f).split("_V_")[-1][:-4]
        res[name] = r
        print(f"{name}: f = {r['f']/1e6:.4f} MHz   Vpp = {r['vpp']:.3f} V   Vdc = {r['vdc']:.3f} V   start-up to 90% ~ {r['t90']*1e6:.1f} us")
    if a.plot and res:
        plot(res, a.plot); print("plot:", a.plot)
