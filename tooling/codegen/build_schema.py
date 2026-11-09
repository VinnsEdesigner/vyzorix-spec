#!/usr/bin/env python3
"""Publish the manifest JSON Schema from tooling/schema/deploy.cue.

The manifest is authored once, in CUE (FR-22). build_types.py projects it onto
the Go wire types; this script projects the same file onto the JSON Schema the
server publishes and the CLI validates against (FR-2). One source, two
artefacts, so the schema the CLI checks and the server enforces cannot drift.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_types import parse_cue_file  # noqa: E402

CUE_PATH = os.environ.get("CUE_PATH", "tooling/schema/deploy.cue")
OUT_PATH = os.environ.get("OUT_PATH", "schema/deploy.schema.json")

# The schema version. It is the {version} segment of
# GET /v1/deploy/schema/{version}, and the value of SchemaVersion in schema.go.
VERSION = "1"

# The root type: the manifest is this object.
ROOT = "DeployManifest"

PRIMITIVES = {
    "int": "integer",
    "int64": "integer",
    "string": "string",
    "bool": "boolean",
    "float": "number",
}

# The JSON Schema type a constraint applies to, so a bound lands on the right
# keyword: `>=1` is minLength for a string, minItems for an array, minimum for a
# number.
NUMERIC_SCHEMA_TYPES = {"integer", "number"}


def apply_constraints(schema, constraints, field_type):
    """Fold a field's `& <constraint>` terms into its JSON Schema.

    The published schema is what the CLI pre-validates against (FR-2), so a
    constraint the server enforces must appear here or the CLI accepts a manifest
    the server then refuses. Each term is one of: a regex (`=~"..."`), an
    equality (`=="..."`), a bound (`>=N` / `<=N`), or an enum (`"a" | "b"`).
    """
    for term in constraints:
        term = term.strip()

        if term.startswith("=~"):
            schema["pattern"] = term[2:].strip().strip('"')
            continue

        if term.startswith("=="):
            schema["const"] = term[2:].strip().strip('"')
            continue

        if term.startswith(">=") or term.startswith("<="):
            op, num = term[:2], int(term[2:].strip())
            if field_type == "array":
                schema["minItems" if op == ">=" else "maxItems"] = num
            elif schema.get("type") in NUMERIC_SCHEMA_TYPES:
                schema["minimum" if op == ">=" else "maximum"] = num
            else:
                schema["minLength" if op == ">=" else "maxLength"] = num
            continue

        if "|" in term:
            schema["enum"] = [v.strip().strip('"') for v in term.split("|")]
            continue

        raise ValueError(f"cannot project constraint {term!r} for a {field_type} field")

    return schema


def field_schema(field):
    ftype = field["type"]
    constraints = field.get("constraints") or []

    if ftype == "map":
        value = field.get("map_value", "_")
        # additionalProperties takes a schema, not a bare type name: "string" is
        # invalid JSON Schema and every validator rejects the whole document.
        value_schema = {"type": PRIMITIVES.get(value, "string")}
        # A value constraint (`{[string]: string & ==""}`) is what makes the
        # `[app.secrets]` table names-only: every value must be empty.
        apply_constraints(value_schema, [field["value_constraint"]] if field.get("value_constraint") else [], "value")

        return {"type": "object", "additionalProperties": value_schema}

    if ftype == "any":
        if field.get("union"):
            return {"oneOf": [member_schema(m) for m in field["union"]]}
        return apply_constraints({}, constraints, "any")

    if field.get("is_nested"):
        return {"$ref": f"#/$defs/{ftype}"}

    if ftype.startswith("[..."):
        elem = ftype[4:-1]
        if elem in PRIMITIVES:
            base = {"type": "array", "items": {"type": PRIMITIVES[elem]}}
        else:
            base = {"type": "array", "items": {"$ref": f"#/$defs/{elem}"}}

        return apply_constraints(base, constraints, "array")

    base = {"type": PRIMITIVES.get(ftype, "string")}

    return apply_constraints(base, constraints, "scalar")


def member_schema(member):
    """One branch of a union: a nested type reference or a primitive."""
    if member.startswith("#"):
        return {"$ref": f"#/$defs/{member[1:]}"}

    return {"type": PRIMITIVES.get(member, "string")}


def type_schema(schema):
    props = {}
    required = []

    for field in schema["fields"]:
        props[field["name"]] = field_schema(field)
        if not field["optional"]:
            required.append(field["name"])

    out = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        out["required"] = required

    return out


def main():
    schemas = parse_cue_file(CUE_PATH)
    defs = {s["name"]: type_schema(s) for s in schemas}

    if ROOT not in defs:
        print(f"deploy.cue has no #{ROOT}", file=sys.stderr)
        return 1

    # No $id. The schema is served from the server's own URL and every $ref in it
    # is fragment-only, so a validator needs nothing but the retrieval URI. A
    # committed $id would pin one host, which a self-hosted deployment is not; the
    # client keys the document by the server URL it fetched it from instead.
    doc = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Vyzorix deploy manifest (vyzorix.toml)",
        "description": (
            "The vyzorix.toml manifest, VYZORIX_DEPLOY_CONTRACT.md section 4. "
            "Generated from tooling/schema/deploy.cue; do not edit by hand."
        ),
        "$ref": f"#/$defs/{ROOT}",
        "$defs": defs,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")

    print(f"Wrote {OUT_PATH} ({len(defs)} types, version {VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
