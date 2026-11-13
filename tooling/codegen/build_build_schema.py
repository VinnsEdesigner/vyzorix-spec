#!/usr/bin/env python3
"""Publish the build-recipe JSON Schema from tooling/schema/build.cue.

A thin wrapper over build_schema.py: points the shared generator at build.cue and
schema/build.schema.json.
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("CUE_PATH", "tooling/schema/build.cue")
os.environ.setdefault("OUT_PATH", "schema/build.schema.json")
os.environ.setdefault("ROOT", "BuildRecipe")
os.environ.setdefault("VERSION", "1")
os.environ.setdefault("TITLE", "Vyzorix build recipe (vyzorix.build.toml)")
os.environ.setdefault("DESCRIPTION",
    "The vyzorix.build.toml recipe. Generated from tooling/schema/build.cue; "
    "do not edit by hand.")

runpy.run_path(os.path.join(HERE, "build_schema.py"), run_name="__main__")
