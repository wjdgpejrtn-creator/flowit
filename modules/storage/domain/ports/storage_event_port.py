from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.storage_event import StorageEvent


class StorageEventPort(ABC):
    @abstractmethod
    async def emit(self, event: StorageEvent) -> None: ...
