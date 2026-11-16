#!/usr/bin/env python3
"""Apply NON-oracle fixes (or deliberately wrong ones) on top of the buggy tree in /app.

usage: altfix.py alt|wrong
  alt   : a different, behaviourally correct fix for every defect
  wrong : plausible but wrong "compensating" fixes for the mirror and direction defects
          (on top of the alt fixes for the other three)
"""
import sys

CAO = "/app/src/client/content_cao.cpp"


def edit(path, old, new):
    s = open(path, encoding="utf-8", newline="").read()
    assert s.count(old) == 1, (path, old[:60], s.count(old))
    open(path, "w", encoding="utf-8", newline="").write(s.replace(old, new))


# 1. frozen upright sprite: keep its mesh out of hardware buffers instead of marking it dirty
B1 = ("""		if (m_meshnode)
			m_meshnode->getMesh()->setHardwareMappingHint(scene::EHM_STATIC);
""", """		if (m_meshnode)
			m_meshnode->getMesh()->setHardwareMappingHint(
				m_prop.visual == "upright_sprite" ? scene::EHM_NEVER : scene::EHM_STATIC);
""")
# 2. mirrored back face: give the back buffer its own texture-coordinate order
B2 = ("""			setMeshBufferTextureCoords(mesh->getMeshBuffer(1), t, 4);
""", """			const v2f tb[4] = {t[1], t[0], t[3], t[2]};
			setMeshBufferTextureCoords(mesh->getMeshBuffer(1), tb, 4);
""")
# 3. mirrored camera-facing sprite: flip U in the texture matrix instead of fixing the billboard
B3 = ("""	matrix.setTextureTranslate(txs*col, tys*row);
	matrix.setTextureScale(txs, tys);
""", """	matrix.setTextureTranslate(txs*(col+1), tys*row);
	matrix.setTextureScale(-txs, tys);
""")
# 4. select_x_by_camera: signed angle between the subject's facing vector and the view vector
B4 = ("""				float dir = mob_dir + m_rotation.Y;
""", """				(void)mob_dir;
				const float yaw = m_rotation.Y * core::DEGTORAD;
				const float fx = std::cos(yaw), fz = std::sin(yaw);
				float dir = std::atan2(fx * cam_to_entity.Z - fz * cam_to_entity.X,
						fx * cam_to_entity.X + fz * cam_to_entity.Z) * core::RADTODEG;
""")
# 5. attached sprites frozen: advance the frame timer for every object, after the movement code
B5 = ("""		m_anim_timer += dtime;
		if(m_anim_timer >= m_anim_framelength)
		{
			m_anim_timer -= m_anim_framelength;
			m_anim_frame++;
			if(m_anim_frame >= m_anim_num_frames)
				m_anim_frame = 0;
		}
	}

	updateTexturePos();
""", """	}

	if (m_anim_framelength > 0) {
		m_anim_timer += dtime;
		while (m_anim_timer >= m_anim_framelength) {
			m_anim_timer -= m_anim_framelength;
			m_anim_frame = (m_anim_frame + 1) % std::max(m_anim_num_frames, 1);
		}
	}

	updateTexturePos();
""")
# wrong 3: "fix" the mirrored profiles by swapping the left/right columns of select_x
W3 = ("""				else if(std::fabs(wrapDegrees_180(dir - 90)) <= 45.1f)
					col += 3;
""", """				else if(std::fabs(wrapDegrees_180(dir - 90)) <= 45.1f)
					col += 1;
""", """				else if(std::fabs(wrapDegrees_180(dir + 90)) <= 45.1f)
					col += 1;
""", """				else if(std::fabs(wrapDegrees_180(dir + 90)) <= 45.1f)
					col += 3;
""")
# wrong 4: "fix" the front/back swap by swapping the front/back columns, keeping the sign
W4 = ("""				if (std::fabs(wrapDegrees_180(dir - 0)) <= 45.1f)
					col += 2;
""", """				if (std::fabs(wrapDegrees_180(dir - 0)) <= 45.1f)
					col += 0;
""", """				else if(std::fabs(wrapDegrees_180(dir - 180)) <= 45.1f)
					col += 0;
""", """				else if(std::fabs(wrapDegrees_180(dir - 180)) <= 45.1f)
					col += 2;
""")

# wrong 5: frame timer added after the movement code, but the copy in the
# "not attached" branch is left in place, so unattached sprites run at double speed
W5 = ("""	updateTexturePos();

	if(m_reset_textures_timer >= 0)
""", """	m_anim_timer += dtime;
	if(m_anim_timer >= m_anim_framelength)
	{
		m_anim_timer -= m_anim_framelength;
		m_anim_frame++;
		if(m_anim_frame >= m_anim_num_frames)
			m_anim_frame = 0;
	}

	updateTexturePos();

	if(m_reset_textures_timer >= 0)
""")
# wrong 2: billboard corner UVs "fixed" by flipping V as well, so sprites are upside down
W2 = ("""	Vertices[0].TCoords.set(0.0f, 1.0f);
	Vertices[0].Color = colorBottom;

	Vertices[1].TCoords.set(0.0f, 0.0f);
	Vertices[1].Color = colorTop;

	Vertices[2].TCoords.set(1.0f, 0.0f);
	Vertices[2].Color = colorTop;

	Vertices[3].TCoords.set(1.0f, 1.0f);
""", """	Vertices[0].TCoords.set(1.0f, 0.0f);
	Vertices[0].Color = colorBottom;

	Vertices[1].TCoords.set(1.0f, 1.0f);
	Vertices[1].Color = colorTop;

	Vertices[2].TCoords.set(0.0f, 1.0f);
	Vertices[2].Color = colorTop;

	Vertices[3].TCoords.set(0.0f, 0.0f);
""")
BB = "/app/irr/src/CBillboardSceneNode.cpp"

mode = sys.argv[1]
if mode == "wrong_speed":
    edit(CAO, *B1); edit(CAO, *B2); edit(CAO, *B3); edit(CAO, *B4); edit(CAO, *W5)
elif mode == "wrong_flip":
    edit(CAO, *B1); edit(CAO, *B2); edit(CAO, *B4); edit(CAO, *B5); edit(BB, *W2)
else:
    for old, new in (B1, B2, B5):
        edit(CAO, old, new)
if mode == "alt":
    for old, new in (B3, B4):
        edit(CAO, old, new)
elif mode == "wrong":
    edit(CAO, W3[0], W3[1])
    edit(CAO, W3[2], W3[3])
    edit(CAO, W4[0], W4[1])
    edit(CAO, W4[2], W4[3])
print("applied", mode)
