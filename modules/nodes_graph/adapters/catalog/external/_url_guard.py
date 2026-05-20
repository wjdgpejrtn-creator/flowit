"""SSRF 방어 — external 노드가 호출하는 사용자 지정 URL 검증 (ADR-0018 Phase 3a).

워크플로우 작성자가 지정한 URL을 worker(VPC 내부, PR #90 vpc_connector)에서 httpx로
호출하므로, `169.254.169.254`(GCP metadata) · private/loopback 대역으로의 호출을
차단해 SA 토큰 탈취·내부 서비스 접근을 막는다.

hostname을 실제로 resolve해 해석된 IP를 검사하므로 IP 리터럴과 내부 IP로 해석되는
도메인을 모두 거른다. (해석 후 httpx가 재해석하는 DNS rebinding은 닫지 않는다 —
사내 신뢰 경계 + 2026-06-30 destroy 정책상 IP pinning까지는 미적용.)
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from common_schemas.exceptions import ValidationError


async def validate_outbound_url(url: str) -> None:
    """SSRF 차단 — 내부/예약 대역으로 해석되는 URL이면 `ValidationError`."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(f"URL scheme must be http or https: {url!r}")
    host = parsed.hostname
    if not host:
        raise ValidationError(f"URL has no host: {url!r}")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValidationError(f"URL host could not be resolved: {host}") from e

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local  # 169.254.0.0/16 — GCP metadata 포함
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValidationError(f"URL이 내부/예약 대역으로 해석됨 (SSRF 차단): {host} -> {ip}")
