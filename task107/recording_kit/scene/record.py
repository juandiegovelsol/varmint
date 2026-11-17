#!/usr/bin/env python3
"""Drive the yard scene (scene/start.sh must have run) and record it with ffmpeg x11grab.

usage: record.py OUT.mp4
Everything happens inside the container's Xvfb (:77); nothing opens on the host.
Shot list (approximate video time):
  0-4   Settings > Appearance > Hook Collisions (always show own line, width 20, legend, preview)
  4-15  spawn: line along the aim, aim swept from right over the top to the left (unhookable
        block on the left); hook fired at the unhookable block, bounces off
  15-27 teleport in front of the tall grass pillar 12 tiles away: line says hookable, hook fired,
        falls short; one tile closer: line says hookable, hook attaches and pulls the player
  27-35 respawn, teleport left of a one-tile block with the second player right behind it: line
        reaches the second player through the block; hook fired, attaches to the block
  35-45 respawn, teleport right of the second player: aim straight at them (tee colour), aim a
        little higher (line passes over their head); hook fired, grabs them
  45-   remote console: "tune hook_fire_speed 0.9"; respawn; aim swept around; hook fired (slow)
"""
import math
import subprocess
import sys
import time

ENV = {"DISPLAY": ":77", "HOME": "/tmp/r/home", "PATH": "/usr/bin:/bin:/usr/local/bin"}
CF, SF = "/tmp/r/client.fifo", "/tmp/r/server.fifo"


def cf(line):
    with open(CF, "w") as f:
        f.write(line + "\n")


def xdo(*args):
    subprocess.run(["xdotool", *[str(a) for a in args]], env=ENV, check=True)


class Aim:
    """Tracks the client's aim target (world units; 1 mouse pixel = 2 units at inp_mousesens 200)."""

    def __init__(self):
        self.m = [1.0, 0.0]

    def to(self, x, y):
        dx = int(round((x - self.m[0]) / 2.0))
        dy = int(round((y - self.m[1]) / 2.0))
        if dx or dy:
            xdo("mousemove_relative", "--", dx, dy)
        self.m[0] += 2 * dx
        self.m[1] += 2 * dy

    def sweep(self, a0, a1, seconds, r=400.0):
        steps = max(2, int(seconds * 30))
        for i in range(1, steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            self.to(r * math.cos(a), r * math.sin(a))
            time.sleep(seconds / steps)


T0 = [None]
MARKS = []


def mark(what):
    if T0[0] is not None:
        MARKS.append((time.time() - T0[0], what))


def hook(hold):
    xdo("mousedown", 3)
    time.sleep(hold)
    xdo("mouseup", 3)


def click():
    xdo("mousedown", 1)
    time.sleep(0.12)
    xdo("mouseup", 1)


def main(out):
    win = subprocess.run(["xdotool", "search", "--name", "DDNet"], env=ENV, capture_output=True,
                         text=True).stdout.split()[0]
    xdo("windowfocus", win)
    aim = Aim()

    # pre-roll (not recorded yet): open Settings > Appearance > Hook Collisions
    xdo("key", "Escape")
    time.sleep(1.0)
    xdo("mousemove_relative", "--", -3000, -3000)
    time.sleep(0.2)
    xdo("mousemove_relative", "--", 594, 15)   # settings gear
    time.sleep(0.3)
    click()
    time.sleep(1.0)
    xdo("mousemove_relative", "--", 0, 153)    # Appearance
    time.sleep(0.3)
    click()
    time.sleep(1.0)
    xdo("mousemove_relative", "--", -271, -126)  # Hook Collisions
    time.sleep(0.3)
    click()
    time.sleep(0.5)
    xdo("mousemove_relative", "--", 3000, 3000)  # park the menu cursor in the corner
    time.sleep(1.0)

    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab", "-draw_mouse", "0",
                           "-framerate", "30", "-video_size", "1280x800", "-i", ":77",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                           "/tmp/r/raw.mp4"], env=ENV, stdin=subprocess.PIPE)
    T0[0] = time.time()
    mark("recording starts, settings page")
    time.sleep(4.0)                     # settings page on screen
    xdo("key", "Escape")                # back to the game
    time.sleep(0.6)

    # --- spawn (column 10): open sky, unhookable block on the left
    mark("game: spawn, aim right")
    aim.to(400, 0)
    time.sleep(1.6)
    mark("sweep right->up")
    aim.sweep(0, -90, 2.6)              # right -> straight up
    time.sleep(0.8)
    mark("sweep up->left")
    aim.sweep(-90, -180, 2.6)           # straight up -> left (onto the unhookable block)
    time.sleep(1.4)
    mark("hook at unhookable block")
    hook(0.5)                           # bounces off the unhookable block
    time.sleep(1.4)

    # --- tall grass pillar: 12 tiles away (face 368 units), then 11 tiles away (336 units)
    mark("teleport: pillar 368")
    cf("rcon move 18 0")
    time.sleep(0.4)
    aim.to(400, 0)
    time.sleep(2.0)
    mark("pillar 368: first hook")
    hook(0.6)                           # flies, falls just short, comes back
    time.sleep(1.4)
    mark("pillar 368: second hook")
    hook(0.6)
    time.sleep(1.6)
    mark("nudge: pillar 336")
    cf("rcon move 1 0")
    time.sleep(1.6)
    mark("pillar 336: hook attaches")
    hook(0.9)                           # attaches, pulls the player to the pillar
    time.sleep(1.5)

    # --- one-tile block with the second player right behind it
    cf("kill")
    time.sleep(1.6)
    mark("teleport: block with buddy behind")
    cf("rcon move 57 0")                # column 67: block face 208 units away, buddy 256 away
    time.sleep(0.4)
    aim.to(400, 0)
    time.sleep(2.6)
    mark("hook at block (buddy behind)")
    hook(0.7)                           # attaches to the block
    time.sleep(1.5)

    # --- right of the second player (column 81, 192 units away), aiming left
    cf("kill")
    time.sleep(1.6)
    mark("teleport: right of buddy")
    cf("rcon move 71 0")
    time.sleep(0.4)
    aim.to(-400, 0)                     # straight at buddy
    time.sleep(2.2)
    mark("aim a little higher over buddy")
    aim.sweep(180, 187.1, 1.0, r=403)   # a little higher: the path passes ~24 units over buddy's centre
    time.sleep(2.2)
    mark("hook grabs buddy")
    hook(0.7)                           # grabs buddy
    time.sleep(1.8)

    # --- slower hook tuning, typed into the remote console
    mark("remote console opens")
    cf("toggle_remote_console")
    time.sleep(1.0)
    xdo("type", "--delay", "70", "tune hook_fire_speed 0.9")
    time.sleep(0.6)
    xdo("key", "Return")
    mark("tune command sent")
    time.sleep(1.8)
    cf("toggle_remote_console")
    time.sleep(0.8)
    cf("kill")
    time.sleep(1.6)
    aim.to(400, 0)
    time.sleep(1.4)
    mark("slow tuning: respawned, sweep")
    aim.sweep(0, -90, 1.8)
    aim.sweep(-90, -10, 1.8)
    time.sleep(0.6)
    mark("slow hook fired")
    hook(3.0)                           # the hook creeps out
    time.sleep(1.0)

    mark("end")
    ff.communicate(b"q")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "/tmp/r/raw.mp4", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    "-an", out], check=True)
    print("wrote", out)
    for t, w in MARKS:
        print(f"{t:6.2f}  {w}")


if __name__ == "__main__":
    main(sys.argv[1])
