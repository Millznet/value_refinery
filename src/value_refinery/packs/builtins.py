from __future__ import annotations

# Fallback builtin packs (used if YAML files are missing in a packaged install).
# Keep this small: just your defaults.

BUILTIN_PACKS = {
    "secops": {
        "id": "secops",
        "version": "0.0.1",
        "description": "Security/IT ops pack (starter)",
        "defaults": {
            "min_score": 55,
            "db_name": "secops.duckdb",
            "allowed_exts": [".md", ".txt", ".log", ".jsonl", ".csv"],
        },
        "rubric": {
            "version": "0.0.1",
            "base_score": 80,
            "rules": [
                {
                    "id": "has_steps",
                    "kind": "regex",
                    "pattern": r"(^|\n)\s*\d+\)\s+",
                    "weight": 8,
                    "reason": "structured_steps",
                },
                {
                    "id": "has_headings",
                    "kind": "regex",
                    "pattern": r"(^|\n)#{1,6}\s+",
                    "weight": 6,
                    "reason": "structured_headings",
                },
                {
                    "id": "too_link_heavy",
                    "kind": "regex_count_ge",
                    "pattern": r"https?://",
                    "threshold": 5,
                    "weight": -20,
                    "reason": "link_heavy",
                },
                {
                    "id": "boilerplate_terms",
                    "kind": "regex",
                    "pattern": r"(cookie|newsletter|subscribe)",
                    "weight": -10,
                    "reason": "boilerplate_like",
                },
            ],
        },
        "redaction": {
            "version": "0.0.1",
            "redactions": [
                {
                    "id": "email",
                    "kind": "regex",
                    "pattern": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                    "replace": "[REDACTED_EMAIL]",
                },
                {
                    "id": "ipv4",
                    "kind": "regex",
                    "pattern": r"\b(\d{1,3}\.){3}\d{1,3}\b",
                    "replace": "[REDACTED_IP]",
                },
                {
                    "id": "aws_key",
                    "kind": "regex",
                    "pattern": r"\bAKIA[0-9A-Z]{16}\b",
                    "replace": "[REDACTED_AWS_KEY]",
                },
            ],
        },
    }
}
