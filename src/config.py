from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerConfig(BaseSettings):
    """Configuration for a single MCP server."""

    name: str = Field(description="Unique name for the MCP server")
    transport: str = Field(
        default="stdio", description="Transport type: stdio, http, sse"
    )
    command: Optional[str] = Field(
        default=None, description="Command to run for stdio transport"
    )
    args: List[str] = Field(
        default_factory=list, description="Arguments for the command"
    )
    url: Optional[str] = Field(default=None, description="URL for http/sse transport")
    env: dict = Field(
        default_factory=dict, description="Environment variables for the server"
    )
    enabled: bool = Field(default=True, description="Whether this server is enabled")

    model_config = SettingsConfigDict(extra="ignore")


class Settings(BaseSettings):
    """Application settings managed by Pydantic."""

    # Google GenAI Configuration
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL_NAME: str = "gemini-2.0-flash-exp"  # Default to latest

    # Agent Configuration
    AGENT_NAME: str = "AntigravityAgent"
    DEBUG_MODE: bool = False
    PROJECT_ROOT: str = Field(
        default_factory=lambda: str(Path(__file__).resolve().parent.parent),
        description="Absolute path to the project root directory.",
    )

    # External LLM (OpenAI-compatible) Configuration
    OPENAI_BASE_URL: str = Field(
        default="",
        description="Base URL for OpenAI-compatible API (e.g., https://api.openai.com/v1 or http://localhost:11434/v1)",
    )
    OPENAI_API_KEY: str = Field(
        default="",
        description="API key for OpenAI-compatible endpoint. Leave blank if not required.",
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o-mini",
        description="Default model name for OpenAI-compatible chat completions.",
    )

    # Memory Configuration
    MEMORY_FILE: str = "agent_memory.json"
    ARTIFACTS_DIR: str = Field(
        default="artifacts",
        description="Directory for artifacts and logs. Relative paths are resolved from PROJECT_ROOT.",
    )

    # MCP Configuration
    MCP_ENABLED: bool = Field(default=False, description="Enable MCP integration")
    MCP_SERVERS_CONFIG: str = Field(
        default="mcp_servers.json", description="Path to MCP servers configuration file"
    )
    MCP_CONNECTION_TIMEOUT: int = Field(
        default=30, description="Timeout in seconds for MCP server connections"
    )
    MCP_TOOL_PREFIX: str = Field(
        default="mcp_", description="Prefix for MCP tool names to avoid conflicts"
    )

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def project_root_path(self) -> Path:
        """Return project root as an absolute path."""
        return Path(self.PROJECT_ROOT).expanduser().resolve()

    def resolve_path(self, path_value: str) -> Path:
        """
        Resolve a path value against project root when it is not absolute.

        Args:
            path_value: Relative or absolute file system path.

        Returns:
            Absolute resolved path.
        """
        path = Path(path_value).expanduser()
        if path.is_absolute():
            return path
        return self.project_root_path / path

    @property
    def memory_file_path(self) -> Path:
        """Return the resolved memory file path."""
        return self.resolve_path(self.MEMORY_FILE)

    @property
    def artifacts_path(self) -> Path:
        """Return the resolved artifacts directory path."""
        return self.resolve_path(self.ARTIFACTS_DIR)


# Global settings instance
settings = Settings()
