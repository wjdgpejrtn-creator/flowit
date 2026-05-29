from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class ExecutionTimeout:
    seconds: int
    DEFAULT: ClassVar[int] = 30
    MAX: ClassVar[int] = 300

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValueError(f"Timeout must be positive, got {self.seconds}")
        if self.seconds > ExecutionTimeout.MAX:
            raise ValueError(f"Timeout {self.seconds}s exceeds MAX {ExecutionTimeout.MAX}s")
