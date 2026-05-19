from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.scan_result import ScanResult


class VirusScanPort(ABC):
    @abstractmethod
    async def scan(self, data: bytes) -> ScanResult: ...
