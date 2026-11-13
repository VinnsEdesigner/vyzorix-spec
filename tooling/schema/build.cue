package vyzorix

// The build recipe schema (vyzorix.build.toml). Authored once: build_build_types.py
// generates the Go types, build_build_schema.py publishes the JSON Schema.

// The recipe: build settings and one or more artifacts.
#BuildRecipe: {
        build: #BuildSettings
        artifact: [...#BuildArtifact] & >=1 & <=16
}

// [build] — the settings shared by every artifact.
#BuildSettings: {
        version?: string & >=1 & <=64
        abi?: [...string]
        suite?: string
        os?: string
}

// One [[artifact]] block. Artifacts that share `app` become one [[app]] block;
// the app-level fields (cmd, port, expose, autostart, purge, pwa, env) come from
// the first artifact of the group that sets them.
#BuildArtifact: {
        app: string & =~"^[a-z0-9][a-z0-9-]*$" & >=1 & <=32
        name: string & =~"^[a-z0-9][a-z0-9-]*$" & >=1 & <=64
        lang: string & "golang" | "rust" | "cpp" | "node-webroot" | "python" | "jvm" | "containerfile"
        cmd?: string & =~"^/"
        path?: string
        build?: string
        dist?: string
        file?: string
        out?: string
        arch?: string & "arm64-v8a" | "armeabi-v7a" | "x86_64" | "all"
        kind?: string & "dir" | "webroot"
        port?: int & >=0 & <=65535
        expose?: string & "loopback" | "lan" | "cloud"
        glibc_floor?: string
        env?: {[string]: string}
        libs?: [...string]
        static?: [...string]
        opts?: {[string]: string}
        autostart?: bool
        purge?: bool
        pwa?: bool
}
