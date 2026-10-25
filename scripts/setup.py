"""一次性初始化（幂等）：解压全部 Multisim 样例 → 建器件索引 → 编译 C# COM 小工具。

python setup.py          # 已有的跳过
python setup.py --force  # 全部重建
"""
import glob, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msenv, ms14
import xml.etree.ElementTree as ET

force = "--force" in sys.argv
n_new = 0
idx = {}
for f in glob.glob(msenv.SAMPLES_SRC + "/**/*.ms14", recursive=True):
    rel = os.path.relpath(f, msenv.SAMPLES_SRC)
    out = os.path.join(msenv.SAMPLES, re.sub(r"[^A-Za-z0-9_.-]", "_", rel)[:-5] + ".xml")
    try:
        if force or not os.path.exists(out):
            open(out, "wb").write(ms14.decompress_ms14(open(f, "rb").read()).replace(b"\x00", b"")); n_new += 1
        root = ET.parse(out).getroot()
    except Exception as e:
        print("skipped", rel, e); continue
    for d in root.iter("CIITDiagram"):
        els = d.find("Elements")
        if els is None: continue
        for it in els:
            if it.get("Class") != "CiComponent": continue
            c = it.find("CiComponent")
            strs = [[x.get("Value", "").replace("&ASC", "") for x in cs.find("strings")]
                    for a in c.find("Attributes") for cs in [a.find("CiaCollString")] if cs is not None]
            key = "|".join(strs[0][:4]) if strs and strs[0] else "|||"
            idx.setdefault(key, []).append((os.path.basename(out), c.get("LocalName", "").replace("&ASC", "")))
json.dump(idx, open(msenv.INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(f"samples: {n_new} newly unpacked, index has {len(idx)} part families -> {msenv.INDEX}")

for name in ("msim", "msop", "tlbdump"):
    exe = os.path.join(msenv.BIN, name + ".exe")
    src = os.path.join(msenv.HERE, name + ".cs")
    if force or not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(src):
        r = subprocess.run([msenv.CSC, "-nologo", "-platform:x86", "-out:" + exe, src], capture_output=True)
        print("compiled", name, "ok" if r.returncode == 0 else r.stdout.decode("gbk", "replace"))
print("done. base document:", msenv.BASE, "ok" if os.path.exists(msenv.BASE) else "MISSING!")
