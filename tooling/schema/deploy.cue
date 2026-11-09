package vyzorix

// The deploy manifest schema (vyzorix.toml), VYZORIX_DEPLOY_CONTRACT.md §4.
// This file is the source of truth: build_schemas.py generates the Go types,
// build_deploy_schema.py publishes the JSON Schema the CLI validates against.
//
// Constraints (`& =~"…"`, `& >=N`, `& <=N`, `& =="…"`, `A | B`) are projected
// onto the published JSON Schema so the CLI refuses what the server would; Go
// carries only the field type.

// The manifest: one device and one or more apps, in declaration order.
#DeployManifest: {
        device: #DeployDevice
        app: [...#DeployApp] & >=1 & <=32
}

// The [device] block. Only id, org and an optional name are the operator's;
// memberId, version and each dir are server-injected and may not be set here.
#DeployDevice: {
        id: string & >=1 & <=128
        org: string & >=1
        name?: string
}

// One [[app]] block. Order is significant: it is the order the config records
// and the device applies.
#DeployApp: {
        name: string & =~"^[a-z0-9][a-z0-9-]*$" & >=1 & <=32
        cmd: string & =~"^/"
        port?: int & >=0 & <=65535
        expose?: string & "loopback" | "lan" | "cloud"
        autostart?: bool
        purge?: bool
        env?: {[string]: string}
        secrets?: {[string]: string & ==""}
        pwa?: bool | #DeployPWA
        artifact?: [...#DeployArtifact]
}

// One artifact reference. The URL is literal and the digest pins its bytes.
#DeployArtifact: {
        name: string & =~"^[a-z0-9][a-z0-9-]*$" & >=1 & <=64
        url: string & =~"^https://"
        sha256: string & =~"^[0-9a-f]{64}$"
        arch?: string & "arm64-v8a" | "armeabi-v7a" | "x86_64"
        kind?: string & "dir" | "webroot"
        size?: int64
}

// The per-app web-manifest declaration. In the manifest it is a boolean or a
// table; the table form overrides the generated defaults.
#DeployPWA: {
        name?: string
        short_name?: string
        description?: string
        theme_color?: string
        background_color?: string
        display?: string & "standalone" | "fullscreen" | "minimal-ui" | "browser"
        orientation?: string
        start_url?: string
        icons?: [...#DeployIcon]
}

// One generated web manifest's icon entry.
#DeployIcon: {
        src: string
        sizes: string
        type: string
}
