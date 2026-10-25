"""把 XML 压成 .ms14，用 Multisim 打开，导出原理图 PNG 和网表报告——画图后的自检闭环。

python render.py 文件.xml            → 同目录生成 文件.ms14 / 文件.png / 文件.net
python render.py 文件.ms14           → 只出图和网表
只关闭本次自己启动的 Multisim 进程（对比启动前后的 PID），不碰用户开着的实例。
"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msenv, ms14


def pids():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq multisim.exe", "/FO", "CSV", "/NH"], capture_output=True)
    out = r.stdout.decode("gbk", "replace")
    return {line.split('","')[1] for line in out.splitlines() if line.startswith('"multisim')}


def kill_new(before):
    for p in pids() - before:
        subprocess.run(["taskkill", "/F", "/PID", p], capture_output=True)


def render(path):
    base, ext = os.path.splitext(os.path.abspath(path))
    if ext.lower() == ".xml":
        open(base + ".ms14", "wb").write(ms14.compress_ms14(open(path, "rb").read()))
    before = pids()
    try:
        r = subprocess.run([msenv.PS32, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            os.path.join(msenv.HERE, "com_img.ps1"), base + ".ms14", base],
                           capture_output=True, timeout=240)
        out = r.stdout.decode("gbk", "replace") + r.stderr.decode("gbk", "replace")
    except subprocess.TimeoutExpired:
        out = "timeout (Multisim may be stuck on a hidden dialog)"
    finally:
        kill_new(before)
    open(base + ".net", "w", encoding="utf-8").write(out)
    for e, keep in ((".0", ".png"), (".1", None), (".2", None)):
        if os.path.exists(base + e):
            os.replace(base + e, base + keep) if keep else os.remove(base + e)
    return out


if __name__ == "__main__":
    o = render(sys.argv[1])
    print(o if len(o) < 4000 else o[:4000] + "\n... (full netlist in the .net file)")
