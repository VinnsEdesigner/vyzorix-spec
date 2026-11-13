package vyzorixspec

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestBuildSchemaCurrentVersion(t *testing.T) {
	got, err := BuildSchema(BuildSchemaVersion)
	if err != nil {
		t.Fatalf("BuildSchema(%q) = %v, want the current schema", BuildSchemaVersion, err)
	}

	if !strings.Contains(string(got), "BuildRecipe") {
		t.Fatalf("schema does not describe the recipe: %s", got)
	}

	// The published schema must parse as JSON: the builder validates against it
	// and the server serves it, so malformed bytes would break both.
	var doc map[string]any
	if err := json.Unmarshal(got, &doc); err != nil {
		t.Fatalf("schema is not valid JSON: %v", err)
	}
}

func TestBuildSchemaUnknownVersionRefuses(t *testing.T) {
	_, err := BuildSchema("999")
	if err == nil {
		t.Fatal("BuildSchema(999) = nil error, want a refusal")
	}

	var unknown *UnknownBuildSchemaVersionError
	if !buildAsError(err, &unknown) {
		t.Fatalf("BuildSchema(999) = %T, want *UnknownBuildSchemaVersionError", err)
	}

	if unknown.Current != BuildSchemaVersion {
		t.Errorf("Current = %q, want %q", unknown.Current, BuildSchemaVersion)
	}
}

func TestBuildRecipeTypesDecodeTheSchemaShape(t *testing.T) {
	// The types and the schema are generated from one CUE file; this pins that
	// the JSON the schema describes decodes into the types without error.
	const recipe = `{
		"build": {"version": "v1.2.0", "abi": ["arm64-v8a"], "suite": "bookworm"},
		"artifact": [
			{"name": "engine", "lang": "cpp", "kind": "dir", "path": "media-ingest-c"}
		]
	}`

	var typed BuildRecipe
	if err := json.Unmarshal([]byte(recipe), &typed); err != nil {
		t.Fatalf("recipe does not decode into BuildRecipe: %v", err)
	}

	if typed.Build.Version != "v1.2.0" || typed.Build.Suite != "bookworm" {
		t.Errorf("build = %+v, want version v1.2.0 on bookworm", typed.Build)
	}

	if len(typed.Build.Abi) != 1 || typed.Build.Abi[0] != "arm64-v8a" {
		t.Errorf("abi = %+v, want [arm64-v8a]", typed.Build.Abi)
	}

	if len(typed.Artifact) != 1 || typed.Artifact[0].Name != "engine" || typed.Artifact[0].Lang != "cpp" {
		t.Errorf("artifact = %+v, want one cpp engine", typed.Artifact)
	}
}

// buildAsError is errors.As specialized to *UnknownBuildSchemaVersionError, kept
// local so the package has no non-test imports for its own error type.
func buildAsError(err error, target **UnknownBuildSchemaVersionError) bool {
	u, ok := err.(*UnknownBuildSchemaVersionError)
	if ok {
		*target = u
	}

	return ok
}
