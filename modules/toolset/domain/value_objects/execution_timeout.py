from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionTimeout:
    seconds: int

    DEFAULT: int = 30
    MAX: int = 300

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValueError(f"Timeout must be positive, got {self.seconds}")
        if self.seconds > self.MAX:
            raise ValueError(f"Timeout {self.seconds}s exceeds MAX {self.MAX}s")
