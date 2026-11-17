#!/usr/bin/env python3
"""Inject the task107 hardening bugs into a clean ddnet tree, one patch per bug.

usage: mkbugs.py OUTDIR        (APP env var = repo root, default /app; tree must be clean at base)

Each bug is a list of exact (file, old, new) string edits; every `old` must occur exactly once.
After each bug the working-tree diff is written to OUTDIR/bug_NN.patch and the tree is reset.
"""
import os
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP", "/app"))
PLAYERS = "src/game/client/components/players.cpp"
GAMECLIENT = "src/game/client/gameclient.cpp"

BUGS = {
    # 1. Tee-hit test of the guide line uses half the tee size as radius, while the real hook
    #    (CCharacterCore::Tick) grabs any tee whose centre is within PhysicalSize() + 2 of the
    #    hook segment. A line passing over a tee's head/feet stays "no collision" although the
    #    hook fired along it grabs that tee.
    "bug_01": [(
        GAMECLIENT,
        """			if(distance(Position, ClosestPoint) < CCharacterCore::PhysicalSize() + 2.0f)
			{
				if(ClosestId == -1 || distance(HookPos, Position) < Distance)""",
        """			if(distance(Position, ClosestPoint) < CCharacterCore::PhysicalSize() / 2.0f + 2.0f)
			{
				if(ClosestId == -1 || distance(HookPos, Position) < Distance)""",
    )],
    # 2. Wide guide line: the quad's side vector is a reflection of the aim direction instead of
    #    a 90 degree rotation (pi/2 - a instead of a - pi/2). Exact for axis-aligned aims, the
    #    quad collapses towards 45 degrees (width |cos 2a|).
    "bug_02": [(
        PLAYERS,
        """		const vec2 PerpToAngle = normalize(vec2(Direction.y, -Direction.x)) * GameClient()->m_Camera.m_Zoom;""",
        """		const vec2 PerpToAngle = direction(pi / 2.0f - angle(Direction)) * GameClient()->m_Camera.m_Zoom;""",
    )],
    # 3. "Cleanup" that merges the hookable-colour block into the stop block and drops the
    #    !DoBreak guard: a wall that is only reached by the last, length-clamped step (where the
    #    real hook is already retracting and never attaches) is previewed as hookable.
    "bug_03": [(
        PLAYERS,
        """		if(!DoBreak && Hit && Hit != TILE_TELEINHOOK)
		{
			if(Hit != TILE_NOHOOK)
			{
				HookCollColor = color_cast<ColorRGBA>(ColorHSLA(g_Config.m_ClHookCollColorHookableColl));
			}
		}

		if(Hit && Hit != TILE_TELEINHOOK)
			break;
""",
        """		if(Hit && Hit != TILE_TELEINHOOK)
		{
			if(Hit != TILE_NOHOOK)
				HookCollColor = color_cast<ColorRGBA>(ColorHSLA(g_Config.m_ClHookCollColorHookableColl));
			break;
		}
""",
    )],
    # 4. The tee test of each step runs over the whole, unclipped step instead of stopping at the
    #    wall the step ran into, so a tee standing right behind a thin wall turns the line into a
    #    "tee" line that runs through the wall, while the real hook attaches to the wall.
    "bug_04": [(
        PLAYERS,
        """		if(ClientId >= 0 && GameClient()->IntersectCharacter(OldPos, FinishPos, FinishPos, ClientId) != -1)""",
        """		if(ClientId >= 0 && GameClient()->IntersectCharacter(OldPos, NewPos, FinishPos, ClientId) != -1)""",
    )],
}


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(APP), *args], check=check, capture_output=True, text=True).stdout


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    assert git("status", "--porcelain", "--untracked-files=no").strip() == "", "tree not clean"
    for name, edits in BUGS.items():
        for rel, old, new in edits:
            p = APP / rel
            s = p.read_text(encoding="utf-8")
            assert s.count(old) == 1, (name, rel, s.count(old))
            p.write_text(s.replace(old, new), encoding="utf-8", newline="")
        (out / f"{name}.patch").write_text(git("diff"), encoding="utf-8", newline="")
        git("checkout", "-q", "--", ".")
        print("wrote", out / f"{name}.patch")


if __name__ == "__main__":
    main()
