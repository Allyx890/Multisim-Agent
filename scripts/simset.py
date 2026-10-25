"""读写 .ms14 里的仿真设置（SIMULATION_INFO，Multisim 自定义的 `键:类型{值}` 嵌套格式）。

python simset.py 文件.ms14|xml                       # 列出所有瞬态相关设置（路径、TSTOP、TMAX、IC）
python simset.py 文件 --tmax 1e-8 [--tstop 1.2e-3] [--ic zero|auto] [-o 输出]
                                                    # 改掉所有瞬态块（交互式仿真 + 瞬态分析 + 各分析内嵌的 Tran）

为什么要管它：瞬态分析默认 TMAX = "calculate"，Multisim 自动取的最大步长约 TSTOP/50，
对 MHz 级载波远远不够——包络会画得乱七八糟（第 6 章 AM 电路踩过）。交互式仿真（F5）另有一套设置。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms14

_TOK = re.compile(r"([^:{}\r\n]+):(list|string|double|long|int|float|bool)\{")


def parse(s, i=0):
    """解析 `键:类型{...}` 序列，返回 [(键, 类型, 值或子列表, 起, 止)]（起止为值在 s 中的范围）。"""
    out = []
    n = len(s)
    while i < n:
        while i < n and s[i] in " \r\n\t":
            i += 1
        if i >= n or s[i] == "}":
            return out, i
        m = _TOK.match(s, i)
        if not m:
            # 不认识的内容：跳到下一行
            j = s.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        key, typ = m.group(1), m.group(2)
        j = m.end()
        if typ == "list":
            kids, k = parse(s, j)
            out.append((key, typ, kids, j, k))
            i = k + 1
        else:
            k = s.find("}", j)
            out.append((key, typ, s[j:k], j, k))
            i = k + 1
    return out, i


def tran_blocks(tree, path=()):
    """找出所有含 TSTOP 和 TMAX 的 list，返回 [(路径, {键: (类型, 值, 起, 止)})]。"""
    res = []
    for key, typ, val, a, b in tree:
        if typ == "list":
            d = {k: (t, v, x, y) for k, t, v, x, y in val if t != "list"}
            if "TSTOP" in d and "TMAX" in d:
                res.append((path + (key,), d))
            res += tran_blocks(val, path + (key,))
    return res


def find_info(xml):
    """返回 SIMULATION_INFO 属性值在 xml 文本中的 (起, 止)。"""
    i = xml.find("SIMULATION_INFO:list{")
    if i < 0:
        return None
    q2 = xml.find('"', i)
    return i, q2          # 从键名开始（前面的 &amp;ASC 前缀不动）


def describe(path, d):
    name = "/".join(path)
    tstop = float(d["TSTOP"][1]) if d["TSTOP"][0] == "double" else d["TSTOP"][1]
    kind = "interactive(F5)" if isinstance(tstop, float) and tstop >= 1e29 else "analysis"
    return f"{name:60} {kind:10} TSTOP={d['TSTOP'][1]:<10} TMAX={d['TMAX'][1]:<10} IC={d.get('IC', ('', '?'))[1]}"


def load_text(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"MSMCompressed"):
        raw = ms14.decompress_ms14(raw)
    return raw.decode("latin-1")


def save_text(path, text):
    data = text.encode("latin-1")
    if path.lower().endswith(".ms14"):
        data = ms14.compress_ms14(data)
    open(path, "wb").write(data)


def edit(text, tmax=None, tstop=None, ic=None, scope="all"):
    """返回改好的 xml 文本和修改条数。交互式块（TSTOP≥1e29）不改 TSTOP。"""
    span = find_info(text)
    if span is None:
        raise ValueError("no SIMULATION_INFO in this file")
    a, b = span
    info = text[a:b]
    tree, _ = parse(info)
    edits = []
    for path, d in tran_blocks(tree):
        interactive = d["TSTOP"][0] == "double" and float(d["TSTOP"][1]) >= 1e29
        if (scope == "interactive" and not interactive) or (scope == "analysis" and interactive):
            continue
        if tmax is not None:
            edits.append((d["TMAX"], "double", f"{tmax:g}"))
        if tstop is not None and not interactive:
            edits.append((d["TSTOP"], "double", f"{tstop:g}"))
        if ic is not None and "IC" in d:
            edits.append((d["IC"], "string", {"zero": "zero_ic", "auto": "auto_ic"}[ic]))
    # 从后往前替换，避免偏移变化；连同类型名一起改（string{calculate} → double{1e-08}）
    for (typ, val, x, y), ntyp, nval in sorted(edits, key=lambda e: -e[0][2]):
        head = info.rfind(":", 0, x)            # “:string{” 的冒号
        info = info[:head] + ":" + ntyp + "{" + nval + info[y:]
    return text[:a] + info + text[b:], len(edits)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--tmax", type=float)
    ap.add_argument("--tstop", type=float)
    ap.add_argument("--ic", choices=["zero", "auto"])
    ap.add_argument("--scope", choices=["all", "interactive", "analysis"], default="all",
                    help="只改交互式仿真(F5)或只改各分析的设置")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    text = load_text(a.file)
    if a.tmax is None and a.tstop is None and a.ic is None:
        tree, _ = parse(text[slice(*find_info(text))])
        for p, d in tran_blocks(tree):
            print(describe(p, d))
        sys.exit()
    new, n = edit(text, a.tmax, a.tstop, a.ic, a.scope)
    out = a.out or a.file
    save_text(out, new)
    tree, _ = parse(new[slice(*find_info(new))])
    for p, d in tran_blocks(tree):
        print(describe(p, d))
    print(f"changed {n} value(s) -> {out}")
