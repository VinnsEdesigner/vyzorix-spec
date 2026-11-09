package vyzorixspec

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestSchemaCurrentVersion(t *testing.T) {
	got, err := Schema(SchemaVersion)
	if err != nil {
		t.Fatalf("Schema(%q) = %v, want the current schema", SchemaVersion, err)
	}

	if !strings.Contains(string(got), "DeployManifest") {
		t.Fatalf("schema does not describe the manifest: %s", got)
	}

	// The published schema must parse as JSON: the CLI validates against it and
	// the server serves it, so malformed bytes would break both.
	var doc map[string]any
	if err := json.Unmarshal(got, &doc); err != nil {
		t.Fatalf("schema is not valid JSON: %v", err)
	}
}

func TestSchemaUnknownVersionRefuses(t *testing.T) {
	_, err := Schema("999")
	if err == nil {
		t.Fatal("Schema(999) = nil error, want a refusal")
	}

	var unknown *UnknownSchemaVersionError
	if !asError(err, &unknown) {
		t.Fatalf("Schema(999) = %T, want *UnknownSchemaVersionError", err)
	}

	if unknown.Current != SchemaVersion {
		t.Errorf("Current = %q, want %q", unknown.Current, SchemaVersion)
	}
}

func TestManifestTypesDecodeTheSchemaShape(t *testing.T) {
	// The types and the schema are generated from one CUE file; this pins that
	// the JSON the schema describes decodes into the types without error.
	const manifest = `{
		"device": {"id": "d_01H", "org": "org_1"},
		"app": [{"name": "vfd", "cmd": "/bin/vfd", "port": 8080}]
	}`

	var typed DeployManifest
	if err := json.Unmarshal([]byte(manifest), &typed); err != nil {
		t.Fatalf("manifest does not decode into DeployManifest: %v", err)
	}

	if typed.Device.ID != "d_01H" || typed.Device.Org != "org_1" {
		t.Errorf("device = %+v, want d_01H/org_1", typed.Device)
	}

	if len(typed.App) != 1 || typed.App[0].Name != "vfd" || typed.App[0].Port != 8080 {
		t.Errorf("app = %+v, want one vfd app on 8080", typed.App)
	}
}

// asError is errors.As specialized to *UnknownSchemaVersionError, kept local so
// the package has no non-test imports for its own error type.
func asError(err error, target **UnknownSchemaVersionError) bool {
	u, ok := err.(*UnknownSchemaVersionError)
	if ok {
		*target = u
	}

	return ok
}
