"""
REQ-006 doc_parser — adapters/config/__init__.py

adapters/config 레이어 public export
"""
from doc_parser.adapters.config.yaml_config_loader import YamlConfigLoader

__all__ = [
    "YamlConfigLoader",
]