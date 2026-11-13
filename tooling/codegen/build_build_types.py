#!/usr/bin/env python3
"""Generate the build-recipe Go types from tooling/schema/build.cue.

A thin wrapper over build_types.py: it points the shared generator at build.cue
and build.go.
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("CUE_FILE", "tooling/schema/build.cue")
os.environ.setdefault("SOURCE_CUE", "tooling/schema/build.cue")
os.environ.setdefault("HEADER",
    "The build-recipe wire types, shared by the deploy CLI and vyzorix-builder.")
os.environ.setdefault("GO_OUT", "build.go")
os.environ.setdefault("GO_PKG", "vyzorixspec")

runpy.run_path(os.path.join(HERE, "build_types.py"), run_name="__main__")
