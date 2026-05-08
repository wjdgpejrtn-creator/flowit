"""
REQ-006 doc_parser — domain/ports/config_port.py

ConfigLoaderPort
설정 로더 ABC 계약
구현체 위치: adapters/config/yaml_config_loader.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from doc_parser.domain.entities.chunk import ChunkingStrategy
from doc_parser.domain.entities.pii import PIIMaskRule
from doc_parser.domain.entities.quality import QualityConfig


class ConfigLoaderPort(ABC):
    """설정 로더 Port (인터페이스 계약).

    구현체: adapters/config/YamlConfigLoader
    설정 파일: config/parser_quality.yaml
    """

    @abstractmethod
    def load_quality_config(self) -> QualityConfig:
        """품질 게이트 설정 로드.

        Returns:
            QualityConfig: 품질 게이트 임계값 설정
        """
        ...

    @abstractmethod
    def load_chunking_strategy(self) -> ChunkingStrategy:
        """청킹 전략 설정 로드.

        Returns:
            ChunkingStrategy: 청킹 전략 설정
        """
        ...

    @abstractmethod
    def load_pii_rules(self) -> list[PIIMaskRule]:
        """PII 마스킹 규칙 로드.

        Returns:
            list[PIIMaskRule]: PII 마스킹 규칙 목록
        """
        ...