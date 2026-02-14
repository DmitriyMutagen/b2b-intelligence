import json

from src.config import settings
from src.mcp_client import MCPClientManager
from src.memory import MemoryManager


def test_memory_manager_default_path_is_anchored_to_project_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "MEMORY_FILE", "nested/agent_memory.json")

    manager = MemoryManager()
    manager.add_entry("user", "hello")

    expected_path = tmp_path / "nested" / "agent_memory.json"
    assert expected_path.exists()


def test_mcp_config_relative_path_is_anchored_to_project_root(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "demo",
                        "transport": "stdio",
                        "command": "echo",
                        "args": ["ok"],
                        "enabled": True,
                        "env": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "PROJECT_ROOT", str(tmp_path))

    manager = MCPClientManager(config_path="configs/mcp_servers.json")
    configs = manager._load_server_configs()

    assert len(configs) == 1
    assert configs[0].name == "demo"
