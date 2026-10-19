# Blender entry: QC an already-built project.  blender -b <project>/build/scene.blend --python bl_qc.py -- <project_dir> [every]
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from studio import qc
a = sys.argv[sys.argv.index('--') + 1:]
qc.run(os.path.abspath(a[0]), int(a[1]) if len(a) > 1 else 1)
