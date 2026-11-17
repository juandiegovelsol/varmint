"""Alternative fix, written differently from the oracle, applied on top of the buggy tree."""
import sys

REPO = sys.argv[1]


def edit(path, old, new):
    p = REPO + "/" + path
    s = open(p).read()
    assert s.count(old) == 1, (path, old[:70])
    open(p, "w").write(s.replace(old, new))


# coins (any touchable) are ignored by a flying rock: bail out early instead of the group check
edit("src/object/rock.cpp",
     "  if (is_grabbed()) {\n    return ABORT_MOVE;\n  }\n",
     "  if (is_grabbed()) {\n    return ABORT_MOVE;\n  }\n\n"
     "  if (auto mo = dynamic_cast<MovingObject*>(&other)) {\n"
     "    if (mo->get_group() == COLGROUP_TOUCHABLE)\n      return FORCE_MOVE;\n  }\n")

# hold the rock against Tux's front edge, slightly overlapping him
edit("src/object/player.cpp",
     "  pos.x -= object_bbox.get_width() * (m_dir == Direction::LEFT ? 0.0f : 1.0f);\n",
     "  if (m_dir == Direction::RIGHT)\n    pos.x = m_col.m_bbox.get_right() - 6.0f;\n"
     "  else\n    pos.x = m_col.m_bbox.get_left() + 6.0f - object_bbox.get_width();\n")

# throw towards the side the rock was put down on (correct sign), slower and flatter
edit("src/object/player.cpp",
     "(dest_.get_left() > m_col.m_bbox.get_left()) ?\n                                   Direction::LEFT : Direction::RIGHT);\n",
     "(dest_.get_left() > m_col.m_bbox.get_left()) ?\n                                   Direction::RIGHT : Direction::LEFT);\n")
edit("src/object/rock.cpp",
     "    physic.set_velocity((dir == Direction::RIGHT) ? 200.0f : -200.0f, -200.0f);\n",
     "    physic.set_velocity((dir == Direction::LEFT) ? -110.0f : 110.0f, -180.0f);\n")

# always solid once released (keep the landing line, it is harmless)
edit("src/object/rock.cpp",
     "  if (physic.get_velocity_x() == 0.0f)\n    set_group(COLGROUP_MOVING_STATIC);\n",
     "  set_group(COLGROUP_MOVING_STATIC);\n")

# keep the override, but only skip the object Tux is carrying himself
edit("src/object/player.cpp",
     "  if (portable && portable->is_portable() && !portable->is_grabbed())\n    return false;\n",
     "  if (portable && portable == m_grabbed_object)\n    return false;\n")

# only icy hazards freeze; anything else that hurts knocks the badguy out
edit("src/badguy/badguy.cpp",
     "    else if (is_freezable()) {\n      freeze();\n    }\n",
     "    else if ((tile_attributes & Tile::ICE) && is_freezable()) {\n      freeze();\n    }\n"
     "    else if (tile_attributes & Tile::ICE) {\n      // not freezable: icy hazards leave it alone\n    }\n")
