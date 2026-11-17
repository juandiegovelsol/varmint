"""Apply the five injected defects one by one to a clean checkout and export
bug_NN.patch files (each relative to the previous step).

usage: python mkbugs.py <repo> <outdir> [only]   (only = e.g. 03 to apply just that edit and stop)
"""
import os
import subprocess
import sys

REPO, OUT = sys.argv[1], sys.argv[2]
ONLY = sys.argv[3] if len(sys.argv) > 3 else None


def edit(path, old, new, count=1):
    p = os.path.join(REPO, path)
    s = open(p, newline="").read()
    assert s.count(old) == count, (path, old[:60], s.count(old))
    s = s.replace(old, new)
    open(p, "w", newline="").write(s)


def bug01():  # carried rock held behind Tux
    edit("src/object/player.cpp",
         "  if (m_dir == Direction::LEFT)\n    pos.x -= object_bbox.get_width();\n  pos.y -= object_bbox.get_height();\n",
         "  pos.x -= object_bbox.get_width() * (m_dir == Direction::LEFT ? 0.0f : 1.0f);\n  pos.y -= object_bbox.get_height();\n")


def bug02():  # rock thrown while walking flies backwards (direction from the drop spot, inverted)
    edit("src/object/player.cpp",
         "        } else {\n          m_grabbed_object->ungrab(*this, m_dir);\n        }\n        m_grabbed_object = nullptr;\n",
         "        } else {\n"
         "          // throw it away from Tux, towards the side it was put down on\n"
         "          m_grabbed_object->ungrab(*this, (dest_.get_left() > m_col.m_bbox.get_left()) ?\n"
         "                                   Direction::LEFT : Direction::RIGHT);\n"
         "        }\n        m_grabbed_object = nullptr;\n")


def bug03():  # rock thrown while walking stays touchable -> falls through the ground
    edit("src/object/rock.cpp",
         "Rock::ungrab(MovingObject& object, Direction dir)\n{\n  set_group(COLGROUP_MOVING_STATIC);\n  on_ground = false;\n",
         "Rock::ungrab(MovingObject& object, Direction dir)\n{\n  on_ground = false;\n")
    edit("src/object/rock.cpp",
         "  } else {\n    physic.set_velocity(0, 0);\n  }\n\n  if (!on_ungrab_script.empty()) {",
         "  } else {\n    physic.set_velocity(0, 0);\n  }\n\n"
         "  // A lantern that is thrown forward has to keep catching willowisps on its\n"
         "  // way; it becomes solid again when it lands (see collision_solid()).\n"
         "  if (physic.get_velocity_x() == 0.0f)\n    set_group(COLGROUP_MOVING_STATIC);\n\n"
         "  if (!on_ungrab_script.empty()) {")
    edit("src/object/rock.cpp",
         "    physic.set_velocity_x(0);\n    on_ground = true;\n",
         "    physic.set_velocity_x(0);\n    set_group(COLGROUP_MOVING_STATIC);\n    on_ground = true;\n")


def bug04():  # Tux never collides with a portable object lying around
    edit("src/object/player.hpp",
         "  virtual void collision_solid(const CollisionHit& hit) override;\n",
         "  virtual void collision_solid(const CollisionHit& hit) override;\n"
         "  virtual bool collides(GameObject& other, const CollisionHit& hit) const override;\n")
    edit("src/object/player.cpp",
         "HitResponse\nPlayer::collision(GameObject& other, const CollisionHit& hit)\n{\n",
         "bool\nPlayer::collides(GameObject& other, const CollisionHit& hit) const\n{\n"
         "  // Tux walks right up to things he can carry and picks them up (see\n"
         "  // try_grab()), so he does not bump into a portable object lying around.\n"
         "  auto portable = dynamic_cast<Portable*>(&other);\n"
         "  if (portable && portable->is_portable() && !portable->is_grabbed())\n"
         "    return false;\n\n"
         "  return MovingObject::collides(other, hit);\n}\n\n"
         "HitResponse\nPlayer::collision(GameObject& other, const CollisionHit& hit)\n{\n")


def bug05():  # hurt + freezable badguy is frozen instead of knocked out
    edit("src/badguy/badguy.cpp",
         "    else if (tile_attributes & Tile::ICE) {\n      if (is_freezable()) freeze();\n    }\n",
         "    else if (is_freezable()) {\n      freeze();\n    }\n")


BUGS = [("01", bug01), ("02", bug02), ("03", bug03), ("04", bug04), ("05", bug05)]


def git(*args, **kw):
    return subprocess.run(["git", "-C", REPO] + list(args), check=True, capture_output=True, **kw).stdout


if ONLY:
    dict(BUGS)[ONLY]()
    sys.exit(0)

os.makedirs(OUT, exist_ok=True)
for n, fn in BUGS:
    fn()
    diff = git("diff")
    open(os.path.join(OUT, "bug_%s.patch" % n), "wb").write(diff)
    git("add", "-A")
    git("-c", "user.email=h@l", "-c", "user.name=h", "commit", "-q", "-m", "bug " + n)
    print("bug_%s.patch: %d bytes" % (n, len(diff)))
