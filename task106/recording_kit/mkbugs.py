#!/usr/bin/env python3
"""Inject the hardening bugs into /app one at a time and write one patch per bug.

usage: mkbugs.py OUTDIR      (run inside the dev container; /app must be a clean git tree)
"""
import subprocess
import sys
from pathlib import Path

import os
APP = Path(os.environ.get("APP", "/app"))

BUGS = {
    # 1. camera-facing sprites: texture mirrored left/right (Irrlicht billboard corner UVs)
    "bug_01": [(
        "irr/src/CBillboardSceneNode.cpp",
        """	Vertices[0].TCoords.set(1.0f, 1.0f);
	Vertices[0].Color = colorBottom;

	Vertices[1].TCoords.set(1.0f, 0.0f);
	Vertices[1].Color = colorTop;

	Vertices[2].TCoords.set(0.0f, 0.0f);
	Vertices[2].Color = colorTop;

	Vertices[3].TCoords.set(0.0f, 1.0f);
	Vertices[3].Color = colorBottom;
""",
        """	Vertices[0].TCoords.set(0.0f, 1.0f);
	Vertices[0].Color = colorBottom;

	Vertices[1].TCoords.set(0.0f, 0.0f);
	Vertices[1].Color = colorTop;

	Vertices[2].TCoords.set(1.0f, 0.0f);
	Vertices[2].Color = colorTop;

	Vertices[3].TCoords.set(1.0f, 1.0f);
	Vertices[3].Color = colorBottom;
""",
    )],
    # 2. upright_sprite: the back quad reuses the front quad's corners with reversed winding,
    #    so the back face shows its texture mirrored
    "bug_02": [(
        "src/client/content_cao.cpp",
        """		{ // Back
			scene::IMeshBuffer *buf = new scene::SMeshBuffer();
			video::S3DVertex vertices[4] = {
				video::S3DVertex( dx,-dy, 0, 0,0,-1, c, 1,1),
				video::S3DVertex(-dx,-dy, 0, 0,0,-1, c, 0,1),
				video::S3DVertex(-dx, dy, 0, 0,0,-1, c, 0,0),
				video::S3DVertex( dx, dy, 0, 0,0,-1, c, 1,0),
			};
			if (m_is_player) {
				// Move minimal Y position to 0 (feet position)
				for (video::S3DVertex &vertex : vertices)
					vertex.Pos.Y += dy;
			}
			u16 indices[] = {0,1,2,2,3,0};
""",
        """		{ // Back
			scene::IMeshBuffer *buf = new scene::SMeshBuffer();
			video::S3DVertex vertices[4] = {
				video::S3DVertex(-dx,-dy, 0, 0,0,-1, c, 1,1),
				video::S3DVertex( dx,-dy, 0, 0,0,-1, c, 0,1),
				video::S3DVertex( dx, dy, 0, 0,0,-1, c, 0,0),
				video::S3DVertex(-dx, dy, 0, 0,0,-1, c, 1,0),
			};
			if (m_is_player) {
				// Move minimal Y position to 0 (feet position)
				for (video::S3DVertex &vertex : vertices)
					vertex.Pos.Y += dy;
			}
			u16 indices[] = {0,3,2,2,1,0};
""",
    )],
    # 3. select_x_by_camera: entity yaw added instead of subtracted
    "bug_03": [(
        "src/client/content_cao.cpp",
        """				float dir = mob_dir - m_rotation.Y;
""",
        """				float dir = mob_dir + m_rotation.Y;
""",
    )],
    # 4. sprite frame timer only advances for objects that are not attached
    "bug_04": [(
        "src/client/content_cao.cpp",
        """				// The footstep-sound doesn't travel with the object. => vel=0
				m_client->sound()->playSoundAt(0, spec, foot_pos, v3f(0.0f));
			}
		}
	}

	m_anim_timer += dtime;
	if(m_anim_timer >= m_anim_framelength)
	{
		m_anim_timer -= m_anim_framelength;
		m_anim_frame++;
		if(m_anim_frame >= m_anim_num_frames)
			m_anim_frame = 0;
	}

	updateTexturePos();
""",
        """				// The footstep-sound doesn't travel with the object. => vel=0
				m_client->sound()->playSoundAt(0, spec, foot_pos, v3f(0.0f));
			}
		}

		m_anim_timer += dtime;
		if(m_anim_timer >= m_anim_framelength)
		{
			m_anim_timer -= m_anim_framelength;
			m_anim_frame++;
			if(m_anim_frame >= m_anim_num_frames)
				m_anim_frame = 0;
		}
	}

	updateTexturePos();
""",
    )],
}


def sh(*a, **kw):
    return subprocess.run(a, cwd=APP, check=True, **kw)


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    only = sys.argv[2:] or list(BUGS)
    for name in only:
        sh("git", "checkout", "-q", "--", ".")
        for rel, old, new in BUGS[name]:
            p = APP / rel
            s = open(p, encoding="utf-8", newline="").read()
            assert s.count(old) == 1, (name, rel, s.count(old))
            open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new))
        diff = subprocess.run(["git", "diff"], cwd=APP, check=True, capture_output=True).stdout
        (out / f"{name}.patch").write_bytes(diff)
        print(name, len(diff.splitlines()), "lines")
    sh("git", "checkout", "-q", "--", ".")


if __name__ == "__main__":
    main()
