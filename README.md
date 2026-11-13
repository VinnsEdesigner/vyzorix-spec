# vyzorix-spec

The deploy manifest contract for Vyzorix: the `vyzorix.toml` wire types and the
JSON Schema that describes them.

This repository is the single source of truth for the manifest shape. The
`vyzorix` deploy CLI and the Vyzorix update server both import this module, so
neither re-declares the wire shape and the two cannot drift
(`VYZORIX_DEPLOY_CONTRACT.md` FR-23). It is public because the CLI is public and
its release build must resolve its dependencies without credentials.

## Contents

| Path | What it is |
| --- | --- |
| `tooling/schema/deploy.cue` | The manifest, authored once in CUE. |
| `tooling/schema/build.cue` | The build recipe, authored once in CUE. |
| `manifest.go` | Generated manifest wire types. Do not edit. |
| `build.go` | Generated build-recipe wire types. Do not edit. |
| `schema/deploy.schema.json` | Generated manifest JSON Schema. Do not edit. |
| `schema/build.schema.json` | Generated build-recipe JSON Schema. Do not edit. |
| `schema.go` | `Schema(version)` and `SchemaVersion`; embeds the manifest schema. |
| `build_schema.go` | `BuildSchema(version)` and `BuildSchemaVersion`; embeds the recipe schema. |

## Regenerate

All four artefacts are generated from CUE — one generator, two documents:

```sh
python3 tooling/codegen/build_types.py         # deploy.cue  -> manifest.go
python3 tooling/codegen/build_schema.py        # deploy.cue  -> schema/deploy.schema.json
python3 tooling/codegen/build_build_types.py   # build.cue   -> build.go
python3 tooling/codegen/build_build_schema.py  # build.cue   -> schema/build.schema.json
```

The build gate re-runs all four and fails on drift, so a change to either `.cue`
must be accompanied by the regenerated files.

## Use

```go
import vyzorixspec "github.com/VinnsEdesigner/vyzorix-spec"

var m vyzorixspec.DeployManifest
if err := json.Unmarshal(manifestJSON, &m); err != nil {
	// ...
}

schema, err := vyzorixspec.Schema(vyzorixspec.SchemaVersion)
```

## Schema versioning

`SchemaVersion` is the `{version}` segment of the server's
`GET /v1/deploy/schema/{version}`. It moves when the manifest shape changes. A
client pins it, so a manifest the client validated is the manifest the server
accepts; an unknown version is a refusal, never a silent fallback.

## License

GPL-3.0. See `LICENSE`.
