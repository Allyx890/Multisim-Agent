"""lint must catch each class of layout defect (no Multisim needed). Run: python tests/test_lint.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import msgen
import lint


def codes(doc, name):
    path = doc.save(os.path.join(msgen.msenv.OUT, "_lint_" + name))
    issues, _ = lint.lint(path)
    return {i["code"] for i in issues if i["level"] == "FAIL"}, issues


def base():
    d = msgen.Doc()
    v1 = d.add("VDC", "V1", 5, at=(108, 207), pin="1")
    g = d.add("GND", "0", at=(108, 360), pin="1")
    r1 = d.add("R_h", "R1", 1e3, at=(198, 171), pin="1")
    r2 = d.add("R_v", "R2", 1e3, at=(306, 225), pin="1")
    return d, v1, g, r1, r2


def good():
    d, v1, g, r1, r2 = base()
    jg = d.junction(108, 342)
    d.wire(v1["1"], r1["1"], via=[(108, 171)])
    d.wire(r1["2"], r2["1"], via=[(306, 171)])
    d.wire(v1["2"], jg); d.wire(jg, g["1"])
    d.wire(r2["2"], jg, via=[(306, 342)])
    d.probe("PR1", 252, 171, show=False, node="n1")
    return d


def check(name, doc, expect):
    got, issues = codes(doc, name)
    ok = (got == expect) if expect == set() else expect <= got
    print(f"{'ok ' if ok else 'BAD'} {name:16} expect {sorted(expect) or 'clean'} got {sorted(got) or 'clean'}")
    if not ok:
        for i in issues:
            print("     ", i)
    return ok


results = [check("clean", good(), set())]

# wire through R2's body
d, v1, g, r1, r2 = base()
jg = d.junction(108, 342)
d.wire(v1["1"], r1["1"], via=[(108, 171)]); d.wire(r1["2"], r2["1"], via=[(306, 171)])
d.wire(v1["2"], jg); d.wire(jg, g["1"]); d.wire(r2["2"], jg, via=[(306, 342)])
d.wire(r1["1"], r2["2"], via=[(198, 252), (306, 252)])           # passes through R2 body
results.append(check("through-body", d, {"through-body"}))

# T without junction: a wire from R3 ends on the middle of the V1-R1 wire with no junction
d, v1, g, r1, r2 = base()
jg = d.junction(108, 342)
d.wire(v1["1"], r1["1"], via=[(108, 171)])
d.wire(r1["2"], r2["1"], via=[(306, 171)])
d.wire(v1["2"], jg); d.wire(jg, g["1"])
d.wire(r2["2"], jg, via=[(306, 342)])
r3 = d.add("R_v", "R3", 1e3, at=(153, 225), pin="1")
d.w.wire(("p", r3.pins["1"][0]), ("p", r3.pins["1"][0]), [(153, 225), (153, 171)])   # ends on V1-R1 wire, no junction
results.append(check("t-no-junction", d, {"t-no-junction"}))

# overlap: second wire drawn on top of the ground return
d = good()
d.w.wire(("p", d.parts["R2"].pins["2"][0]), ("p", d.parts["V1"].pins["2"][0]), [(306, 270), (306, 342), (108, 342), (108, 243)])
results.append(check("overlap", d, {"overlap"}))

# probe not on a wire
d = good()
d.probe("PR2", 400, 400, show=False)
results.append(check("probe-off-wire", d, {"probe-off-wire"}))

# bodies overlap
d = good()
d.add("R_v", "R9", 1e3, at=(306, 234), pin="1")
results.append(check("body-overlap", d, {"body-overlap"}))

n = sum(not r for r in results)
print("test_lint:", "PASS" if n == 0 else f"{n} FAILED")
sys.exit(n)
