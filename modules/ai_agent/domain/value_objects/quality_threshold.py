from __future__ import annotations


class QualityThreshold:
    MIN_SCORE = 8.0

    def is_pass(self, score: float) -> bool:
        return score >= self.MIN_SCORE
