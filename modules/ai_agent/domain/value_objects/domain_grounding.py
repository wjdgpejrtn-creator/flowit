"""도메인 그라운딩 레이어 VO (ADR-0029) — skill builder 전용, composer와 분리.

composer 온톨로지(`Skeleton`/`SlotSpec`/`Pattern`/`FILLED_BY`/`CAN_FOLLOW`)와 **어휘가
한 글자도 안 겹친다**. 노드는 그래프 엣지가 아니라 **node_type 문자열**로만 참조하고
ETL/로더가 `EXECUTABLE_NODE_TYPES`로 검증한다 → 두 서브그래프는 물리적으로 disjoint.

레이어: Domain(업종/직무) → Playbook(도메인 최적화 프로세스) → Stage(순서·역할 단계)
       + Rule(LLM 그라운딩 지침: 필수/금지/포커스/주의/형식).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RuleKind = Literal["required", "forbidden", "focus", "caution", "format"]
DomainKind = Literal["industry", "function"]

_RULE_KINDS: frozenset[str] = frozenset(
    {"required", "forbidden", "focus", "caution", "format"}
)
# required/forbidden은 node_type을 지목하는 제약, 나머지는 자유 문장 지침.
_NODE_RULE_KINDS: frozenset[str] = frozenset({"required", "forbidden"})


@dataclass(frozen=True)
class Rule:
    """도메인/프로세스 레벨 LLM 그라운딩 지침 1건.

    - required/forbidden: `node_type`을 지목하는 노드 제약, **또는** `statement`로 표현된
      프로세스 must/금지(예: "임계 초과 시 사람 승인 단계 필수"). 둘 중 하나는 있어야 함.
    - focus/caution/format: `statement`가 본문(신뢰할 산출물을 위한 지침).
    """

    kind: RuleKind
    statement: str = ""
    node_type: str | None = None
    rationale: str = ""
    severity: Literal["low", "normal", "high"] = "normal"


@dataclass(frozen=True)
class Stage:
    """프로세스의 한 단계 — 순서·역할·목적 + 단계별 '주요 포인트' + 허용 노드 후보."""

    order: int
    role: str  # SlotRole value 문자열(trigger/source/transform/gate/sink/router/…) — 참조만, 결합 아님
    purpose: str = ""
    allowed_node_types: tuple[str, ...] = ()
    key_points: tuple[str, ...] = ()


@dataclass(frozen=True)
class Playbook:
    """도메인 최적화 프로세스(구조). composer의 범용 Skeleton과 무관한 독립 정의."""

    id: str
    name: str
    intent: str = ""  # '|' 구분 키워드(소비측 매칭용, Pattern.intent와 동형이나 별개 라벨)
    summary: str = ""
    stages: tuple[Stage, ...] = ()
    rules: tuple[Rule, ...] = ()


@dataclass(frozen=True)
class Domain:
    """업종(industry) 또는 직무(function) — 도메인 그라운딩의 최상위."""

    code: str
    name: str
    kind: DomainKind
    description: str = ""
    rules: tuple[Rule, ...] = ()
    playbooks: tuple[Playbook, ...] = ()


@dataclass(frozen=True)
class DomainGroundingBundle:
    """소비측(skill builder 추출)이 받는 그라운딩 묶음 — 프롬프트 조립용.

    Domain 전체 + 편의 집계(필수/금지 node_type)를 담는다. 추출 프롬프트는 이걸로
    '프로세스 레일 + 단계 포인트 + 지침 + 필수/금지'를 LLM에 주입한다.
    """

    domain: Domain
    required_node_types: tuple[str, ...] = ()
    forbidden_node_types: tuple[str, ...] = ()


# ── 파싱 + 검증 (nodes_graph import 없음 — known_node_types를 호출부가 주입) ─────────


def _parse_rule(data: dict[str, Any]) -> Rule:
    kind = data.get("kind")
    if kind not in _RULE_KINDS:
        raise ValueError(f"알 수 없는 rule kind: {kind!r} (허용: {sorted(_RULE_KINDS)})")
    node_type = data.get("node_type")
    statement = data.get("statement", "")
    # required/forbidden은 node_type(노드 제약) 또는 statement(프로세스 must/금지) 중 하나는 있어야.
    if kind in _NODE_RULE_KINDS and not node_type and not statement:
        raise ValueError(f"rule kind={kind}는 node_type 또는 statement 필요")
    return Rule(
        kind=kind,
        statement=data.get("statement", ""),
        node_type=node_type,
        rationale=data.get("rationale", ""),
        severity=data.get("severity", "normal"),
    )


def _parse_stage(data: dict[str, Any]) -> Stage:
    return Stage(
        order=int(data["order"]),
        role=data["role"],
        purpose=data.get("purpose", ""),
        allowed_node_types=tuple(data.get("allowed_node_types", []) or []),
        key_points=tuple(data.get("key_points", []) or []),
    )


def _parse_playbook(data: dict[str, Any]) -> Playbook:
    stages = tuple(sorted((_parse_stage(s) for s in data.get("stages", [])), key=lambda s: s.order))
    return Playbook(
        id=data["id"],
        name=data["name"],
        intent=data.get("intent", ""),
        summary=data.get("summary", ""),
        stages=stages,
        rules=tuple(_parse_rule(r) for r in data.get("rules", [])),
    )


def _iter_node_types(domain: Domain) -> list[str]:
    out: list[str] = []
    for r in domain.rules:
        if r.node_type:
            out.append(r.node_type)
    for pb in domain.playbooks:
        for r in pb.rules:
            if r.node_type:
                out.append(r.node_type)
        for st in pb.stages:
            out.extend(st.allowed_node_types)
    return out


def parse_domain(data: dict[str, Any], known_node_types: set[str]) -> Domain:
    """도메인 시드 dict → Domain VO. 참조 node_type이 카탈로그에 실재하는지 검증.

    `known_node_types`는 호출부(ETL/로더)가 `EXECUTABLE_NODE_TYPES`로 주입한다(이 VO
    모듈은 nodes_graph에 의존하지 않는다 — 순수 도메인 유지). 실재하지 않는 node_type을
    참조하면 ValueError(환각 차단 — composer skeleton 시드 원칙 계승).
    """
    kind = data.get("kind")
    if kind not in ("industry", "function"):
        raise ValueError(f"domain kind는 industry|function: {kind!r}")
    domain = Domain(
        code=data["code"],
        name=data["name"],
        kind=kind,
        description=data.get("description", ""),
        rules=tuple(_parse_rule(r) for r in data.get("rules", [])),
        playbooks=tuple(_parse_playbook(p) for p in data.get("playbooks", [])),
    )
    unknown = sorted({nt for nt in _iter_node_types(domain) if nt not in known_node_types})
    if unknown:
        raise ValueError(
            f"도메인 '{domain.code}'가 카탈로그에 없는 node_type 참조(환각): {unknown}"
        )
    return domain


def to_bundle(domain: Domain) -> DomainGroundingBundle:
    """Domain → 소비측 번들(필수/금지 node_type 집계)."""
    req = tuple(r.node_type for r in domain.rules if r.kind == "required" and r.node_type)
    forb = tuple(r.node_type for r in domain.rules if r.kind == "forbidden" and r.node_type)
    return DomainGroundingBundle(domain=domain, required_node_types=req, forbidden_node_types=forb)
