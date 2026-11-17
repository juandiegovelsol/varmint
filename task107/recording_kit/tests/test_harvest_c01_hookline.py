"""Behavioural tests for the hook collision line (the in-game preview of where the grappling hook
will go and what it will hit).

Every test drives the real DDNet-Server and DDNet client headlessly (Xvfb + Mesa llvmpipe) on a
small map written by this file, aims the player with the real mouse path (xdotool), takes two
in-engine screenshots of the same settled scene - one with the client's "always show my hook
collision line" setting off, one with it on - and inspects only the pixels that turning the
setting on changed. The checks are what a player sees: whether a line is drawn along the aim, how
far it reaches, how wide it is, and which of the three legend colours of the settings page
("Nothing hookable", "Something hookable", "A Tee") it uses. The expected answers come from the
game's own hook rules (a hook leaves the tee 1.5 tee-sizes out, advances hook_fire_speed units per
tick, gives up once the next step would pass hook_length, attaches to hookable ground, bounces off
unhookable ground, and grabs a tee whose centre comes within one tee-size plus 2 units of its
path). Nothing here reads source code or internal names.
"""
import colorsys
import functools
import math
import os
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------------------------
# Map writer: a minimal DDNet datafile (version 4) with a sky quad, two design tile layers and a
# game layer, built from an ASCII layout.
#   '.' air   '#' hookable ground   'x' unhookable ground   'S' first spawn   'D' second spawn
# The first player to join gets 'S' (first spawn in row-major order); a second player (the dummy)
# gets 'D', the free spawn farthest away.
# ---------------------------------------------------------------------------------------------
TILE_SOLID, TILE_NOHOOK, TILE_SPAWN = 1, 3, 192


def _name_ints(name, n=3):
    raw = name.encode()[: n * 4 - 1].ljust(n * 4, b"\0")
    ints = []
    for i in range(n):
        b = raw[i * 4: i * 4 + 4]
        v = ((b[0] + 128) << 24) | ((b[1] + 128) << 16) | ((b[2] + 128) << 8) | (b[3] + 128)
        ints.append(struct.unpack("<i", struct.pack("<I", v & 0xFFFFFFFF))[0])
    ints[-1] &= ~0xFF
    return ints


def write_map(path, rows):
    h = len(rows)
    w = max(len(r) for r in rows)
    grid = [r.ljust(w, ".") for r in rows]

    def at(x, y):  # outside the map the game repeats the border tiles, so the edges do too
        return grid[min(max(y, 0), h - 1)][min(max(x, 0), w - 1)]

    game, grass, unhook = bytearray(), bytearray(), bytearray()
    for y in range(h):
        for x in range(w):
            c = at(x, y)
            g = gr = un = 0
            if c == "#":
                g = TILE_SOLID
                up, dn = at(x, y - 1) != "#", at(x, y + 1) != "#"
                lf, rt = at(x - 1, y) != "#", at(x + 1, y) != "#"
                gr = (4 if up and lf else 5 if up and rt else 36 if dn and lf else 37 if dn and rt
                      else 16 if up else 52 if dn else 20 if lf else 21 if rt else 1)
            elif c == "x":
                g, un = TILE_NOHOOK, 1
            elif c in "SD":
                g = TILE_SPAWN
            game += bytes((g, 0, 0, 0))
            grass += bytes((gr, 0, 0, 0))
            unhook += bytes((un, 0, 0, 0))

    datas = [b"grass_main\0", b"generic_unhookable\0"]
    s = 1200 << 10
    quad = [-s, -s, s, -s, -s, s, s, s, 0, 0]
    quad += [94, 132, 174, 255] * 2 + [204, 232, 255, 255] * 2
    quad += [0, 0] * 4 + [-1, 0, -1, 0]
    datas += [struct.pack("<38i", *quad), bytes(unhook), bytes(grass), bytes(game)]

    def ints(*v):
        return struct.pack(f"<{len(v)}i", *v)

    items = [(0, 0, ints(1))]  # version
    items += [(2, 0, ints(1, 1024, 1024, 1, 0, -1)), (2, 1, ints(1, 1024, 1024, 1, 1, -1))]  # images
    items += [(4, 0, ints(3, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, *_name_ints("Sky"))),
              (4, 1, ints(3, 0, 0, 100, 100, 1, 3, 0, 0, 0, 0, 0, *_name_ints("Game")))]

    def tiles(img, data, flags, name):
        return ints(0, 2, 0, 3, w, h, flags, 255, 255, 255, 255, -1, 0, img, data,
                    *_name_ints(name), -1, -1, -1, -1, -1)

    items += [(5, 0, ints(0, 3, 0, 2, 1, 2, -1, *_name_ints("Sky"))),
              (5, 1, tiles(1, 3, 0, "Unhook")), (5, 2, tiles(0, 4, 0, "Grass")),
              (5, 3, tiles(-1, 5, 1, "Game"))]

    comp = [zlib.compress(d) for d in datas]
    types = sorted({t for t, _, _ in items})
    by_type = {t: [it for it in items if it[0] == t] for t in types}
    item_size = sum(len(p) + 8 for _, _, p in items)
    data_size = sum(len(c) for c in comp)
    swap = 36 + 12 * len(types) + 4 * (len(items) + 2 * len(datas)) + item_size
    out = b"DATA" + ints(4, swap + data_size - 16, swap - 16, len(types), len(items), len(datas),
                         item_size, data_size)
    start = 0
    for t in types:
        out += ints(t, start, len(by_type[t]))
        start += len(by_type[t])
    off = 0
    for t in types:
        for _, _, p in by_type[t]:
            out += ints(off)
            off += len(p) + 8
    off = 0
    for c in comp:
        out += ints(off)
        off += len(c)
    for d in datas:
        out += ints(len(d))
    for t in types:
        for _, i, p in by_type[t]:
            out += ints((t << 16) | i, len(p)) + p
    for c in comp:
        out += c
    Path(path).write_bytes(out)


def _layout(features, spawn_row=20, width=44, height=30):
    """A flat two-row floor under row `spawn_row`, main spawn at column 10 of that row, plus
    `features`: {(col, row): char}. The tee then stands with its centre 336 units from the map's
    left edge, so a wall whose left face is k tiles right of the spawn column is 32*k - 16 units
    in front of the tee's centre."""
    rows = [["."] * width for _ in range(height)]
    for c in range(2, width - 2):
        rows[spawn_row + 1][c] = "#"
        rows[spawn_row + 2][c] = "#"
    rows[spawn_row][10] = "S"
    for (c, r), ch in features.items():
        rows[r][c] = ch
    return ["".join(r) for r in rows]


def _wall(col, top, bottom, ch="#"):
    return {(col, r): ch for r in range(top, bottom + 1)}


LAYOUTS = {
    # open ground, nothing within hook reach in front of or above the tee
    "open": _layout({}),
    # hookable wall whose face is 336 units in front of the tee: the 5th hook step (282 -> 362)
    # reaches it, so the hook attaches
    "wall_in_reach": _layout(_wall(21, 14, 20)),
    # hookable wall whose face is 368 units away: inside hook_length (380), but the step that would
    # get there (362 -> 442) passes hook_length, so the hook gives up and never attaches
    "wall_past_reach": _layout(_wall(22, 14, 20)),
    # unhookable wall 240 units away: the hook bounces off it
    "unhookable_wall": _layout(_wall(18, 14, 20, "x")),
    # a second tee standing on the same floor, centre 192 units in front of the tee
    "tee_ahead": _layout({(16, 20): "D"}),
    # a one-tile hookable wall (face 208 units away) with the second tee standing right behind it
    # (centre 256 units away)
    "tee_behind_wall": _layout({**_wall(17, 17, 20), (18, 20): "D"}),
    # the second tee (centre 256 units away) standing right in front of a hookable wall (face 272
    # units away): both lie inside the same hook step (202 -> 282), the tee comes first
    "tee_before_wall": _layout({**_wall(19, 14, 20), (18, 20): "D"}),
}

# ---------------------------------------------------------------------------------------------
# Screen geometry at 1280x800 with the default zoom: the camera is centred on the local tee and
# shows about 1356.5 x 847.8 world units.
# ---------------------------------------------------------------------------------------------
W, H = 1280, 800
CX, CY = W // 2, H // 2
PX_PER_UNIT = W / (math.sqrt(1150 * 1000 * (W / H)))
HUD_BOXES = [(0, 0, 130, 130), (540, 0, 740, 50), (0, 600, 560, 800), (1100, 580, 1280, 800)]
TEE_RADIUS_PX = 46  # the tee itself (and its idle animation) is ignored


def _hsl_cfg_to_rgb(v):
    h, s, l = ((v >> 16) & 0xFF) / 255.0, ((v >> 8) & 0xFF) / 255.0, (v & 0xFF) / 255.0
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (round(r * 255), round(g * 255), round(b * 255))


# the client's default legend colours (Settings > Appearance > Hook collisions)
LEGEND = {
    "nothing": _hsl_cfg_to_rgb(65407),
    "hookable": _hsl_cfg_to_rgb(6401973),
    "tee": _hsl_cfg_to_rgb(2817919),
}
# a line may also be drawn in an inverted legend colour (e.g. while the "hook collisions" key is
# held, or for an outcome the client cannot predict); presence and reach accept those too
LINE_COLOURS = list(LEGEND.values()) + [tuple(255 - v for v in c) for c in LEGEND.values()]


def _near(c, ref, tol=70):
    return abs(c[0] - ref[0]) + abs(c[1] - ref[1]) + abs(c[2] - ref[2]) <= tol


def _line_coloured(c):
    return any(_near(c, ref) for ref in LINE_COLOURS)


def _builddir():
    d = os.environ.get("DDNET_BUILD_DIR")
    if d:
        return Path(d)
    for cand in (REPO_ROOT / "build", REPO_ROOT / "debug", REPO_ROOT / "release"):
        if (cand / "DDNet").exists() and (cand / "DDNet-Server").exists():
            return cand
    raise RuntimeError("could not find a DDNet/DDNet-Server build; set DDNET_BUILD_DIR")


def _wait_for(pred, timeout, what):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return
        time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {what}")


class Session:
    """One DDNet-Server + DDNet client (optionally with a dummy) on a generated map."""

    _next = 0

    def __init__(self, tmp_path, layout, tunes=(), client_cfg=(), dummy=False):
        Session._next += 1
        self.tmp = tmp_path
        self.layout = layout
        self.tunes = tunes
        self.client_cfg = client_cfg
        self.dummy = dummy
        self.port = 18310 + Session._next + (os.getpid() % 50) * 20
        self.display = 90 + (Session._next * 7 + os.getpid()) % 400
        while Path(f"/tmp/.X{self.display}-lock").exists():
            self.display += 1
        self.procs = []

    def __enter__(self):
        try:
            return self._start()
        except BaseException:
            self.__exit__()
            raise

    def _start(self):
        builddir = _builddir()
        home = Path(os.environ["HOME"])
        maps = home / ".local" / "share" / "ddnet" / "maps"
        maps.mkdir(parents=True, exist_ok=True)
        self.map_name = f"hookline_{self.layout}"
        write_map(maps / f"{self.map_name}.map", LAYOUTS[self.layout])
        self.shots_dir = home / ".local" / "share" / "ddnet" / "screenshots"

        self.env = dict(os.environ, DISPLAY=f":{self.display}", SDL_AUDIODRIVER="dummy",
                        LIBGL_ALWAYS_SOFTWARE="1")
        self.procs.append(subprocess.Popen(["Xvfb", f":{self.display}", "-screen", "0", f"{W}x{H}x24"],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(1.0)

        self.server_fifo = self.tmp / "server.fifo"
        self.client_fifo = self.tmp / "client.fifo"
        self.server_log = self.tmp / "server.log"
        with open(self.server_log, "w") as log:
            self.procs.append(subprocess.Popen(
                [str(builddir / "DDNet-Server"), "sv_rcon_password harvest", f"sv_map {self.map_name}",
                 f"sv_port {self.port}", "sv_register 0", "sv_motd \"\"",
                 f"sv_input_fifo {self.server_fifo.name}"],
                cwd=self.tmp, env=self.env, stdout=log, stderr=subprocess.STDOUT))
        _wait_for(self.server_fifo.exists, 20, "server console")
        time.sleep(1.0)
        for t in self.tunes:  # tunings stick once set live, after the world has initialised
            self.server(f"tune {t}")
        time.sleep(0.3)

        cfg = ["gfx_fullscreen 0", f"gfx_screen_width {W}", f"gfx_screen_height {H}",
               f"cl_input_fifo {self.client_fifo.name}", "cl_save_settings 0",
               "cl_show_hook_coll_own 0", "cl_show_hook_coll_other 0", "cl_mouse_max_distance 1000",
               "cl_nameplates 0",  # name tags are drawn over the scene and would hide parts of the line
               *self.client_cfg, f"connect 127.0.0.1:{self.port}"]
        self.procs.append(subprocess.Popen([str(builddir / "DDNet"), *cfg], cwd=self.tmp, env=self.env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        _wait_for(self.client_fifo.exists, 30, "client console")
        _wait_for(lambda: "ClientId=0" in self.server_log.read_text(errors="ignore"), 60, "player join")
        if self.dummy:
            time.sleep(1.0)
            self.client("dummy_connect")
            _wait_for(lambda: "ClientId=1" in self.server_log.read_text(errors="ignore"), 60, "dummy join")
            time.sleep(1.0)
            self.client("cl_dummy 0")  # connecting the dummy hands control to it; look as the player
        time.sleep(4.0)  # spawn, fall onto the floor, settle
        self._focus()
        return self

    def _focus(self):
        for _ in range(20):
            r = subprocess.run(["xdotool", "search", "--name", "DDNet"], env=self.env,
                               capture_output=True, text=True)
            ids = r.stdout.split()
            if ids:
                subprocess.run(["xdotool", "windowfocus", ids[0]], env=self.env, capture_output=True)
                return
            time.sleep(0.5)

    def server(self, line):
        with open(self.server_fifo, "w") as f:
            f.write(line + "\n")

    def client(self, line):
        with open(self.client_fifo, "w") as f:
            f.write(line + "\n")

    def aim(self, dx, dy):
        """Move the real mouse by (dx, dy) screen pixels (the client turns this into aim)."""
        self._focus()
        subprocess.run(["xdotool", "mousemove_relative", "--", str(dx), str(dy)], env=self.env,
                       check=True, capture_output=True)
        time.sleep(0.8)

    def screenshot(self, dest):
        before = set(self.shots_dir.glob("*.png")) if self.shots_dir.is_dir() else set()
        time.sleep(1.1)  # screenshot names have a one-second resolution
        self.client("screenshot")
        for _ in range(100):
            time.sleep(0.1)
            new = (set(self.shots_dir.glob("*.png")) if self.shots_dir.is_dir() else set()) - before
            if new:
                time.sleep(0.3)
                src = sorted(new)[-1]
                out = self.tmp / dest
                out.write_bytes(src.read_bytes())
                return out
        raise RuntimeError("no screenshot appeared")

    def line_off_on(self, extra=()):
        for c in extra:
            self.client(c)
        self.client("cl_show_hook_coll_own 0")
        time.sleep(0.5)
        off = self.screenshot("off.png")
        self.client("cl_show_hook_coll_own 2")
        time.sleep(0.5)
        on = self.screenshot("on.png")
        return Line(off, on)

    def __exit__(self, *exc):
        for p in reversed(self.procs):  # client, server, then Xvfb (which removes its lock file)
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


class Line:
    """The pixels that turning the line on changed, outside the HUD and the tee itself."""

    def __init__(self, off_png, on_png):
        a = Image.open(off_png).convert("RGB")
        b = Image.open(on_png).convert("RGB")
        pa, pb = a.load(), b.load()
        self.pixels = []
        for y in range(H):
            for x in range(W):
                if any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in HUD_BOXES):
                    continue
                if (x - CX) ** 2 + (y - CY) ** 2 < TEE_RADIUS_PX ** 2:
                    continue
                ca, cb = pa[x, y], pb[x, y]
                if abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2]) > 60:
                    self.pixels.append((x, y, cb))

    def along(self, ux, uy, band=12):
        """Changed pixels within `band` px of the ray from the tee centre along (ux, uy), as
        (distance along the ray in px, signed offset across it in px, colour)."""
        out = []
        for x, y, c in self.pixels:
            dx, dy = x - CX, y - CY
            t = dx * ux + dy * uy
            o = -dx * uy + dy * ux
            if t > 0 and abs(o) <= band:
                out.append((t, o, c))
        return out

    def reach_units(self, ux, uy):
        """How far the drawn line reaches from the tee centre, in world units (0 if absent).
        Only the contiguous part starting near the tee counts."""
        ts = sorted({int(t) for t, _, c in self.along(ux, uy) if _line_coloured(c)})
        if not ts or ts[0] > 120:  # the tee and the weapon it holds cover the line's first ~60 px
            return 0.0
        end = ts[0]
        for t in ts[1:]:
            if t - end > 14:
                break
            end = t
        return end / PX_PER_UNIT

    def legend_share(self, ux, uy):
        """{legend colour name: share} of the line's pixels that match a legend colour."""
        counts = {k: 0 for k in LEGEND}
        for _, _, c in self.along(ux, uy, band=8):
            best, dist = None, 1e9
            for k, ref in LEGEND.items():
                d = abs(c[0] - ref[0]) + abs(c[1] - ref[1]) + abs(c[2] - ref[2])
                if d < dist:
                    best, dist = k, d
            if dist <= 70:
                counts[best] += 1
        total = sum(counts.values())
        return {k: (v / total if total else 0.0) for k, v in counts.items()}, total

    def width_px(self, ux, uy, t0=90, t1=230):
        """Average thickness (px) of the line between t0 and t1 px from the tee centre."""
        seg = [p for p in self.along(ux, uy, band=20) if t0 <= p[0] < t1 and _line_coloured(p[2])]
        return len(seg) / float(t1 - t0)


@pytest.fixture
def home_isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


RIGHT = (1.0, 0.0)


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def _dominant(line, u):
    share, total = line.legend_share(*u)
    best = max(share, key=share.get)
    return best, share, total


def _twice(test):
    """Run a scenario a second time, from scratch, if the first attempt fails (a slow start-up or a
    one-off bad frame on a loaded machine). A wrong line is wrong on every attempt, so this only
    removes harness noise; the test fails when both attempts fail."""
    @functools.wraps(test)
    def run(tmp_path, home_isolated):
        errors = []
        for attempt in (1, 2):
            work = tmp_path / f"attempt{attempt}"
            work.mkdir()
            try:
                return test(work, home_isolated)
            except Exception as e:  # noqa: BLE001 - reported below
                errors.append(e)
        raise AssertionError(f"failed on both attempts; first: {errors[0]!r}") from errors[1]
    return run


# ------------------------------------------------------------------- the line is drawn at all


@_twice
def test_hook_coll_line_drawn_with_subunit_fire_speed(tmp_path, home_isolated):
    """A server tuned to a hook_fire_speed below 1 (0.9) still gets a guide line along the aim."""
    with Session(tmp_path, "open", tunes=["hook_fire_speed 0.9"]) as s:
        line = s.line_off_on()
    reach = line.reach_units(*RIGHT)
    assert reach >= 150, f"expected a guide line along the aim with hook_fire_speed 0.9, got {reach:.0f} units"


@_twice
def test_hook_coll_line_drawn_with_normal_fire_speed(tmp_path, home_isolated):
    """With the default tuning the guide line is drawn along the aim, in the 'nothing hookable'
    colour, and reaches about as far as the hook can go (over open ground)."""
    with Session(tmp_path, "open") as s:
        line = s.line_off_on()
    reach = line.reach_units(*RIGHT)
    best, share, total = _dominant(line, RIGHT)
    assert 330 <= reach <= 395, f"line over open ground reaches {reach:.0f} units, expected ~362-380"
    assert best == "nothing" and share["nothing"] >= 0.8, (best, share, total)


# ------------------------------------------------------------------- walls


@_twice
def test_hook_coll_line_hookable_wall_within_reach(tmp_path, home_isolated):
    """A hookable wall the hook does reach: 'something hookable' colour, ending at the wall."""
    with Session(tmp_path, "wall_in_reach") as s:
        line = s.line_off_on()
    best, share, total = _dominant(line, RIGHT)
    reach = line.reach_units(*RIGHT)
    assert best == "hookable" and share["hookable"] >= 0.8, (best, share, total)
    assert 310 <= reach <= 350, f"line should end at the wall 336 units away, ends at {reach:.0f}"


@_twice
def test_hook_coll_line_wall_past_hook_reach_is_not_hookable(tmp_path, home_isolated):
    """A hookable wall 368 units away is closer than hook_length (380), but the hook gives up on
    the step that would reach it and never attaches: the line must not promise a hookable hit."""
    with Session(tmp_path, "wall_past_reach") as s:
        line = s.line_off_on()
    best, share, total = _dominant(line, RIGHT)
    assert total >= 100, f"no guide line drawn ({total} legend-coloured pixels)"
    assert share["hookable"] < 0.2 and best == "nothing", (
        f"line previews a hookable hit on a wall the hook cannot reach: {share}")


@_twice
def test_hook_coll_line_unhookable_wall(tmp_path, home_isolated):
    """An unhookable wall: 'nothing hookable' colour, ending at the wall (240 units away)."""
    with Session(tmp_path, "unhookable_wall") as s:
        line = s.line_off_on()
    best, share, total = _dominant(line, RIGHT)
    reach = line.reach_units(*RIGHT)
    assert best == "nothing" and share["nothing"] >= 0.8, (best, share, total)
    assert 215 <= reach <= 255, f"line should end at the unhookable wall 240 units away, ends at {reach:.0f}"


# ------------------------------------------------------------------- other tees


@_twice
def test_hook_coll_line_tee_straight_ahead(tmp_path, home_isolated):
    """A tee standing straight ahead: 'a tee' colour, ending at that tee (192 units away)."""
    with Session(tmp_path, "tee_ahead", dummy=True) as s:
        line = s.line_off_on()
    best, share, total = _dominant(line, RIGHT)
    reach = line.reach_units(*RIGHT)
    assert best == "tee" and share["tee"] >= 0.8, (best, share, total)
    assert 160 <= reach <= 225, f"line should end at the tee 192 units away, ends at {reach:.0f}"


@_twice
def test_hook_coll_line_tee_grazed_by_hook_path(tmp_path, home_isolated):
    """Aim slightly above a tee 192 units away so the hook path passes ~24 units from its centre:
    the real hook grabs that tee, so the line must use the 'a tee' colour and end at it."""
    dx, dy = 199, -25  # mouse pixels; the client turns them into the aim target (399, -50)
    u = _unit(399, -50)
    with Session(tmp_path, "tee_ahead", dummy=True) as s:
        s.aim(dx, dy)
        line = s.line_off_on()
    best, share, total = _dominant(line, u)
    reach = line.reach_units(*u)
    assert best == "tee" and share["tee"] >= 0.8, (
        f"hook path grazes a tee (it would grab it) but the line says {best}: {share}")
    assert reach <= 230, f"line should stop at the grazed tee (~190 units), reaches {reach:.0f}"


@_twice
def test_hook_coll_line_tee_clearly_missed(tmp_path, home_isolated):
    """Aim well above a tee so the hook path passes ~60 units from its centre: no tee colour."""
    u = _unit(399, -130)
    with Session(tmp_path, "tee_ahead", dummy=True) as s:
        s.aim(199, -65)
        line = s.line_off_on()
    best, share, total = _dominant(line, u)
    reach = line.reach_units(*u)
    assert best == "nothing" and share["tee"] < 0.2, (best, share, total)
    assert reach >= 330, f"line should run on past a missed tee, reaches {reach:.0f}"


@_twice
def test_hook_coll_line_stops_at_wall_in_front_of_tee(tmp_path, home_isolated):
    """A tee right behind a thin hookable wall: the hook attaches to the wall, so the line must use
    the 'something hookable' colour and end at the wall (208 units away), not at the tee."""
    with Session(tmp_path, "tee_behind_wall", dummy=True) as s:
        line = s.line_off_on()
    best, share, total = _dominant(line, RIGHT)
    reach = line.reach_units(*RIGHT)
    assert best == "hookable" and share["tee"] < 0.2, (best, share, total)
    assert reach <= 222, f"line should end at the wall 208 units away, ends at {reach:.0f}"


@_twice
def test_hook_coll_line_tee_in_front_of_wall(tmp_path, home_isolated):
    """A tee standing right in front of a hookable wall, both reached in the same hook step: the hook
    grabs the tee first, so the line uses the 'a tee' colour and ends at the tee (256 units away),
    not at the wall behind it (272 units away)."""
    with Session(tmp_path, "tee_before_wall", dummy=True) as s:
        line = s.line_off_on()
    best, share, total = _dominant(line, RIGHT)
    reach = line.reach_units(*RIGHT)
    assert best == "tee" and share["tee"] >= 0.8, (best, share, total)
    assert 225 <= reach <= 268, f"line should end at the tee 256 units away, ends at {reach:.0f}"


# ------------------------------------------------------------------- line width setting


@_twice
def test_hook_coll_line_width_setting_straight_aim(tmp_path, home_isolated):
    """With the width setting at its maximum (20) the line is drawn about 10 px wide."""
    with Session(tmp_path, "open", client_cfg=["cl_hook_coll_size 20"]) as s:
        line = s.line_off_on()
    width = line.width_px(*RIGHT)
    assert 7.0 <= width <= 14.0, f"wide line drawn {width:.1f} px wide when aiming straight"


@_twice
def test_hook_coll_line_width_setting_diagonal_aim(tmp_path, home_isolated):
    """The same wide line keeps its width when the aim is diagonal (up and to the right)."""
    u = _unit(283, -282)
    with Session(tmp_path, "open", client_cfg=["cl_hook_coll_size 20"]) as s:
        s.aim(141, -141)
        line = s.line_off_on()
    width = line.width_px(*u)
    reach = line.reach_units(*u)
    assert 7.0 <= width <= 14.0, f"wide line drawn {width:.1f} px wide when aiming diagonally"
    assert reach >= 330, f"diagonal line reaches {reach:.0f} units"
