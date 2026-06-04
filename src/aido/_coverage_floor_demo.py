"""Intentionally-uncovered module for testing the coverage-floor gate.

DO NOT MERGE. This file exists to verify that the bootstrap-installed
diff-cover gate (CI step + pre-push hook) actually blocks PRs that fall
below the 90% new-code threshold. Every function below is unreachable
from the existing test suite by design.
"""


def shout(text: str) -> str:
    return text.upper() + "!"


def whisper(text: str) -> str:
    return "(" + text.lower() + ")"


def repeat(text: str, n: int) -> str:
    if n < 1:
        return ""
    return (text + " ") * (n - 1) + text


def sandwich(top: str, filling: str, bottom: str) -> str:
    parts = [top, filling, bottom]
    return "\n".join(part for part in parts if part)


def is_palindrome(text: str) -> bool:
    normalized = "".join(ch.lower() for ch in text if ch.isalnum())
    return normalized == normalized[::-1]
