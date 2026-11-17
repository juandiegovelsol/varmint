#!/usr/bin/env python3
"""Apply NON-oracle fixes (or deliberately wrong ones) on top of the all-bugs tree in /app.

usage: altfix.py alt|wrong_radius|wrong_reach|wrong_width
  alt          : a different, behaviourally correct fix for every defect, keeping the base loop
                 (no upstream rewrite): float tunings, own guard placement, other-sign normal...
  wrong_radius : alt, but the tee-hit radius "fixed" to a generous 64 units (over-reports tees)
  wrong_reach  : alt, but the reach defect "fixed" by never using the hookable colour
  wrong_width  : alt, but the wide-line defect "fixed" by always drawing the thin line
"""
import sys

PL = "/app/src/game/client/components/players.cpp"
GC = "/app/src/game/client/gameclient.cpp"


def edit(path, old, new):
    s = open(path, encoding="utf-8", newline="").read()
    assert s.count(old) == 1, (path, old[:70], s.count(old))
    open(path, "w", encoding="utf-8", newline="").write(s.replace(old, new))


ALT = [
    # original defect: keep the tunings as float (and no early-out for 0 < speed < 1)
    (PL, """	int HookSpeed = GameClient()->m_aClients[ClientId].m_Predicted.m_Tuning.m_HookFireSpeed;
	if(HookSpeed <= 0)
		return;

	int HookLength = GameClient()->m_aClients[ClientId].m_Predicted.m_Tuning.m_HookLength;""",
     """	const float HookSpeed = GameClient()->m_aClients[ClientId].m_Predicted.m_Tuning.m_HookFireSpeed;
	if(!(HookSpeed > 0.0f))
		return;

	const float HookLength = GameClient()->m_aClients[ClientId].m_Predicted.m_Tuning.m_HookLength;"""),
    # reach: only a step that is still flying may attach (written as a separate flag)
    (PL, """		if(Hit && Hit != TILE_TELEINHOOK)
		{
			if(Hit != TILE_NOHOOK)
				HookCollColor = color_cast<ColorRGBA>(ColorHSLA(g_Config.m_ClHookCollColorHookableColl));
			break;
		}
""", """		if(Hit && Hit != TILE_TELEINHOOK)
		{
			const bool StillFlying = !DoBreak;
			if(Hit != TILE_NOHOOK && StillFlying)
				HookCollColor = color_cast<ColorRGBA>(ColorHSLA(g_Config.m_ClHookCollColorHookableColl));
			break;
		}
"""),
    # tee behind wall: test the part of the step in front of the wall only (separate variable)
    (PL, """		if(ClientId >= 0 && GameClient()->IntersectCharacter(OldPos, NewPos, FinishPos, ClientId) != -1)""",
     """		const vec2 StepEnd = FinishPos;
		if(ClientId >= 0 && GameClient()->IntersectCharacter(OldPos, StepEnd, FinishPos, ClientId) != -1)"""),
    # tee radius: same rule as the hook, written with the size vector
    (GC, """			if(distance(Position, ClosestPoint) < CCharacterCore::PhysicalSize() / 2.0f + 2.0f)""",
     """			if(distance(Position, ClosestPoint) < CCharacterCore::PhysicalSizeVec2().x + 2.0f)"""),
    # width: the other-handed normal
    (PL, """		const vec2 PerpToAngle = direction(pi / 2.0f - angle(Direction)) * GameClient()->m_Camera.m_Zoom;""",
     """		const vec2 PerpToAngle = vec2(-Direction.y, Direction.x) * GameClient()->m_Camera.m_Zoom;"""),
]

WRONG = {
    "wrong_radius": (GC, """CCharacterCore::PhysicalSizeVec2().x + 2.0f)""", """64.0f)"""),
    "wrong_reach": (PL, """			if(Hit != TILE_NOHOOK && StillFlying)""", """			if(false && StillFlying)"""),
    "wrong_width": (PL, """	if(HookCollSize > 0)
	{
		std::vector<IGraphics::CFreeformItem>""", """	if(false)
	{
		std::vector<IGraphics::CFreeformItem>"""),
}

mode = sys.argv[1]
for e in ALT:
    edit(*e)
if mode != "alt":
    edit(*WRONG[mode])
print("applied", mode)
