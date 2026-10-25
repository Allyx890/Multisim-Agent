#!/usr/bin/env python3
"""multisim-agent command line — one entry point for everything.

  python scripts/msa.py doctor                 check the environment (Multisim, samples, ngspice, numpy) and say how to fix gaps
  python scripts/msa.py setup [--force]        one-time init: unpack Multisim samples, build part index, compile COM helpers
  python scripts/msa.py parts [--json]         templates you can place, with pin offsets and body boxes (plan layout from this)
  python scripts/msa.py models KEY...          exact .MODEL text Multisim uses for a template (paste into your .cir)
  python scripts/msa.py new NAME [--dir D]     scaffold NAME.py (build script) + NAME.cir (reference netlist) to fill in
  python scripts/msa.py check NAME.py --cir NAME.cir [--tran T] [--deliver DIR] [verify options]
                                               THE golden path: build -> lint -> open in Multisim -> verify against ngspice
  python scripts/msa.py lint FILE.xml          layout geometry checks only (fast, no Multisim)
  python scripts/msa.py verify FILE --cir C [..]   verification only (see verify.py --help)
  python scripts/msa.py render FILE            open in Multisim, export FILE.png + netlist FILE.net
  python scripts/msa.py sim FILE.ms14 T|--op   run Multisim's own simulator on the probes
  python scripts/msa.py simset FILE [--tmax ..] show / fix simulation settings stored in the file
  python scripts/msa.py unpack FILE.ms14 / pack FILE.xml   .ms14 <-> XML
  python scripts/msa.py selftest [--quick]     run the test-suite (unit tests; full Multisim+ngspice suite unless --quick)
"""
import functools
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
PY = sys.executable
print = functools.partial(print, flush=True)   # keep our lines in order with child-process output


def run_script(name, args):
    return subprocess.call([PY, os.path.join(HERE, name), *args])


# ---------------------------------------------------------------- doctor
def doctor(args):
    import msenv
    rows = []

    def row(ok, what, detail, fix=""):
        rows.append({"ok": bool(ok), "check": what, "detail": detail, "fix": fix})

    row(sys.version_info >= (3, 8), "Python >= 3.8", sys.version.split()[0], "install Python 3.8+")
    row(os.name == "nt", "Windows", os.name, "Multisim and its COM interface only exist on Windows")
    for mod in ("numpy", "matplotlib"):
        try:
            __import__(mod)
            row(True, f"python package {mod}", "ok")
        except ImportError:
            row(False, f"python package {mod}", "missing", f"{PY} -m pip install {mod}   (needed by verify/sim/plots)")
    row(msenv.MULTISIM_DIR and os.path.exists(msenv.MSINTERFACE or ""), "Multisim install (MSInterface.dll)",
        msenv.MULTISIM_DIR or "not found", "install NI Multisim 14.x, or set MULTISIM_DIR to the folder with MSInterface.dll")
    com = False
    try:
        import winreg
        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "MultisimInterface.MultisimApp")
        com = True
    except Exception:
        pass
    row(com, "COM class MultisimInterface.MultisimApp", "registered" if com else "not registered",
        "repair/reinstall Multisim (the automation interface is part of the full install)")
    row(msenv.SAMPLES_SRC, "Multisim samples (*.ms14 templates)", msenv.SAMPLES_SRC or "not found",
        "install the Multisim sample circuits, or set MULTISIM_SAMPLES")
    row(os.path.exists(msenv.PS32), "32-bit PowerShell", msenv.PS32, "")
    row(msenv.CSC, ".NET Framework C# compiler (csc.exe)", msenv.CSC or "not found", "enable .NET Framework 4.x")
    ng_ok = False
    if msenv.NGSPICE:
        try:
            r = subprocess.run([msenv.NGSPICE, "-v"], capture_output=True, timeout=30)
            ng_ok = b"ngspice" in (r.stdout + r.stderr).lower()
        except Exception:
            pass
    row(ng_ok, "ngspice (reference simulator for verify)", msenv.NGSPICE or "not found",
        "download ngspice for Windows (sourceforge.net/projects/ngspice), unzip, set NGSPICE=...\\Spice64\\bin\\ngspice_con.exe")
    inited = all(os.path.exists(p) for p in (msenv.BASE, msenv.INDEX, os.path.join(msenv.BIN, "msim.exe"), os.path.join(msenv.BIN, "msop.exe")))
    row(inited, "cache initialised (setup)", msenv.CACHE, f"{PY} {os.path.join(HERE, 'msa.py')} setup")
    if "--json" in args:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for r in rows:
            print(f"[{'OK' if r['ok'] else 'MISSING'}] {r['check']}: {r['detail']}" + ("" if r["ok"] or not r["fix"] else f"\n          fix: {r['fix']}"))
        bad = [r for r in rows if not r["ok"]]
        print("\nAll good — next: msa.py new NAME" if not bad else f"\n{len(bad)} problem(s). Fix them, then run doctor again.")
    return sum(not r["ok"] for r in rows)


# ---------------------------------------------------------------- parts / models
def parts(args):
    import msgen
    t = msgen.templates()
    if "--json" in args:
        print(json.dumps(t, ensure_ascii=False, indent=1))
        return 0
    print("Pin offsets are relative to ref_pin; body = (x0, y0, x1, y1) relative to ref_pin. Grid = 9. y grows downward.")
    print("Place with d.add(KEY, REF, VALUE, at=(x, y), pin=PIN): pin PIN lands exactly on (x, y).\n")
    print(f"{'key':10} {'ref':4} {'pins (dx,dy)':58} {'body':22} model")
    for k, v in t.items():
        pins = ", ".join(f"{p}{tuple(int(c) for c in xy)}" for p, xy in v["pins"].items())
        print(f"{k:10} {v['ref_pin']:4} {pins:58} {str(v['body']):22} {v['model'] or ''}")
    print("\nValues: R/C/L/VDC take a number in SI units (4.7e3, 180e-12); VAC takes (peak_volts, freq_hz).")
    return 0


def models(args):
    import msgen
    keys = [a for a in args if not a.startswith("-")] or [k for k in msgen.TPL if msgen.model_name(k)]
    for k in keys:
        txt = msgen.model_text(k)
        if txt:
            print(f"* template {k}: reference this model name in the .cir -> {msgen.model_name(k)}")
            print(txt.strip() + "\n")
        else:
            print(f"* template {k}: no model (ideal/virtual part)\n")
    return 0


# ---------------------------------------------------------------- new
def new(args):
    if not args:
        print("usage: msa.py new NAME [--dir DIR]"); return 2
    name = args[0]
    d = args[args.index("--dir") + 1] if "--dir" in args else os.getcwd()
    os.makedirs(d, exist_ok=True)
    tpl = os.path.join(ROOT, "templates")
    made = []
    for src, dst in (("build_template.py", name + ".py"), ("netlist_template.cir", name + ".cir")):
        p = os.path.join(d, dst)
        if os.path.exists(p):
            print(f"exists, not overwritten: {p}")
            continue
        text = open(os.path.join(tpl, src), encoding="utf-8").read().replace("__NAME__", name).replace("__SCRIPTS__", HERE.replace("\\", "/"))
        open(p, "w", encoding="utf-8").write(text)
        made.append(p)
    for p in made:
        print("created", p)
    print(f"\nNext: 1) write the circuit in {name}.cir and simulate it in ngspice until it is right;"
          f"\n      2) lay it out in {name}.py (msa.py parts shows pin offsets);"
          f"\n      3) msa.py check {name}.py --cir {name}.cir --tran <seconds>")
    return 0


# ---------------------------------------------------------------- check (golden path)
def check(args):
    if not args:
        print("usage: msa.py check BUILD.py|DESIGN.xml --cir REF.cir [--tran T] [--deliver DIR] [--force] [verify options]")
        return 2
    target, rest = args[0], args[1:]
    deliver = None
    if "--deliver" in rest:
        i = rest.index("--deliver"); deliver = rest[i + 1]; del rest[i:i + 2]
    force = "--force" in rest
    rest = [a for a in rest if a != "--force"]
    # 1 build
    if target.endswith(".py"):
        print(f"== 1/3 build {target}")
        r = subprocess.run([PY, target], capture_output=True, text=True, encoding="utf-8", errors="replace")
        sys.stdout.write(r.stdout[-2000:]); sys.stderr.write(r.stderr[-4000:])
        if r.returncode:
            print("BUILD FAILED — fix the script (the error above usually names the part/pin)."); return 1
        xml = next((l.strip() for l in reversed(r.stdout.splitlines()) if l.strip().endswith(".xml")), None)
        if not xml:
            print("The build script must print the path returned by d.save(...) (print(d.save('name')))."); return 1
    else:
        xml = target
    # 2 lint
    import lint
    print(f"== 2/3 lint {xml}")
    issues, stats = lint.lint(xml)
    for i in issues:
        print(f"[{i['level']}] {i['code']:15} {i['msg']}")
    nf = sum(i["level"] == "FAIL" for i in issues)
    print(f"lint: {stats} -> {nf} FAIL")
    if nf and not force:
        print("LINT FAILED — fix the layout first (or --force to verify anyway)."); return 1
    # 3 verify (renders in Multisim too)
    print("== 3/3 verify (Multisim + ngspice)")
    code = subprocess.call([PY, os.path.join(HERE, "verify.py"), xml, *rest])
    base = os.path.splitext(os.path.abspath(xml))[0]
    if code == 0:
        print(f"\nALL CHECKS PASSED.\n  schematic: {base}.ms14\n  preview:   {base}.png   (look at it once)\n  report:    {base}_verify\\report.md")
        if deliver:
            os.makedirs(deliver, exist_ok=True)
            for ext in (".ms14", ".png"):
                shutil.copy2(base + ext, deliver)
            if os.path.exists(base + "_verify/compare.png"):
                shutil.copy2(base + "_verify/compare.png", os.path.join(deliver, os.path.basename(base) + "_compare.png"))
            print(f"  delivered to {deliver}")
    else:
        print(f"\nVERIFY FAILED ({code} item(s)). Read {base}_verify\\report.md; the FAIL lines say what differs. "
              f"Do not deliver until it passes.")
    return code


# ---------------------------------------------------------------- selftest
def selftest(args):
    tests = os.path.join(ROOT, "tests")
    codes = []
    env = dict(os.environ, QUICK="1") if "--quick" in args else None
    for t in ("test_unit.py", "test_lint.py"):
        print(f"\n######## {t}")
        codes.append(subprocess.call([PY, os.path.join(tests, t)], env=env))
    if "--quick" not in args:
        print("\n######## test_circuits.py (Multisim + ngspice, several minutes)")
        codes.append(subprocess.call([PY, os.path.join(tests, "test_circuits.py"), *[a for a in args if a != "--quick"]]))
    n = sum(c != 0 for c in codes)
    print(f"\nselftest: {'PASS' if n == 0 else f'{n} suite(s) FAILED'}")
    return n


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__); return 0
    cmd, args = sys.argv[1], sys.argv[2:]
    table = {
        "doctor": doctor, "parts": parts, "models": models, "new": new, "check": check, "selftest": selftest,
        "setup": lambda a: run_script("setup.py", a),
        "lint": lambda a: run_script("lint.py", a),
        "verify": lambda a: run_script("verify.py", a),
        "render": lambda a: run_script("render.py", a),
        "sim": lambda a: run_script("sim.py", a),
        "simset": lambda a: run_script("simset.py", a),
        "unpack": lambda a: run_script("ms14.py", ["x", *a]),
        "pack": lambda a: run_script("ms14.py", ["c", *a]),
    }
    if cmd not in table:
        print(f"unknown command {cmd!r}\n" + __doc__); return 2
    return table[cmd](args)


if __name__ == "__main__":
    sys.exit(min(main() or 0, 100))
