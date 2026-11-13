package vyzorixspec

import (
	_ "embed"
	"fmt"
)

// BuildSchemaVersion is the published build-recipe schema's version. It is the
// {version} segment of GET /v1/deploy/build-schema/{version}. It moves when the
// recipe shape does; a client pins it, so a recipe the client validated is a
// recipe the builder accepts.
const BuildSchemaVersion = "1"

//go:embed schema/build.schema.json
var buildSchemaJSON []byte

// BuildSchema returns the published JSON Schema for the requested version. Only
// the current version is served: an unknown version is a refusal, not a fallback
// to a schema that would accept a different shape.
func BuildSchema(version string) ([]byte, error) {
	if version != BuildSchemaVersion {
		return nil, &UnknownBuildSchemaVersionError{Requested: version, Current: BuildSchemaVersion}
	}

	return buildSchemaJSON, nil
}

// UnknownBuildSchemaVersionError names both versions so a client can see which
// one to pin. It maps to 404.
type UnknownBuildSchemaVersionError struct {
	Requested string
	Current   string
}

// Error implements error.
func (e *UnknownBuildSchemaVersionError) Error() string {
	return fmt.Sprintf("build: schema version %q does not exist; current version is %s", e.Requested, e.Current)
}
