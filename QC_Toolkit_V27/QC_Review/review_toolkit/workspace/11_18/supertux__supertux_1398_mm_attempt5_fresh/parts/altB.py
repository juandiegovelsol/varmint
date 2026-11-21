"""Independent alternative fix (ALT-B) written differently from the golden, applied inside the task image."""
def sub(path, old, new):
    s = open(path).read()
    assert s.count(old) == 1, (path, old[:70])
    open(path, "w").write(s.replace(old, new))

# defect 0: early return for touchable objects, in the style of the existing HeavyCoin/Explosion early returns
sub("/app/src/object/rock.cpp",
"""  auto explosion = dynamic_cast<Explosion*> (&other);
  if (explosion) {
    return ABORT_MOVE;
  }
""",
"""  auto explosion = dynamic_cast<Explosion*> (&other);
  if (explosion) {
    return ABORT_MOVE;
  }

  // Coins and other touchable objects are nothing a rock can land on.
  auto touchable = dynamic_cast<MovingObject*> (&other);
  if (touchable && touchable->get_group() == COLGROUP_TOUCHABLE) {
    return ABORT_MOVE;
  }
""")
# defect 1: flip the ternary instead of an if
sub("/app/src/object/player.cpp",
"pos.x -= object_bbox.get_width() * (m_dir == Direction::LEFT ? 0.0f : 1.0f);",
"pos.x -= object_bbox.get_width() * (m_dir == Direction::LEFT ? 1.0f : 0.0f);")
# defect 2: flip the comparison instead of passing m_dir
sub("/app/src/object/player.cpp",
"(dest_.get_left() > m_col.m_bbox.get_left()) ?",
"(dest_.get_left() < m_col.m_bbox.get_left()) ?")
# defect 3: make every release solid again, keep the (harmless) landing line
sub("/app/src/object/rock.cpp",
"""  if (physic.get_velocity_x() == 0.0f)
    set_group(COLGROUP_MOVING_STATIC);
""",
"""  set_group(COLGROUP_MOVING_STATIC);
""")
# defect 4: keep the override, but only skip an object that is being carried
sub("/app/src/object/player.cpp",
"""  if (portable && portable->is_portable() && !portable->is_grabbed())
    return false;""",
"""  if (portable && portable->is_grabbed())
    return false;""")
# defect 5: compound condition instead of a nested if
sub("/app/src/badguy/badguy.cpp",
"""    else if (is_freezable()) {
      freeze();
    }""",
"""    else if ((tile_attributes & Tile::ICE) && is_freezable()) {
      freeze();
    }""")
print("altB applied")
