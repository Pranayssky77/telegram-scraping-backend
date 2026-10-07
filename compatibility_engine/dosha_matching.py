from __future__ import annotations


class DoshaMatcher:
    def score(self, source_dosha: dict, candidate_dosha: dict) -> dict:
        source_has = bool(source_dosha["has_kuja_dosha"]) and not bool(source_dosha.get("is_cancelled"))
        candidate_has = bool(candidate_dosha["has_kuja_dosha"]) and not bool(candidate_dosha.get("is_cancelled"))
        if source_has == candidate_has:
            return {"score": 100.0, "reason": "Kuja/Manglik dosha status is compatible"}
        source_severity = int(source_dosha.get("adjusted_severity", source_dosha["severity"]))
        candidate_severity = int(candidate_dosha.get("adjusted_severity", candidate_dosha["severity"]))
        severity_gap = abs(source_severity - candidate_severity)
        return {
            "score": max(20.0, 60.0 - severity_gap * 20.0),
            "reason": "Kuja/Manglik dosha mismatch",
        }
