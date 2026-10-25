"""Schematic lint: geometry checks on a generated Multisim XML/.ms14 — no Multisim needed, runs in < 1 s.

python lint.py design.xml|design.ms14 [--json]

Catches layout defects an agent cannot see without looking at the PNG, including ones that change
connectivity (a wire end resting on the middle of another wire is NOT connected in Multisim unless a
junction is placed there):

  FAIL  diagonal       wire segment not horizontal/vertical
  FAIL  through-body   wire segment passes through a component body
  FAIL  overlap        two different wires run on top of each other (collinear overlap)
  FAIL  t-no-junction  a wire end / pin lies on the middle of another wire without being connected to it
  FAIL  body-overlap   two component bodies overlap
  FAIL  off-sheet      something outside the drawing sheet
  FAIL  probe-off-wire probe not sitting on a wire (Multisim ignores it; verify can't read it)
  WARN  off-grid       point not on the 9-unit grid
  WARN  crossing       wires of different nets cross (allowed, but a cleaner layout avoids it)
  WARN  dangling-pin   a component pin with nothing connected
Exit code = number of FAILs.
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msxml

GRID = 9


class UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def load(path):
    root = msxml.parse(path)
    d, objs, refs = msxml.diagram(root)
    bodies, pins, junc, ends, links, probes, texts = [], {}, {}, {}, {}, [], []
    for sid, s in msxml.symbols(objs):
        name = s.get("InstanceRefDes", "").replace("&ASC", "") or "XSC"
        ts = msxml.T(s)
        for it in s.find("Objects"):
            if it.get("Class") == "CIITSymbolBorderRect":
                b = it.find("CIITSymbolBorderRect")
                tb = msxml.T(b)
                pts = [msxml.apply(ts, *msxml.apply(tb, float(b.get(k + "X")), float(b.get(k + "Y")))) for k in ("pt0", "pt1")]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                bodies.append((name, min(xs), min(ys), max(xs), max(ys)))
        for pn, cid, pc, x, y in msxml.pins_of(s):
            pins[cid] = (name, pn, x, y)
    for it in objs:
        cl = it.get("Class")
        if cl == "CODPinComp":
            p = it.find("CODPinComp")
            junc[it.get("ID")] = msxml.apply(msxml.T(p), float(p.get("CenterX")), float(p.get("CenterY")))
        elif cl == "CIITLinkComp":
            l = it.find("CIITLinkComp")
            pts = [(float(q.get("X")), float(q.get("Y"))) for q in l.find("Points")]
            links[it.get("ID")] = (pts, l.get("Connect1"), l.get("Connect2"))
        elif cl == "CIITProbeExtComponent":
            p = it.find("CIITProbeExtComponent")
            probes.append((float(p.get("Transformer-M20")), float(p.get("Transformer-M21"))))
    for it in refs:
        if it.get("Class") == "CODPinComp" and len(it):
            p = it.find("CODPinComp")
            tg = [k.get("ID") for k in p.find("ConnectList")] if p.find("ConnectList") is not None else []
            ends[it.get("ID")] = (float(p.get("CenterX")), float(p.get("CenterY")), tg)
    # sheet extent from the title-block/border drawing
    bx, by = [], []
    bg = d.find("Background")
    if bg is not None:
        for e in bg.iter():
            for kx, ky in (("pt0X", "pt0Y"), ("pt1X", "pt1Y")):
                if e.get(kx) is not None:
                    x, y = msxml.apply(msxml.T(e), float(e.get(kx)), float(e.get(ky)))
                    bx.append(x); by.append(y)
    sheet = (min(bx), min(by), max(bx), max(by)) if bx else None
    return bodies, pins, junc, ends, links, probes, sheet


def segs(pts):
    return list(zip(pts, pts[1:]))


def on_seg(p, a, b, strict=True):
    """p on segment a-b (axis-aligned). strict: excluding the two ends."""
    (x, y), (x1, y1), (x2, y2) = p, a, b
    if x1 == x2 == x and min(y1, y2) <= y <= max(y1, y2):
        return not strict or (y != y1 and y != y2)
    if y1 == y2 == y and min(x1, x2) <= x <= max(x1, x2):
        return not strict or (x != x1 and x != x2)
    return False


def seg_hits_box(a, b, box, pad=1.0):
    (x1, y1), (x2, y2) = a, b
    _, bx0, by0, bx1, by1 = box
    bx0, by0, bx1, by1 = bx0 + pad, by0 + pad, bx1 - pad, by1 - pad
    if bx0 >= bx1 or by0 >= by1:
        return False
    if y1 == y2:
        return by0 < y1 < by1 and max(x1, x2) > bx0 and min(x1, x2) < bx1
    if x1 == x2:
        return bx0 < x1 < bx1 and max(y1, y2) > by0 and min(y1, y2) < by1
    return False


def lint(path):
    bodies, pins, junc, ends, links, probes, sheet = load(path)
    issues = []

    def add(level, code, msg):
        issues.append({"level": level, "code": code, "msg": msg})

    # nets (union-find over links, endpoints, pins, junctions)
    uf = UF()
    for lid, (pts, c1, c2) in links.items():
        for c in (c1, c2):
            uf.union(lid, c)
            if c in ends:
                for t in ends[c][2]:
                    uf.union(c, t)
    net_of_link = {lid: uf.find(lid) for lid in links}
    pin_net = {cid: uf.find(cid) for cid in pins}

    all_segs = [(lid, a, b) for lid, (pts, _, _) in links.items() for a, b in segs(pts)]
    for lid, a, b in all_segs:
        if a[0] != b[0] and a[1] != b[1]:
            add("FAIL", "diagonal", f"wire {lid} segment {a}->{b} is diagonal")
    # through-body
    for lid, a, b in all_segs:
        for box in bodies:
            if seg_hits_box(a, b, box):
                add("FAIL", "through-body", f"wire {lid} segment {a}->{b} passes through {box[0]} body {tuple(round(v) for v in box[1:])}")
    # overlap between different wires
    for i in range(len(all_segs)):
        l1, a1, b1 = all_segs[i]
        for j in range(i + 1, len(all_segs)):
            l2, a2, b2 = all_segs[j]
            if l1 == l2:
                continue
            if a1[1] == b1[1] == a2[1] == b2[1]:
                lo, hi = max(min(a1[0], b1[0]), min(a2[0], b2[0])), min(max(a1[0], b1[0]), max(a2[0], b2[0]))
            elif a1[0] == b1[0] == a2[0] == b2[0]:
                lo, hi = max(min(a1[1], b1[1]), min(a2[1], b2[1])), min(max(a1[1], b1[1]), max(a2[1], b2[1]))
            else:
                continue
            if hi - lo > 0:
                add("FAIL", "overlap", f"wires {l1} and {l2} overlap along {a1}->{b1} / {a2}->{b2}")
    # T without junction: endpoints / pins resting on the interior of another wire
    points = []
    for lid, (pts, c1, c2) in links.items():
        points.append((pts[0], net_of_link[lid], f"end of wire {lid}"))
        points.append((pts[-1], net_of_link[lid], f"end of wire {lid}"))
    for cid, (ref, pn, x, y) in pins.items():
        points.append(((x, y), pin_net[cid], f"pin {ref}.{pn}"))
    for p, pnet, what in points:
        for lid, a, b in all_segs:
            if on_seg(p, a, b) and net_of_link[lid] != pnet:
                add("FAIL", "t-no-junction", f"{what} at {p} touches the middle of wire {lid} ({a}->{b}) but is not connected — "
                    f"split the wire with d.junction() if they should connect, otherwise move it")
    # crossings between different nets
    ncross = 0
    for i in range(len(all_segs)):
        l1, a1, b1 = all_segs[i]
        for j in range(i + 1, len(all_segs)):
            l2, a2, b2 = all_segs[j]
            if net_of_link[l1] == net_of_link[l2]:
                continue
            h, v = ((a1, b1), (a2, b2)) if a1[1] == b1[1] else ((a2, b2), (a1, b1))
            if h[0][1] == h[1][1] and v[0][0] == v[1][0]:
                x, y = v[0][0], h[0][1]
                if min(h[0][0], h[1][0]) < x < max(h[0][0], h[1][0]) and min(v[0][1], v[1][1]) < y < max(v[0][1], v[1][1]):
                    ncross += 1
                    if ncross <= 5:
                        add("WARN", "crossing", f"wires {l1} and {l2} (different nets) cross at {(x, y)}")
    if ncross > 5:
        add("WARN", "crossing", f"... {ncross} crossings in total")
    # bodies overlapping
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            a, b = bodies[i], bodies[j]
            if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]:
                add("FAIL", "body-overlap", f"{a[0]} and {b[0]} bodies overlap")
    # off-grid
    offg = set()
    for lid, (pts, _, _) in links.items():
        for p in pts:
            if p[0] % GRID or p[1] % GRID:
                offg.add(p)
    for p in junc.values():
        if p[0] % GRID or p[1] % GRID:
            offg.add(p)
    for p in sorted(offg)[:5]:
        add("WARN", "off-grid", f"point {p} is not on the {GRID}-unit grid")
    # probes
    for p in probes:
        if not any(on_seg(p, a, b, strict=False) for _, a, b in all_segs):
            add("FAIL", "probe-off-wire", f"probe at {p} is not on any wire")
    # dangling pins (instruments excluded)
    connected = {t for e in ends.values() for t in e[2]}
    for cid, (ref, pn, x, y) in pins.items():
        if cid not in connected and ref not in ("XSC", ""):
            add("WARN", "dangling-pin", f"pin {ref}.{pn} at {(x, y)} is not connected")
    # sheet
    if sheet:
        x0, y0, x1, y1 = sheet
        for name, bx0, by0, bx1, by1 in bodies:
            if bx0 < x0 or by0 < y0 or bx1 > x1 or by1 > y1:
                add("FAIL", "off-sheet", f"{name} is outside the sheet {tuple(round(v) for v in sheet)}")
    return issues, dict(parts=len(bodies), wires=len(links), junctions=len(junc), probes=len(probes))


def main():
    path = sys.argv[1]
    issues, stats = lint(path)
    nf = sum(i["level"] == "FAIL" for i in issues)
    if "--json" in sys.argv:
        print(json.dumps({"stats": stats, "fails": nf, "issues": issues}, ensure_ascii=False, indent=1))
    else:
        for i in issues:
            print(f"[{i['level']}] {i['code']:15} {i['msg']}")
        print(f"lint: {stats['parts']} parts, {stats['wires']} wires, {stats['junctions']} junctions, "
              f"{stats['probes']} probes -> {nf} FAIL, {len(issues) - nf} WARN")
    return nf


if __name__ == "__main__":
    sys.exit(min(main(), 100))
