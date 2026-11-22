#!/usr/bin/env python3
"""Route an instruction to a domain skill and load its context."""
import os, re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")

DOMAINS = {
    "electrical": ["feeder", "cable", "ampacity", "voltage drop", "conduit", "breaker", "ocpd",
                   "transformer", "relay", "grounding", "circuit", "panelboard", "switchgear",
                   "busway", "backfeed", "energiz", "interconnection", "solar", "photovoltaic",
                   "inverter", "utility", "protection coordin", "arc flash", "der "],
    "structural": ["beam", "column", "footing", "diaphragm", "shear", "seismic", "wind", "deck",
                   "roof", "shoring", "excavation", "settlement", "load", "steel", "concrete",
                   "anchor", "bracing", "tilt", "deflection", "lateral", "elevation", "pier"],
    "mep": ["hvac", "chiller", "cooling tower", "heat rejection", "flush", "pump", "duct",
            "pipe", "airflow", "crah", "plenum", "mep", "clash", "routing", "sprinkler",
            "plumb", "riser", "method of procedure", "commissioning", "cxa", "cable tray",
            "containment", "life-cycle cost"],
    "civil": ["road", "pavement", "conveyance", "spillway", "grading", "erosion", "culvert",
              "earthwork", "fill ", "compaction", "survey", "site plan", "trench", "asphalt",
              "drainage", "retention", "storm", "landscape", "street tree", "resubmittal",
              "sheet revision"],
    "fire": ["fire", "e119", "smoke", "egress", "flame", "nfpa", "spray", "sprinkler",
             "detection", "notification", "aass"],
    "cost": ["estimate", "cost", "quantity takeoff", "bid", "markup", "unit price",
             "labor rate", "contingency", " lcc", "life cycle", "life-cycle"],
    "permit": ["permit", "pto", "permission to operate", "authority having jurisdiction",
               "code official", "submittal", "approval", "variance", "pre-application",
               "entitlement"],
    "cfd": ["cfd", "mesh", "turbulence", "les ", "plume", "solver", "convergence", "openfoam",
            "discretisation", "residual", "energy spectrum"],
}

# directories that actually exist under skills/ - the loader can only read these
SKILLED = {"electrical", "structural", "mep", "civil"}


def _skill_dir(raw):
    """cost / fire / cfd / permit / bim live inside misc."""
    return raw if raw in SKILLED else "misc"
FAMILIES = {
    "memo": ["memo", "letter", "reply", "note", "memorandum", "narrative", "determination"],
    "package": ["package", "submission", "set of", "five files", "four files", "files:"],
    "calculation": ["schedule", "calculation", "takeoff", "register", "log", "tracker"],
    "model": ["ifc", "model", "3d", "clash-free"],
}


def path_hint(instruction):
    """The workspace path usually carries the project family (__electrical_task12__)."""
    m = re.search(r"/(?:filesystem|app|workspace)/[A-Za-z0-9_./\-]+", instruction[:900])
    if not m:
        return None
    p = m.group(0).lower()
    for token, dom in (("structural", "structural"), ("mechanical", "mep"),
                       ("electrical", "electrical"), ("civil", "civil"),
                       ("landscape", "civil"), ("fire", "fire"), ("cfd", "cfd"),
                       ("bim", "bim"), ("cost", "cost"), ("permit", "permit"),
                       ("mep", "mep")):
        if token in p:
            return dom
    return None


def route(instruction, spec=None):
    text = instruction[:4000].lower()
    head = instruction[:600].lower()
    scores = {}
    for dom, kws in DOMAINS.items():
        s = 0.0
        for kw in kws:
            n = text.count(kw)
            if n:
                s += min(n, 5)
            if kw in head:
                s += 6          # the opening paragraph carries the real subject
        scores[dom] = s
    ph = path_hint(instruction)
    if ph:
        scores[ph] = scores.get(ph, 0) + 9
    if spec and spec.get("mode") == "ifc":
        scores["mep"] = scores.get("mep", 0) + 4
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    domain = ranked[0][0] if ranked[0][1] > 0 else "misc"

    fam = "memo"
    for f, kws in FAMILIES.items():
        if any(k in instruction[:3000].lower() for k in kws):
            fam = f
            break
    if spec:
        m = spec.get("mode")
        if m == "zip" or len(spec.get("all_named_files") or []) > 1:
            fam = "package"
        elif m in ("ifc",):
            fam = "model"
        elif m == "xlsx":
            fam = "calculation"
    return {"domain": _skill_dir(domain), "subdomain": domain, "family": fam,
            "scores": dict(ranked[:4])}


def _read(path, cap):
    try:
        with open(path, encoding="utf-8") as f:
            t = f.read()
        return t[:cap]
    except OSError:
        return ""


def load_context(domain, budget=2800):
    """Shared skeleton first, then the domain skill, then its checklist."""
    parts = []
    shared = _read(os.path.join(ROOT, "_shared", "SKILL.md"), 1400)
    if shared:
        parts.append(("shared skeleton", shared))
    d = _read(os.path.join(ROOT, domain, "SKILL.md"), int(budget * 0.7))
    if not d:
        d = _read(os.path.join(ROOT, "misc", "SKILL.md"), int(budget * 0.7))
    if d:
        parts.append((f"{domain} skill", d))
    ck = _read(os.path.join(ROOT, domain, "checklist.md"), 900)
    if ck:
        parts.append((f"{domain} checklist", ck))
    return parts
