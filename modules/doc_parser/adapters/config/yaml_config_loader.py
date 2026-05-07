"""
REQ-006 doc-parser — adapters/config/yaml_config_loader.py

YamlConfigLoader
ConfigLoaderPort 구현체
config/parser_quality.yaml 에서 설정 로드
"""
from __future__ import annotations

from pathlib import Path

import yaml

from doc_parser.domain.entities.chunk import ChunkingStrategy
from doc_parser.domain.entities.pii import PIIMaskRule
from doc_parser.domain.entities.quality import QualityConfig
from doc_parser.domain.ports.config_port import ConfigLoaderPort

# 기본 config 파일 경로
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "parser_quality.yaml"


class YamlConfigLoader(ConfigLoaderPort):
    """YAML 설정 로더 구현체.

    config/parser_quality.yaml 에서 설정을 로드하여
    QualityConfig, ChunkingStrategy, PIIMaskRule 반환.

    Args:
        config_path: yaml 파일 경로 (기본: config/parser_quality.yaml)
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or _DEFAULT_CONFIG_PATH
        self._raw: dict = self._load_yaml()

    def load_quality_config(self) -> QualityConfig:
        """품질 게이트 설정 로드.

        Returns:
            QualityConfig: 품질 게이트 임계값 설정
        """
        return QualityConfig(
            min_text_length=self._raw["min_text_length"],
            min_text_per_page=self._raw["min_text_per_page"],
            korean_ratio_warn=self._raw["korean_ratio_warn"],
            broken_char_warn=self._raw["broken_char_warn"],
            blocks_per_page_warn=self._raw["blocks_per_page_warn"],
            max_parser_warnings=self._raw["max_parser_warnings"],
            min_heading_ratio=self._raw["min_heading_ratio"],
            min_valid_table_ratio=self._raw["min_valid_table_ratio"],
            min_structural_chunk_ratio=self._raw["min_structural_chunk_ratio"],
            warn_threshold_count=self._raw["warn_threshold_count"],
        )

    def load_chunking_strategy(self) -> ChunkingStrategy:
        """청킹 전략 설정 로드.

        Returns:
            ChunkingStrategy: 청킹 전략 설정
        """
        return ChunkingStrategy(
            max_tokens=self._raw["max_tokens"],
            overlap_tokens=self._raw["token_chunk_overlap"],
            token_estimator_mode=self._raw["token_estimator_mode"],
        )

    def load_pii_rules(self) -> list[PIIMaskRule]:
        """PII 마스킹 규칙 로드.

        yaml 에 pii_rules 섹션 없으면 기본값(PIIMaskRule.defaults()) 반환.

        Returns:
            list[PIIMaskRule]: PII 마스킹 규칙 목록
        """
        pii_rules = self._raw.get("pii_rules")
        if not pii_rules:
            return PIIMaskRule.defaults()

        return [
            PIIMaskRule(
                pattern=rule["pattern"],
                replacement=rule["replacement"],
                label=rule["label"],
            )
            for rule in pii_rules
        ]

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _load_yaml(self) -> dict:
        """YAML 파일 로드.

        Raises:
            FileNotFoundError: 설정 파일 없음
            RuntimeError: YAML 파싱 실패
        """
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"설정 파일 없음: {self._config_path}"
            )
        try:
            with open(self._config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise RuntimeError(f"YAML 파싱 실패: {e}") from e