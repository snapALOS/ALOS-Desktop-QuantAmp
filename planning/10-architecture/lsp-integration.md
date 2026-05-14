# LSP Integration

**Goal for v0.2:** Forge is a real IDE with code intelligence for the languages ALOS itself is written in. Registry is pluggable so users can add more.

## Shipped in v0.2

| Language | Server | Source | Bundle strategy |
|---|---|---|---|
| Python | `pyright` | npm (`pyright`) | Shipped as vendored node_modules binary |
| TypeScript / JavaScript | `typescript-language-server` | npm | Shipped vendored |
| Rust | `rust-analyzer` | standalone binary | Shipped as OS-specific binary in `resources/lsp/` |

Others users commonly want (deferred to later 0.x as pluggable):
- `gopls` (Go)
- `clangd` (C/C++)
- `lua-language-server`
- `solargraph` (Ruby)
- `jdtls` (Java)

## Architecture

```
Forge (Monaco)  ─── JSON-RPC over stdio ───▶  LSP server process
                                                    ▲
                                                    │  spawned/managed by
                                                    │
                                        Rust LSP supervisor
                                         (src-tauri/src/lsp/)
                                                    ▲
                                                    │  reads
                                                    │
                                            LSP registry
                                         (config/lsp.toml)
```

- **Monaco ↔ server:** standard LSP JSON-RPC. Use `monaco-languageclient` on the frontend, wrapped in a small adapter.
- **Supervisor:** Rust module owns spawning, health checks, restart on crash, per-workspace process lifecycle. Lives in `src-tauri/src/lsp/`.
- **Registry:** a TOML file the user can edit to add/remove servers without recompilation.

## Registry format

```toml
# ~/.alos/lsp.toml (generated on first run from defaults, user-editable)

[[server]]
id = "pyright"
languages = ["python"]
command = ["node", "${alos.resources}/lsp/pyright/langserver.js", "--stdio"]
root_markers = ["pyproject.toml", "setup.py", "requirements.txt", ".git"]
enabled = true

[[server]]
id = "typescript"
languages = ["typescript", "javascript", "typescriptreact", "javascriptreact"]
command = ["node", "${alos.resources}/lsp/ts-ls/server.js", "--stdio"]
root_markers = ["package.json", "tsconfig.json", ".git"]
enabled = true

[[server]]
id = "rust-analyzer"
languages = ["rust"]
command = ["${alos.resources}/lsp/rust-analyzer"]
root_markers = ["Cargo.toml"]
enabled = true
```

`${alos.resources}` resolves to the bundled resource dir. Users can point to their own installed binaries.

## Lifecycle

1. User opens a file in Forge.
2. Forge determines the file's language from extension.
3. Forge asks the LSP supervisor (via Tauri command `lsp_request_server`) for a server for that language + workspace root.
4. Supervisor either returns an existing handle or spawns a new one.
5. Monaco starts an LSP client connected to that server.
6. Server stays warm for the workspace; killed on workspace close or 5-minute idle.

## Agent hooks

Atlas consumes LSP where it gives better truth than static parse (cross-file references, go-to-definition across packages). Agents invoke Atlas tools, which may in turn call LSP — agents never talk to LSP directly.

## What v0.2 does NOT do

- Remote LSP (deferred to v0.3).
- LSP for non-file-backed buffers.
- Custom extensions to the LSP protocol.
- Auto-installing servers (user manages their own config past the three bundled ones).

## Acceptance criteria

- [ ] Opening a `.py` file in a workspace with `pyproject.toml` gives Monaco working hover, completion, go-to-def within 10 seconds.
- [ ] Same for `.ts` with `package.json` present.
- [ ] Same for `.rs` with `Cargo.toml` present.
- [ ] Killing the LSP server process in Activity Monitor auto-restarts it within 5 seconds without losing the user's buffers.
- [ ] User can disable a server by editing `~/.alos/lsp.toml` and restarting ALOS.
