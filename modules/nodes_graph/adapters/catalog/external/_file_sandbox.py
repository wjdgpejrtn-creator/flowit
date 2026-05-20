"""file 노드 경로 샌드박스 — 워커 로컬 FS의 임의 경로 접근(LFI) 차단 (ADR-0018 Phase 3d).

file_read/write/transform가 다루는 사용자 지정 경로를 `NODE_FILE_BASE_DIR`
(기본 `/tmp/workflow_files`) 하위로 제한한다. 절대 경로·`..` 탈출 모두 차단해
워커의 비밀(ENCRYPTION_KEY 등)·SA 파일을 워크플로 작성자가 읽지 못하게 한다.

워커는 ephemeral container라 이 디렉토리의 파일은 워크플로 실행 1회 범위의
scratch로만 유효하다 (실행 종료/스케일 시 소실).
"""
from __future__ import annotations

import os
from pathlib import Path

from common_schemas.exceptions import ValidationError


def base_dir() -> Path:
    return Path(os.getenv("NODE_FILE_BASE_DIR", "/tmp/workflow_files")).resolve()


def resolve_sandboxed_path(path: str) -> Path:
    """user 지정 path를 샌드박스 base 디렉토리 안으로 제한. 탈출 시 `ValidationError`."""
    base = base_dir()
    # 절대 경로는 base 밖으로 탈출하므로 leading separator를 제거해 항상 상대 취급.
    candidate = (base / path.lstrip("/\\")).resolve()
    if candidate != base and not candidate.is_relative_to(base):
        raise ValidationError(f"file 경로가 샌드박스 디렉토리를 벗어남: {path!r}")
    return candidate
