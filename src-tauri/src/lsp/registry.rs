use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LspServerConfig {
    pub id: String,
    pub languages: Vec<String>,
    pub command: Vec<String>,
    pub root_markers: Vec<String>,
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

fn default_enabled() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LspRegistryConfig {
    #[serde(rename = "server")]
    pub servers: Vec<LspServerConfig>,
}

pub struct LspRegistry {
    pub config: LspRegistryConfig,
}

impl LspRegistry {
    /// Load registry from a TOML file.
    pub fn load_from_file(path: &Path) -> Result<Self> {
        let content = std::fs::read_to_string(path)
            .with_context(|| format!("Failed to read LSP registry at {}", path.display()))?;
        let config: LspRegistryConfig = toml::from_str(&content)
            .with_context(|| format!("Failed to parse LSP registry TOML at {}", path.display()))?;
        Ok(Self { config })
    }

    /// Find a server config for a given language.
    pub fn find_for_language(&self, language: &str) -> Option<&LspServerConfig> {
        self.config
            .servers
            .iter()
            .find(|s| s.enabled && s.languages.contains(&language.to_string()))
    }

    /// Return the list of all supported languages across all enabled servers.
    pub fn supported_languages(&self) -> Vec<String> {
        let mut langs = Vec::new();
        for server in &self.config.servers {
            if server.enabled {
                for lang in &server.languages {
                    if !langs.contains(lang) {
                        langs.push(lang.clone());
                    }
                }
            }
        }
        langs
    }

    /// Ensure the user-editable lsp.toml exists in ~/.alos/
    pub fn ensure_config(resource_dir: &Path) -> Result<PathBuf> {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .map_err(|_| anyhow!("Cannot determine home directory"))?;
        let mut path = PathBuf::from(home);
        path.push(".alos");
        if !path.exists() {
            std::fs::create_dir_all(&path)?;
        }
        path.push("lsp.toml");

        if !path.exists() {
            let template = resource_dir.join("lsp").join("lsp.toml");
            if template.exists() {
                std::fs::copy(&template, &path)?;
                log::info!(
                    "LspRegistry: initialized from template at {}",
                    path.display()
                );
            } else {
                // Create an empty registry if no template
                std::fs::write(&path, "server = []")?;
            }
        }
        Ok(path)
    }
}
