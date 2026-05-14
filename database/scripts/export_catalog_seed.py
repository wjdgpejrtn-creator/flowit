"""박아름 카탈로그 → database/seeds/node_definitions.json 추출.

조장 5/13 합의: placeholder seed는 박아름 노드 카탈로그를 따라간다.
본 스크립트로 박아름 55종 카탈로그를 JSON으로 추출 + seed 파일 갱신.

embedding은 런타임 생성 필요 (BGE-M3 모델) → JSON에는 포함 안 함.
bootstrap_node_definitions.py가 embedding 채우는 역할.

사용:
    PYTHONUTF8=1 python database/scripts/export_catalog_seed.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# PYTHONPATH 보강
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for p in (
    _REPO_ROOT / "modules",
    _REPO_ROOT / "packages" / "common_schemas" / "python",
):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def main() -> int:
    from nodes_graph.application.catalog_registry import get_all_node_definitions

    nodes = get_all_node_definitions()
    print(f"[INFO] 카탈로그 발견: {len(nodes)}종")

    # NodeDefinition → JSON dict 변환 (embedding 제외, 009 스키마 정합)
    items = []
    for n in nodes:
        items.append({
            "node_type": n.node_type,
            "name": n.name,
            "category": n.category,
            "version": n.version,
            "input_schema": n.input_schema,
            "output_schema": n.output_schema,
            "parameter_schema": n.parameter_schema,
            "risk_level": n.risk_level.value if hasattr(n.risk_level, "value") else str(n.risk_level),
            "required_connections": list(n.required_connections),
            "description": n.description,
            "is_mvp": n.is_mvp,
            "service_type": n.service_type,
        })

    # category 분포 출력
    from collections import Counter
    by_cat = Counter(item["category"] for item in items)
    print(f"[INFO] category 분포:")
    for cat, cnt in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat:15s}: {cnt}")

    # JSON 직렬화 + seed 파일 덮어쓰기
    seed_file = _REPO_ROOT / "database" / "seeds" / "node_definitions.json"
    seed_file.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] {seed_file} ({len(items)}종, {seed_file.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
