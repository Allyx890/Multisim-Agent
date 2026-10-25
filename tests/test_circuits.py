"""End-to-end tests: build -> lint -> Multisim -> verify against ngspice (needs Multisim + ngspice; minutes).

Positive cases must pass every layer; negative cases are deliberately broken and the verifier must FAIL
the right layer — a verifier that never fails proves nothing.
Run: python tests/test_circuits.py [--only NAME ...]
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MSA = os.path.join(ROOT, "scripts", "msa.py")
EX = os.path.join(ROOT, "examples")
PY = sys.executable


def check(build, cir, *args):
    """run msa.py check; return (exit code, report rows [(layer, item, status)])."""
    r = subprocess.run([PY, MSA, "check", build, "--cir", cir, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=os.path.dirname(build))
    m = re.search(r"report:\s+(\S+report\.md)", r.stdout) or re.search(r"\(report: (.+?report\.md)\)", r.stdout)
    rows = []
    if m and os.path.exists(m.group(1)):
        for line in open(m.group(1), encoding="utf-8"):
            p = [x.strip() for x in line.split("|")]
            if len(p) > 4 and p[3] in ("PASS", "WARN", "FAIL"):
                rows.append((p[1], p[2], p[3]))
    return r.returncode, rows, r.stdout + r.stderr


def scaffold(tmp, name, edit_build=None, edit_cir=None):
    """make NAME.py/NAME.cir from the `new` templates, optionally edited."""
    subprocess.run([PY, MSA, "new", name, "--dir", tmp], capture_output=True)
    for ext, fn in ((".py", edit_build), (".cir", edit_cir)):
        if fn:
            p = os.path.join(tmp, name + ext)
            s = open(p, encoding="utf-8").read()
            s2 = fn(s)
            assert s2 != s, f"edit of {name}{ext} changed nothing"
            open(p, "w", encoding="utf-8").write(s2)
    return os.path.join(tmp, name + ".py"), os.path.join(tmp, name + ".cir")


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def template_rc(tmp):
    b, c = scaffold(tmp, "t_rc")
    return "pass", check(b, c, "--tran", "5e-3", "--dt", "2e-6")


@case
def ce_amplifier(tmp):
    d = os.path.join(EX, "ce_amplifier")
    return "pass", check(os.path.join(d, "build.py"), os.path.join(d, "circuit.cir"), "--tran", "10e-3", "--dt", "5e-6")


@case
def seiler_oscillator(tmp):
    d = os.path.join(EX, "seiler_oscillator")
    return "pass", check(os.path.join(d, "build.py"), os.path.join(d, "circuit.cir"), "--tran", "300e-6", "--dt", "1e-8")


@case
def am_transmitter(tmp):
    d = os.path.join(EX, "am_transmitter")
    return "pass", check(os.path.join(d, "build.py"), os.path.join(d, "circuit.cir"), "--tran", "1.2e-3", "--dt", "1e-8")


@case
def am_link(tmp):
    d = os.path.join(EX, "am_link")
    code, rows, out = check(os.path.join(d, "build.py"), os.path.join(d, "circuit.cir"), "--tran", "2e-3", "--dt", "1e-8")
    if code == 0:
        r = subprocess.run([PY, os.path.join(d, "validate_recovery.py")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        code = r.returncode
        out += r.stdout + r.stderr
        rows.append(("F", "5 kHz recovery quality", "PASS" if code == 0 else "FAIL"))
    return "pass", (code, rows, out)


@case
def neg_reversed_source(tmp):
    """.cir says the source is the other way round -> layer A must FAIL."""
    b, c = scaffold(tmp, "n_rev", edit_cir=lambda s: s.replace("V1 in 0 SIN", "V1 0 in SIN"))
    return "fail:A", check(b, c, "--no-op")


@case
def neg_wrong_value(tmp):
    """.cir says R2 = 2k but the schematic has 1k -> layer B must FAIL."""
    b, c = scaffold(tmp, "n_val", edit_cir=lambda s: s.replace("R2 mid 0 1k", "R2 mid 0 2k"))
    return "fail:B", check(b, c, "--no-op")


@case
def neg_tmax_missing(tmp):
    """1 MHz source, no sim_settings -> TMAX 'calculate' -> layer C must FAIL."""
    b, c = scaffold(tmp, "n_tmax",
                    edit_build=lambda s: s.replace("(1.0, 1e3)", "(1.0, 1e6)").replace('d.sim_settings(tstop=5e-3, tmax=2e-6, ic="auto")', "pass"),
                    edit_cir=lambda s: s.replace("SIN(0 1 1k)", "SIN(0 1 1Meg)"))
    return "fail:C", check(b, c, "--no-op")


def main():
    only = sys.argv[sys.argv.index("--only") + 1:] if "--only" in sys.argv else None
    tmp = tempfile.mkdtemp(prefix="msa_test_")
    bad = 0
    try:
        for fn in CASES:
            if only and fn.__name__ not in only:
                continue
            expect, (code, rows, out) = fn(tmp)
            fails = {r[0] for r in rows if r[2] == "FAIL"}
            if expect == "pass":
                ok = code == 0 and not fails
            else:
                layer = expect.split(":")[1]
                ok = code != 0 and any(layer in f for f in fails)
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {fn.__name__:22} expect {expect:7} -> exit {code}, failing layers {sorted(fails) or '-'}")
            if not ok:
                print("\n".join("      " + l for l in out.strip().splitlines()[-25:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("test_circuits:", "PASS" if bad == 0 else f"{bad} FAILED")
    return bad


if __name__ == "__main__":
    sys.exit(main())
