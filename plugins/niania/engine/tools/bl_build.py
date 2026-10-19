# Blender entry: build the animated scene for a project.  blender -b --factory-startup --python bl_build.py -- <project_dir>
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from studio import build
build.build(os.path.abspath(sys.argv[sys.argv.index('--') + 1]))
