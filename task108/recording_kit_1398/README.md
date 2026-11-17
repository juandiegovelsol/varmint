# task108 (supertux 1398) hardening kit - scratch, not part of the bundle

- `mkbugs.py <repo> <outdir> [NN]` - applies the 5 injected defects in order and exports bug_NN.patch (NN alone: apply just that one).
- `altfix.py <repo>` - independent alternative fix applied on the buggy tree (passes 10/10).
- `matrix.sh` - each bug alone on base+original fix -> which RockBehaviour tests fail. `run2.sh` = build + run tests (installed as /usr/local/bin/rbrun in the dev container).
- Reshoot (dev container from the task image + gdb/xdotool/bc, buggy tree, `cmake --build /build --target supertux2`):
  `python3 mklevel.py /rec/lf.stl 860 860 objs2.txt s4.nut && bash record.sh /rec/lf.stl raw.mp4 32`,
  then `ffmpeg -ss 2.5 -t 26 ... recording.mp4`. Takes vary run to run (leaf hit); check frames with mosaic.sh and keep a take where the leaf freezes.
- Nothing is shown on a real display: Xvfb :99 inside the container only.
