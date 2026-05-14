use std::path::PathBuf;

use app_lib::modules::{builtin_entries, load_all_modules, load_module_manifest};

/// Helper: workspace root is one directory above CARGO_MANIFEST_DIR (src-tauri/).
fn workspace_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("CARGO_MANIFEST_DIR should have a parent")
        .to_path_buf()
}

// -----------------------------------------------------------------------
// test_valid_fixture_loads
// -----------------------------------------------------------------------
#[test]
fn test_valid_fixture_loads() {
    let path = workspace_root().join("modules/_fixtures/valid/MODULE.toml");
    let entry = load_module_manifest(&path).expect("valid fixture should parse");

    assert_eq!(entry.id, "test-valid");
    assert_eq!(entry.display_name, "Test Valid Module");
    assert_eq!(entry.version, "0.1.0");
    assert_eq!(entry.order, 15);
    assert_eq!(entry.icon, "flask-conical");
    assert_eq!(entry.route, "/test-valid");
    assert!(entry.available);
    assert!(entry.error_message.is_none());
    assert!(!entry.hidden);
    assert_eq!(entry.kind, "module");
}

// -----------------------------------------------------------------------
// test_invalid_fixture_returns_error
// -----------------------------------------------------------------------
#[test]
fn test_invalid_fixture_returns_error() {
    let path = workspace_root().join("modules/_fixtures/invalid/MODULE.toml");
    let result = load_module_manifest(&path);

    assert!(result.is_err(), "invalid fixture should return an error");
    let msg = result.unwrap_err();
    // The error should mention the missing field so it is actionable.
    assert!(
        msg.contains("name") || msg.contains("nav"),
        "error message should mention the missing field: {msg}"
    );
}

// -----------------------------------------------------------------------
// test_underscore_dirs_skipped
// -----------------------------------------------------------------------
#[test]
fn test_underscore_dirs_skipped() {
    // Create a temporary directory that mimics the modules/ layout with only
    // underscore-prefixed subdirectories.
    let tmp = tempfile::tempdir().expect("failed to create temp dir");
    let underscored = tmp.path().join("_test");
    std::fs::create_dir_all(&underscored).unwrap();
    std::fs::write(
        underscored.join("MODULE.toml"),
        r#"
[module]
name = "should-be-skipped"
display_name = "Skipped"
version = "0.0.1"

[nav]
order = 1
icon = "x"
route = "/skip"
"#,
    )
    .unwrap();

    let entries = load_all_modules(tmp.path());
    assert!(
        entries.is_empty(),
        "directories starting with _ must be skipped, got: {entries:?}"
    );
}

// -----------------------------------------------------------------------
// test_builtins_present
// -----------------------------------------------------------------------
#[test]
fn test_builtins_present() {
    let builtins = builtin_entries();
    assert_eq!(builtins.len(), 4, "expected exactly 4 built-in entries");

    let chat = builtins
        .iter()
        .find(|e| e.id == "chat")
        .expect("missing chat");
    assert_eq!(chat.order, 90);
    assert_eq!(chat.icon, "message-square");
    assert_eq!(chat.route, "/chat");
    assert_eq!(chat.kind, "builtin");
    assert!(chat.available);

    let ext = builtins
        .iter()
        .find(|e| e.id == "extensions")
        .expect("missing extensions");
    assert_eq!(ext.order, 95);
    assert_eq!(ext.icon, "puzzle");
    assert_eq!(ext.route, "/extensions");
    assert_eq!(ext.kind, "builtin");
    assert!(ext.available);

    let scout = builtins
        .iter()
        .find(|e| e.id == "scout")
        .expect("missing scout");
    assert_eq!(scout.order, 97);
    assert_eq!(scout.icon, "activity");
    assert_eq!(scout.route, "/scout");
    assert_eq!(scout.kind, "builtin");
    assert!(scout.available);

    let settings = builtins
        .iter()
        .find(|e| e.id == "settings")
        .expect("missing settings");
    assert_eq!(settings.order, 99);
    assert_eq!(settings.icon, "settings");
    assert_eq!(settings.route, "/settings");
    assert_eq!(settings.kind, "builtin");
    assert!(settings.available);
}

// -----------------------------------------------------------------------
// test_order_sorting
// -----------------------------------------------------------------------
#[test]
fn test_order_sorting() {
    // Build a mixed list of modules + builtins and verify the sort contract.
    let tmp = tempfile::tempdir().expect("failed to create temp dir");

    // Module alpha: order 50
    let alpha = tmp.path().join("alpha");
    std::fs::create_dir_all(&alpha).unwrap();
    std::fs::write(
        alpha.join("MODULE.toml"),
        r#"
[module]
name = "alpha"
display_name = "Alpha"
version = "1.0.0"

[nav]
order = 50
icon = "a"
route = "/alpha"
"#,
    )
    .unwrap();

    // Module beta: order 10
    let beta = tmp.path().join("beta");
    std::fs::create_dir_all(&beta).unwrap();
    std::fs::write(
        beta.join("MODULE.toml"),
        r#"
[module]
name = "beta"
display_name = "Beta"
version = "1.0.0"

[nav]
order = 10
icon = "b"
route = "/beta"
"#,
    )
    .unwrap();

    // Module gamma: order 50 (collision with alpha — tiebreak by id)
    let gamma = tmp.path().join("gamma");
    std::fs::create_dir_all(&gamma).unwrap();
    std::fs::write(
        gamma.join("MODULE.toml"),
        r#"
[module]
name = "gamma"
display_name = "Gamma"
version = "1.0.0"

[nav]
order = 50
icon = "g"
route = "/gamma"
"#,
    )
    .unwrap();

    let mut entries = load_all_modules(tmp.path());
    entries.extend(builtin_entries());
    entries.sort_by(|a, b| a.order.cmp(&b.order).then_with(|| a.id.cmp(&b.id)));

    // Expected order: beta(10), alpha(50), gamma(50), chat(90), extensions(95), scout(97), settings(99)
    let ids: Vec<&str> = entries.iter().map(|e| e.id.as_str()).collect();
    assert_eq!(
        ids,
        vec!["beta", "alpha", "gamma", "chat", "extensions", "scout", "settings"],
        "entries should be sorted by order then id"
    );
}
