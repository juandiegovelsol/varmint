import pathlib
import re
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(r"c:\Users\juand\OneDrive\Documentos\Outlier\varmint\task109")
F2P = [
    "missileIsDrawnBeforeForegroundLayer",
    "carriedRocketPointsWhereTheCarPoints",
    "firedRocketFliesWhereTheCarPoints",
    "rocketExhaustComesOutOfItsTail",
    "rocketShadowHasTheRocketsOrientation",
    "vehicleShadowFallsLikeEveryOtherShadow",
    "viewLooksAheadOfTheCarWhicheverWayItHeads",
]
SHORT = ["zorder", "carried", "fired", "exhaust", "rktShadow", "carShadow", "camera"]

print(f"{'attempt':8} {'mode':10} {'runs':>4} {'rew=1':>5}  " + " ".join(f"{s:>9}" for s in SHORT))
for attempt in sorted(p for p in ROOT.glob("Attempt*") if p.is_dir()):
    for mode in ("without_images", "with_images"):
        runs = [d for d in (attempt / "Trials" / mode).glob("*") if (d / "verifier" / "junit.xml").exists()]
        if not runs:
            continue
        passed = {t: 0 for t in F2P}
        full = 0
        for run in runs:
            root = ET.parse(run / "verifier" / "junit.xml").getroot()
            ok = {}
            for case in root.iter("testcase"):
                bad = any(child.tag in ("failure", "error") for child in case)
                ok[case.get("name")] = not bad
            for t in F2P:
                passed[t] += 1 if ok.get(t) else 0
            reward = (run / "verifier" / "reward.txt").read_text().strip()
            full += 1 if re.match(r"1(\.0)?$", reward) else 0
        label = "no-img" if mode == "without_images" else "with-img"
        print(f"{attempt.name:8} {label:10} {len(runs):>4} {full:>5}  "
              + " ".join(f"{passed[t]:>6}/{len(runs)}" for t in F2P))
