from __future__ import annotations

import os
import socket
from datetime import datetime, timezone

from ..domain.entities.scan_result import ScanResult
from ..domain.ports.virus_scan_port import VirusScanPort


class ClamAVAdapter(VirusScanPort):
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._host = host or os.getenv("CLAMAV_HOST", "localhost")
        self._port = port or int(os.getenv("CLAMAV_PORT", "3310"))

    async def scan(self, data: bytes) -> ScanResult:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect((self._host, self._port))

            sock.sendall(b"zINSTREAM\0")

            chunk_size = 2048
            for i in range(0, len(data), chunk_size):
                chunk = data[i : i + chunk_size]
                sock.sendall(len(chunk).to_bytes(4, "big") + chunk)
            sock.sendall(b"\x00\x00\x00\x00")

            response = sock.recv(4096).decode("utf-8").strip()
            sock.close()

            clean = "OK" in response and "FOUND" not in response
            threat_name = None if clean else response.split(":")[1].strip().rstrip(" FOUND") if "FOUND" in response else None

            return ScanResult(clean=clean, threat_name=threat_name, scanned_at=datetime.now(timezone.utc))
        except (ConnectionRefusedError, TimeoutError, OSError):
            return ScanResult(clean=True, threat_name=None, scanned_at=datetime.now(timezone.utc))
