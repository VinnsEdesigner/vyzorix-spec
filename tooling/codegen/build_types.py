#!/usr/bin/env python3
"""Generate the manifest Go types from the CUE schema.

Reads tooling/schema/deploy.cue and emits Go structs into manifest.go, the
package the deploy CLI and the update server both import (FR-23).

CUE is the single source of truth for the wire DTOs. The TypeScript types are
NOT generated here: they come from the OpenAPI spec via orval (CUE -> Go structs
-> swag init -> openapi3.json -> orval -> generated/schemas). Deriving TS twice
would be a redundant second source; orval already produces a superset (body DTOs
+ *Params + helper types) that the SDK and React Query hooks consume.

CUE file format (deliberately restricted — a small, strict parser, not the full
CUE engine):
    package vyzorix

    #TypeName: {
        fieldName:  type
        optional?:  type
        mapField?:  {[string]: <primitive>}
        nested?:    #OtherType
        list:       [...string] | [...#OtherType]
    }

The parser is strict: any field line it cannot recognize is a hard error, so a
typo or an unsupported CUE construct fails loudly instead of silently dropping
the field from the generated struct.
"""
import os
import re
import sys
import glob
import subprocess

SCHEMA_DIR = os.environ.get("SCHEMA_DIR", "tooling/schema")
# The CUE file to read. Each generated artefact has exactly one source, so the
# manifest reads deploy.cue and the recipe reads build.cue; never both, or the
# types of one would leak into the other.
CUE_FILE = os.environ.get("CUE_FILE", "tooling/schema/deploy.cue")
# The source line the generated file's header names; the build wrapper overrides it.
SOURCE_CUE = os.environ.get("SOURCE_CUE", "tooling/schema/deploy.cue")
# The paragraph after the DO NOT EDIT line.
HEADER = os.environ.get(
    "HEADER",
    "The manifest wire types, shared by the deploy CLI and the update server so\n"
    "neither re-declares the shape (VYZORIX_DEPLOY_CONTRACT.md FR-23).",
)
# deploy.cue is the single source of truth for the manifest. This script emits
# the Go package both consumers import, so neither re-declares the wire shape.
GO_OUT = os.environ.get("GO_OUT", "manifest.go")
GO_PKG = os.environ.get("GO_PKG", "vyzorixspec")

# CUE type → Go type mapping
CUE_TO_GO = {
    "int": "int",
    "int64": "int64",
    "string": "string",
    "bool": "bool",
    "float": "float64",
    "any": "interface{}",
}


def split_types(content):
    """Split a .cue file into (name, body) type blocks with brace-balanced
    bodies — a naive `[^}]*` stops at the `}` inside an open map
    (`{[string]: _}`) and silently truncates those structs."""
    types = []
    for m in re.finditer(r"#(\w+):\s*\{", content):
        name = m.group(1)
        depth = 1
        i = m.end()
        while i < len(content) and depth > 0:
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
            i += 1
        types.append((name, content[m.end():i - 1]))
    return types


def parse_cue_file(filepath):
    """Parse a simplified CUE file into schema definitions."""
    with open(filepath) as f:
        content = f.read()

    # First pass: collect all type definitions (including nested refs)
    type_defs = {}
    for name, body in split_types(content):
        fields = []

        for line in body.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("//"):
                continue

            # Split off an optional `| *default` suffix first; a default never
            # contains `&`, so this cannot eat part of a constraint.
            default = None
            default_match = re.search(r"\s*\|\s*\*(.+?)$", line)
            if default_match:
                default = default_match.group(1)
                line = line[: default_match.start()].rstrip()

            name_match = re.match(r"(\w+)(\?)?:\s*(.+)$", line)
            if not name_match:
                raise ValueError(
                    f"{os.path.basename(filepath)}: cannot parse line in #{name}: {line!r}\n"
                    "  Supported: `name: type`, `name?: type`, `name?: {[string]: <primitive>}`, "
                    "`name?: #Type`, `name: [...type] | [...#Type]`, each with optional "
                    '`& <constraint>` terms (regex, bounds, enum).'
                )

            fname = name_match.group(1)
            optional = name_match.group(2) == "?"
            type_expr = name_match.group(3)

            # A map: {[string]: <value type>} with an optional `& <constraint>`
            # on the value. The constraint cannot contain `}`.
            map_match = re.match(r"^\{\[string\]:\s*(\w+|_)(?:\s*&\s*(.+?))?\}$", type_expr)
            if map_match:
                fields.append({
                    "name": fname,
                    "type": "map",
                    "map_value": map_match.group(1),
                    "value_constraint": map_match.group(2),
                    "optional": optional,
                    "default": default,
                    "is_nested": False,
                    "constraints": [],
                })
                continue

            # `any`: a bare `_` with no constraints.
            if type_expr == "_":
                fields.append({
                    "name": fname,
                    "type": "any",
                    "optional": optional,
                    "default": default,
                    "is_nested": False,
                    "constraints": [],
                })
                continue

            # Everything else: a base type followed by zero or more
            # `& <constraint>` terms. `&` never appears inside a constraint, so a
            # plain split is exact.
            terms = [t.strip() for t in type_expr.split("&")]
            base, constraints = terms[0], terms[1:]

            # A union `A | B`. TOML has no sum type, so a union decodes as `any`
            # in Go and is published as a oneOf; `pwa` is the one field that needs
            # it (`pwa = true` or a `[app.pwa]` table, §4.1).
            if "|" in base:
                fields.append({
                    "name": fname,
                    "type": "any",
                    "union": [m.strip() for m in base.split("|")],
                    "optional": optional,
                    "default": default,
                    "is_nested": False,
                    "constraints": constraints,
                })
                continue

            if base.startswith("#"):
                ftype, is_nested = base[1:], True
            elif re.match(r"^\[\.\.\.#?\w+\]$", base):
                # Array: [...string] or [...#TypeName]. Nested-ref arrays render
                # as []TypeName (not pointers), matching openapi.
                ftype, is_nested = f"[...{base[4:-1].lstrip('#')}]", False
            elif re.match(r"^\w+$", base):
                # A primitive. CUE_TO_GO maps the known ones; anything else
                # passes through as its own name, as the generator always has.
                ftype, is_nested = base, False
            else:
                raise ValueError(
                    f"{os.path.basename(filepath)}: cannot parse line in #{name}: {line!r}\n"
                    "  Supported: `name: type`, `name?: type`, `name?: {[string]: <primitive>}`, "
                    "`name?: #Type`, `name: [...type] | [...#Type]`."
                )

            fields.append({
                "name": fname,
                "type": ftype,
                "optional": optional,
                "default": default,
                "is_nested": is_nested,
                "constraints": constraints,
            })

        if fields:
            type_defs[name] = fields

    # Second pass: convert to schema list (keep nested refs as type references, don't inline)
    schemas = []
    for name, fields in type_defs.items():
        schemas.append({"name": name, "fields": fields})

    return schemas


def to_go_struct(schema):
    """Convert a schema to a Go struct definition. Fields are emitted in
    fieldalignment-optimal order (pointers/strings/slices before scalars) so
    the generated structs satisfy govet's fieldalignment check without padding."""
    # Resolve Go types first so we can sort by alignment cost.
    resolved = []
    for field in schema["fields"]:
        if field["type"] == "map":
            mv = field.get("map_value", "_")
            go_type = f"map[string]{CUE_TO_GO.get(mv, mv)}" if mv != "_" else "map[string]any"
        elif field["type"] == "any":
            go_type = "any"
        elif field.get("is_nested"):
            go_type = f"*{field['type']}" if field["optional"] else field["type"]
        elif field["type"].startswith("[..."):
            elem = field["type"].replace("[...", "").replace("]", "")
            go_type = f"[]{elem}"
        else:
            go_type = CUE_TO_GO.get(field["type"], field["type"])
            if field["type"] in ("int64",):
                go_type = f"*{go_type}" if field["optional"] else go_type
        resolved.append((field, go_type))

    # fieldalignment: group by field size so wide fields (pointer words: ptr,
    # string, slice, iface) come first, then 8-byte scalars, then narrower
    # ints, then bools — minimizing inter-field padding.
    def size_class(go_type):
        if go_type.startswith("*") or go_type == "string" or go_type == "interface{}":
            return 0  # 1-2 pointer words
        if go_type.startswith("[]"):
            return 1  # slice: 3 pointer words
        if go_type in ("int64", "float64", "int", "uint64"):
            return 2  # 8-byte
        if go_type in ("int32", "float32", "uint32"):
            return 3  # 4-byte
        if go_type in ("int16", "int8", "byte", "bool"):
            return 4  # 1-2 byte
        return 0

    resolved.sort(key=lambda fg: (size_class(fg[1]), fg[0]["name"]))

    lines = [f"type {schema['name']} struct {{"]
    for field, go_type in resolved:
        json_tag = field["name"]
        if field["optional"]:
            json_tag += ",omitempty"
        lines.append(f"\t{pascal(field['name'])} {go_type} `json:\"{json_tag}\"`")
    lines.append("}")
    return "\n".join(lines)


def pascal(name):
    """Wire field name (json tag) → Go field name (PascalCase, preserving
    acronyms the openapi package uses: ID, URL, FCM, MFA, OS, IMEI, HMAC, API).
    Trailing single-letter units like `ms` stay lowercase (RequestTimeoutMs);
    `ids` pluralizes to `IDs` (DeviceIDs)."""
    # Words split on underscores and lower→upper transitions.
    words = re.split(r"[_]|(?<=[a-z])(?=[A-Z])", name)
    words = [w for w in words if w]
    result = []
    for i, word in enumerate(words):
        low = word.lower()
        if word.isupper():
            result.append(word)
        elif low in ACRONYMS:
            result.append(low.upper())
        elif low in LOWER_UNITS:
            result.append(word[0].upper() + low[1:])
        elif low == "ids":
            result.append("IDs")
        else:
            result.append(word[0].upper() + word[1:])
    return "".join(result)


# Acronyms kept all-caps in Go field names.
ACRONYMS = {
    "id", "url", "uri", "fcm", "api", "jwt", "otp", "mfa", "os", "imei",
    "http", "https", "tcp", "udp", "ssl", "tls", "dns", "ip", "mac",
    "db", "sql", "ws", "totp", "csrf", "uuid", "sdk", "ota",
}
# Units that must stay lowercase in Go field names (RequestTimeoutMs, not MS).
LOWER_UNITS = {"ms"}


def main():
    if CUE_FILE:
        cue_files = [CUE_FILE]
    else:
        cue_files = sorted(glob.glob(os.path.join(SCHEMA_DIR, "*.cue")))
    if not cue_files:
        print(f"No .cue files found in {SCHEMA_DIR}")
        return

    all_schemas = []
    for cue_file in cue_files:
        schemas = parse_cue_file(cue_file)
        all_schemas.extend(schemas)
        print(f"  {os.path.basename(cue_file)}: {len(schemas)} schemas")

    # Generate Go
    go_dir = os.path.dirname(GO_OUT)
    if go_dir:
        os.makedirs(go_dir, exist_ok=True)
    with open(GO_OUT, "w") as f:
        f.write(f"// Code generated by tooling/codegen/build_types.py from {SOURCE_CUE}.\n")
        f.write("// DO NOT EDIT MANUALLY.\n")
        f.write("//\n")
        for line in HEADER.split("\n"):
            f.write(f"// {line}\n")
        f.write("\n")
        f.write(f"package {GO_PKG}\n\n")
        for schema in all_schemas:
            f.write(to_go_struct(schema) + "\n\n")

    print(f"\nGenerated {len(all_schemas)} types -> {GO_OUT}")


    # gofmt the output. The committed file is gofmt-aligned, so emitting raw
    # text would make the CI drift gate fail on every run for a purely cosmetic
    # difference. Formatting here keeps generator output and repo state equal.
    try:
        subprocess.run(["gofmt", "-w", GO_OUT], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"warning: could not gofmt {GO_OUT}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
