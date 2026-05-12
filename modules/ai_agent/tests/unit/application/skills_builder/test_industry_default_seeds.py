"""산업 default seed JSON 5종 구조 검증.

Sprint 3 plan §4.2 5/15 박아름 산출물:
modules/ai_agent/seeds/industry_defaults/{manufacturing,service,wholesale_retail,food,it}.json

각 산업당 5개 SkillNode (총 25). 5/16 `BuildFromIndustryDefaultUseCase`의 입력.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


SEEDS_DIR = Path(__file__).resolve().parents[4] / "seeds" / "industry_defaults"

EXPECTED_INDUSTRIES = {"manufacturing", "service", "wholesale_retail", "food", "it"}

# DB node_definitions.category CHECK 8종 (database/schemas/009_node_definitions.sql)
ALLOWED_CATEGORIES = {"trigger", "action", "condition", "transform", "ai", "integration", "utility", "output"}

# common_schemas.enums.RiskLevel
ALLOWED_RISK_LEVELS = {"Low", "Medium", "High", "Restricted"}

REQUIRED_SKILL_NODE_FIELDS = {
    "node_type", "name", "category", "description",
    "inputs", "outputs", "risk_level",
    "required_connections", "service_type",
}


def _load_all_seeds() -> dict[str, dict]:
    seeds = {}
    for code in EXPECTED_INDUSTRIES:
        path = SEEDS_DIR / f"{code}.json"
        with path.open(encoding="utf-8") as f:
            seeds[code] = json.load(f)
    return seeds


# ----------------------------------------------------------------------
# 파일 존재 + 로드
# ----------------------------------------------------------------------


def test_seeds_directory_exists():
    assert SEEDS_DIR.is_dir(), f"seeds 디렉토리 없음: {SEEDS_DIR}"


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_seed_file_loads_as_valid_json(code: str):
    path = SEEDS_DIR / f"{code}.json"
    assert path.exists(), f"{code}.json 파일 없음"
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)


# ----------------------------------------------------------------------
# 최상위 구조
# ----------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_seed_has_required_top_level_keys(code: str):
    seeds = _load_all_seeds()
    data = seeds[code]
    assert data["industry_code"] == code
    assert data["industry_name"], "industry_name 비어있음"
    assert isinstance(data.get("skill_nodes"), list), "skill_nodes 키가 list 아님"
    assert len(data["skill_nodes"]) >= 5, f"{code}: skill_nodes 5개 이상 필요 (plan §4.2 산업별 5~7)"


# ----------------------------------------------------------------------
# SkillNode 필드 검증
# ----------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_skill_node_required_fields(code: str):
    seeds = _load_all_seeds()
    for i, node in enumerate(seeds[code]["skill_nodes"]):
        missing = REQUIRED_SKILL_NODE_FIELDS - set(node.keys())
        assert not missing, f"{code}.skill_nodes[{i}] 필수 필드 누락: {missing}"


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_skill_node_category_in_db_check_enum(code: str):
    """category는 DB CHECK 영문 8종 안에 있어야 upsert 가능."""
    seeds = _load_all_seeds()
    for node in seeds[code]["skill_nodes"]:
        assert node["category"] in ALLOWED_CATEGORIES, (
            f"{code}.{node['node_type']} category='{node['category']}'가 DB CHECK 8종에 없음"
        )


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_skill_node_risk_level_valid(code: str):
    seeds = _load_all_seeds()
    for node in seeds[code]["skill_nodes"]:
        assert node["risk_level"] in ALLOWED_RISK_LEVELS, (
            f"{code}.{node['node_type']} risk_level='{node['risk_level']}' 비유효 (Low/Medium/High/Restricted)"
        )


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_skill_node_inputs_outputs_are_json_schema(code: str):
    """inputs/outputs는 JSON schema dict 형태."""
    seeds = _load_all_seeds()
    for node in seeds[code]["skill_nodes"]:
        for key in ("inputs", "outputs"):
            schema = node[key]
            assert isinstance(schema, dict), f"{code}.{node['node_type']}.{key}가 dict 아님"
            assert schema.get("type") == "object", (
                f"{code}.{node['node_type']}.{key}.type이 'object' 아님"
            )
            assert "properties" in schema, f"{code}.{node['node_type']}.{key}.properties 누락"


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_skill_node_type_has_industry_prefix(code: str):
    """node_type은 산업 코드 prefix를 가짐 — 다른 산업 노드와 충돌 회피.

    wholesale_retail의 prefix는 'wholesale_'로 축약.
    """
    seeds = _load_all_seeds()
    prefix = "wholesale_" if code == "wholesale_retail" else f"{code}_"
    for node in seeds[code]["skill_nodes"]:
        assert node["node_type"].startswith(prefix), (
            f"{code}.{node['node_type']}: prefix '{prefix}' 누락 (산업 간 충돌 방지)"
        )


# ----------------------------------------------------------------------
# 전체 uniqueness
# ----------------------------------------------------------------------


def test_all_node_types_unique_across_industries():
    seeds = _load_all_seeds()
    all_types = []
    for code, data in seeds.items():
        for node in data["skill_nodes"]:
            all_types.append(node["node_type"])
    assert len(all_types) == len(set(all_types)), "전체 SkillNode node_type 중복 존재"


def test_total_skill_node_count():
    """5종 산업 × 5개 SkillNode = 25개 (최소). plan §4.2 25~35 범위 안."""
    seeds = _load_all_seeds()
    total = sum(len(data["skill_nodes"]) for data in seeds.values())
    assert 25 <= total <= 35, f"전체 SkillNode 수 {total} — plan 범위(25~35) 벗어남"


# ----------------------------------------------------------------------
# 필드 의미 검증
# ----------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_required_connections_is_list_of_strings(code: str):
    seeds = _load_all_seeds()
    for node in seeds[code]["skill_nodes"]:
        rc = node["required_connections"]
        assert isinstance(rc, list)
        for conn in rc:
            assert isinstance(conn, str)
            assert conn, f"{code}.{node['node_type']} required_connections에 빈 문자열"


@pytest.mark.parametrize("code", sorted(EXPECTED_INDUSTRIES))
def test_service_type_is_string_or_null(code: str):
    seeds = _load_all_seeds()
    for node in seeds[code]["skill_nodes"]:
        st = node["service_type"]
        assert st is None or isinstance(st, str), (
            f"{code}.{node['node_type']} service_type가 string/null 아님"
        )
