"""比对 Multisim 网表报告（render.py 生成的 .net）与 SPICE 网表（.cir）：按每个网络所连元件引脚的集合比较。

python netcheck.py name.net file.cir [cir名=ms名 ...]

- 无极性两端元件（R/C/L）不看引脚号；**有极性的（V/I 源、二极管）和三极管严格比对引脚**——
  旧版对电源也不看引脚号，电源接反了照样报“一致”。
- 也被 verify.py 当模块用：parse_cir() 顺带解析元件数值。
"""
import collections
import re
import sys

# 元件类型 → 引脚名（按 SPICE 节点顺序）。Multisim：V 源 1=+、2=−；三极管 C/B/E。
PINS = {"Q": ["C", "B", "E"], "R": ["1", "2"], "C": ["1", "2"], "L": ["1", "2"],
        "V": ["1", "2"], "I": ["1", "2"], "D": ["A", "K"]}
POLAR = set("VIDQ")
_SUF = [("meg", 1e6), ("mil", 25.4e-6), ("t", 1e12), ("g", 1e9), ("k", 1e3), ("m", 1e-3),
        ("u", 1e-6), ("µ", 1e-6), ("n", 1e-9), ("p", 1e-12), ("f", 1e-15)]


def spice_num(s):
    """'10k' → 1e4，'2.2u' → 2.2e-6，'1Meg' → 1e6；不是数返回 None。"""
    m = re.match(r"^([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)([a-zA-Zµ]*)", s)
    if not m:
        return None
    v, suf = float(m.group(1)), m.group(2).lower()
    for k, mul in _SUF:
        if suf.startswith(k):
            return v * mul
    return v


def parse_cir(path):
    """返回 [(名字, 类型, 节点列表, 主值或None, 原始行)]。处理 + 续行，跳过 .subckt 内部。"""
    lines, out, sub = [], [], 0
    for raw in open(path, encoding="utf-8", errors="replace"):
        s = raw.split(";")[0].rstrip()
        if s.lstrip().startswith("+") and lines:
            lines[-1] += " " + s.lstrip()[1:]
        else:
            lines.append(s)
    # .param a=1 b=2k → 在元件行里替换 {a}
    params = {}
    for s in lines:
        if s.lower().lstrip().startswith(".param"):
            for k, v in re.findall(r"(\w+)\s*=\s*([^\s]+)", s[s.lower().find(".param") + 6:]):
                params[k.lower()] = v
    def subst(s):
        return re.sub(r"\{\s*(\w+)\s*\}", lambda m: params.get(m.group(1).lower(), m.group(0)), s)
    for i, s in enumerate(lines):
        s = subst(s)
        t = s.replace("(", " ( ").replace(")", " ) ").split() if re.search(r"(?i)\b(sin|pulse)\s*\(", s) else s.split()
        if i == 0 or not t or t[0][0] in "*":
            continue
        low = t[0].lower()
        if low.startswith(".subckt"):
            sub += 1; continue
        if low.startswith(".ends"):
            sub -= 1; continue
        if sub or t[0][0] == "." or t[0][0].upper() not in PINS:
            continue
        kind = t[0][0].upper()
        n = len(PINS[kind])
        nodes = t[1:1 + n]
        val = None
        rest = t[1 + n:]
        if kind in "RCL" and rest:
            val = spice_num(rest[0])
        elif kind == "V" and rest:
            # V a b 9 / V a b DC 9 / V a b SIN(偏置 幅值 频率 ...) → ("sin", 幅值, 频率)
            low = [x.lower() for x in rest]
            if "sin" in low:
                args = [spice_num(x) for x in rest[low.index("sin") + 1:] if x not in "()"]
                if len(args) >= 3 and None not in args[:3]:
                    val = ("sin", args[1], args[2])
            elif low[0] == "dc" and len(rest) > 1:
                val = spice_num(rest[1])
            elif re.match(r"^[-+]?\d", rest[0]):
                val = spice_num(rest[0])
        out.append((t[0], kind, nodes, val, s))
    return out


def ms_nets(net_text):
    ms = collections.defaultdict(set)
    for line in net_text.splitlines():
        if line.startswith("Netlist") or "->" in line:
            continue
        m = re.match(r"(\S+)\s+\S+\s+(\S+)\s+(\S+)\s*$", line)
        if m and m.group(1) not in ("Net",):
            ms[m.group(1)].add((m.group(2), m.group(3)))
    return ms


def _norm(s, kinds):
    return frozenset((c, p if kinds.get(c, "R") in POLAR else "*") for c, p in s)


def check(net_text, cir_path, alias=None):
    """返回 (不一致数, 报告行列表)。"""
    alias = alias or {}
    elems = parse_cir(cir_path)
    kinds = {alias.get(n, n): k for n, k, _, _, _ in elems}
    cir = collections.defaultdict(set)
    for name, kind, nodes, _, _ in elems:
        for pn, node in zip(PINS[kind], nodes):
            cir[node].add((alias.get(name, name), pn))
    ms = ms_nets(net_text)
    instr = sorted((k, c, p) for k, v in ms.items() for c, p in v if c.startswith("XSC"))
    ms_sets = {k: _norm({x for x in v if not x[0].startswith("XSC") and x[0] != "Ground"}, kinds) for k, v in ms.items()}
    ms_sets = {k: v for k, v in ms_sets.items() if v}
    cir_sets = {k: _norm(v, kinds) for k, v in cir.items()}
    inv = {v: k for k, v in ms_sets.items()}
    # Ground anchors the match. Net names are ignored, so without this a source wired upside down
    # (its two nets swapped as a whole) still looked like a perfect one-to-one match.
    ms_ground = {k for k, v in ms.items() if any(c == "Ground" for c, _ in v)}
    rep, bad = [], 0
    for k, v in sorted(cir_sets.items()):
        hit = inv.get(v)
        if k == "0" and hit is not None and ms_ground and hit not in ms_ground:
            rep.append(f"XX  0 (ground) {sorted(v)}\n    matches Multisim net {hit}, which is NOT the ground net "
                       f"{sorted(ms_ground)} — a source/part is probably reversed or ground is attached to the wrong node")
            bad += 1
            continue
        if hit is None:
            # 给出最接近的 Multisim 网络，方便定位（例如电源接反时能看到同一组元件引脚号不同）
            best = max(ms_sets.items(), key=lambda kv: len(kv[1] & v), default=(None, set()))
            rep.append(f"XX  {k:10} {sorted(v)}\n    closest Multisim net {best[0]}: {sorted(best[1])}")
            bad += 1
        else:
            rep.append(f"OK  {k:10} -> {hit}")
    for e in set(ms_sets.values()) - set(cir_sets.values()):
        rep.append(f"XX  extra net in Multisim: {sorted(e)}")
        bad += 1
    rep.append(f"instrument connections (not in the netlist report; check the PNG): {instr}")
    return bad, rep


if __name__ == "__main__":
    alias = dict(a.split("=") for a in sys.argv[3:])
    bad, rep = check(open(sys.argv[1], encoding="utf-8").read(), sys.argv[2], alias)
    print("\n".join(rep))
    print("mismatches:", bad)
