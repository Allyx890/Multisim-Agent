import sys, json, os, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msenv, msxml
idx = json.load(open(msenv.INDEX, encoding="utf-8"))
want = sys.argv[1:]
cache = {}
for key, lst in idx.items():
    fam = key.split("|")
    if not any(w == fam[1] or w == key for w in want): continue
    seen = set()
    for f, name in lst:
        if f not in cache: cache[f] = msxml.parse(os.path.join(msenv.SAMPLES, os.path.basename(f)))
        root = cache[f]
        for d in root.iter("CIITDiagram"):
            els = d.find("Elements")
            if els is None: continue
            ci = {i.get("CiID"): i.find("CiComponent") for i in els if i.get("Class") == "CiComponent"}
            objs = d.find("Components/CODComposite/Objects")
            for sid, s in msxml.symbols(objs):
                c = ci.get(s.get("CiComponent"))
                if c is None or c.get("LocalName", "").replace("&ASC", "") != name: continue
                pins = msxml.pins_of(s)
                M = msxml.T(s)
                rel = tuple((p[0], round(p[3] - M[4]), round(p[4] - M[5])) for p in pins)
                orient = "ident" if M[:4] == (1, 0, 0, 1) else "rot"
                sig = (orient, tuple(sorted((r[0], r[1], r[2]) for r in rel)))
                if sig in seen: continue
                seen.add(sig)
                print(f"{key:55} {name:6} {os.path.basename(f):45} {orient}  pins {rel}")
