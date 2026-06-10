from __future__ import annotations

from dataclasses import dataclass

from ..value_objects.skeleton import AssembledDraft, DraftNode, SlotRole

# 조립된 스켈레톤(AssembledDraft) → 스킬 게시 산출물 매퍼 (ADR-0028 T5 `assemble_skill`).
#
# 배경(§6.6/#416): soft 모티프 힌트는 작은 LLM의 구조 출력을 못 바꾼다 → 구조는 코드가
# 결정적으로 조립하고 LLM은 파라미터/설명만 채운다. 본 매퍼는 그 결정적 조립 결과
# (`SkeletonAssembler.assemble`의 순수 node_type 구조)를 스킬의 두 산출물로 옮긴다:
#   ① COMPOSER.md 본문 — "이 스킬을 쓰려면 어떤 노드를 어떻게 엮어야 하는가"(ADR-0024 2-md).
#      Composer drafter가 워크플로우 생성 시 주입받는 결정적 배선 지침(#372 결함 A 해소).
#   ② 정밀 BINDS — 스캐폴드에 실제로 등장한 node_type 집합(ADR-0028 D4). 현 coarse BINDS
#      (모든 ai 노드 + connection 노드)를 스켈레톤 유래 실노드로 정밀화하기 위한 원천.
#
# 순수 도메인 서비스 — I/O·LLM·Neo4j 의존 없음. assembler 출력만 소비하므로 단위테스트로
# 전수 검증한다. assembler에 skill 전용 메서드를 더하지 않고 어댑팅을 빌더 쪽에서 한다는
# O4(신정혜 RESOLVED) 합의의 "빌더 쪽 어댑팅" 지점이 바로 이 매퍼다.

# 역할 → COMPOSER.md 한글 설명. Composer가 각 슬롯의 의미를 이해하도록 SlotRole을 풀어 쓴다.
_ROLE_LABEL: dict[SlotRole, str] = {
    SlotRole.TRIGGER: "발동 — 워크플로우 진입점",
    SlotRole.SOURCE: "데이터 읽기·수집",
    SlotRole.TRANSFORM: "AI/LLM 가공",
    SlotRole.SCORER: "생성물 채점 (품질 점수화)",
    SlotRole.SINK: "내보내는 채널",
    SlotRole.GATE: "품질 검증 게이트 (재생성 루프)",
    SlotRole.ROUTER: "조건 분기 (XOR)",
    SlotRole.SPLITTER: "병렬 분할",
    SlotRole.MERGER: "병렬 합류",
    SlotRole.DELAY: "백오프 대기 (재시도)",
    SlotRole.TERMINAL: "종료",
}

# 조건 분기 엣지 핸들 → 한글 주석. 기본 핸들(output/input)은 주석 생략.
_HANDLE_LABEL: dict[str, str] = {
    "true": "조건 충족",
    "false": "조건 미충족",
}


@dataclass(frozen=True)
class SkillSkeletonMapping:
    """T5 산출 — AssembledDraft를 스킬 게시 산출물로 매핑한 결과 (ADR-0028 D2/D4).

    Attributes:
        skeleton_name: 조립에 쓰인 스켈레톤 이름(관측·디버깅용).
        composer_instructions: COMPOSER.md 본문(결정적). 스켈레톤 매칭 시 LLM 자유추출을 대체.
        bound_node_types: 스캐폴드에 등장한 node_type을 등장 순·중복 제거로 나열 — 정밀 BINDS 원천.
    """

    skeleton_name: str
    composer_instructions: str
    bound_node_types: tuple[str, ...]


class SkeletonComposerMapper:
    """조립된 스켈레톤(AssembledDraft)을 스킬의 COMPOSER.md + 정밀 BINDS로 매핑 (ADR-0028 T5).

    `SkeletonAssembler.assemble`가 반환한 `AssembledDraft`(순수 node_type 구조)만 받는다 —
    `WorkflowSchema` 변환(`to_workflow_schema`, node_id 해소)은 composer 몫이라 빌더는 쓰지
    않는다(D2). 빌더는 구조를 "사람·Composer가 읽는 지침서"로 옮길 뿐이다.
    """

    def map(self, draft: AssembledDraft) -> SkillSkeletonMapping:
        return SkillSkeletonMapping(
            skeleton_name=draft.skeleton_name,
            composer_instructions=self._to_composer_markdown(draft),
            bound_node_types=self._bound_node_types(draft.nodes),
        )

    @staticmethod
    def _bound_node_types(nodes: tuple[DraftNode, ...]) -> tuple[str, ...]:
        """스캐폴드 노드의 node_type을 등장 순으로 중복 제거(정밀 BINDS 대상 집합)."""
        seen: dict[str, None] = {}
        for n in nodes:
            seen.setdefault(n.node_type, None)
        return tuple(seen)

    @staticmethod
    def _to_composer_markdown(draft: AssembledDraft) -> str:
        """AssembledDraft를 COMPOSER.md 본문(필수 노드 목록 + 연결 배선)으로 직렬화."""
        # 같은 node_type이 여러 슬롯에 들어가면(예: 복수 sink) 연결 줄에서 ref로 구분.
        type_counts: dict[str, int] = {}
        for n in draft.nodes:
            type_counts[n.node_type] = type_counts.get(n.node_type, 0) + 1
        ref_to_node: dict[str, DraftNode] = {n.ref: n for n in draft.nodes}

        def render(ref: str) -> str:
            node = ref_to_node.get(ref)
            if node is None:
                return f"`{ref}`"
            if type_counts.get(node.node_type, 0) > 1:
                return f"`{node.node_type}`({node.ref})"
            return f"`{node.node_type}`"

        lines: list[str] = ["## 필수 노드"]
        lines.append(
            f"이 스킬을 워크플로우에 쓰려면 다음 노드를 배치한다 "
            f"(결정적 스켈레톤: `{draft.skeleton_name}`):"
        )
        lines.append("")
        for i, n in enumerate(draft.nodes, start=1):
            label = _ROLE_LABEL.get(n.role, n.role.value)
            lines.append(f"{i}. `{n.node_type}` ({n.role.value}) — {label}")

        lines.append("")
        lines.append("## 연결")
        if draft.edges:
            for e in draft.edges:
                handle = _HANDLE_LABEL.get(e.from_handle)
                suffix = f" [{handle}]" if handle else ""
                lines.append(f"- {render(e.from_ref)} → {render(e.to_ref)}{suffix}")
        else:
            lines.append("- (단일 노드 — 연결 없음)")

        if draft.warnings:
            lines.append("")
            lines.append("## 주의")
            for w in draft.warnings:
                lines.append(f"- {w}")

        return "\n".join(lines)
