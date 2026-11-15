"""Audit the exact Git index before publishing PDFManipulator.

Prints only file names and finding categories; never echoes secret values.
Also checks that build outputs, private PDFs, local sessions and venvs
are absent from the staged snapshot. Run after git add.
"""
from __future__ import annotations

import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DISALLOWED_SUFFIXES = {
    ".pdf", ".exe", ".dll", ".dpapi", ".pem", ".pfx", ".p12",
    ".key", ".sqlite", ".sqlite3", ".db", ".env", ".log", ".bak",
}
DISALLOWED_NAMES = {
    "host.json", "recipes.json", "token.json", "secrets.json",
    "credentials.json", ".env", "accounts.dpapi",
}
BLOCKED_DIRS = {
    ".venv", "venv", "build", "dist", ".git", "__pycache__",
    ".idea", ".vscode", "node_modules",
}
PATTERNS = {
    "OpenAI or Anthropic secret key": re.compile(rb"\bsk-(?:ant-)?[A-Za-z0-9_-]{18,}"),
    "GitHub access token": re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{28,}|github_pat_[A-Za-z0-9_]{40,}"),
    "GitLab token": re.compile(rb"\bglpat-[A-Za-z0-9_-]{18,}"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "Slack token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{18,}"),
    "Stripe secret key": re.compile(rb"\bsk_(?:live|test)_[A-Za-z0-9]{18,}"),
    "private key material": re.compile(rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "password inside URL": re.compile(rb"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|https?)://[^\s:@/]{1,64}:[^\s@/]{5,}@"),
    "personal Windows user path": re.compile(rb"(?i)\b[A-Z]:\\Users\\(?!Public\\|Default\\)[^\\/\r\n]{2,}\\"),
}
MAX_TEXT_BYTES = 10 * 1024 * 1024

def run(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def staged_paths() -> list[str]:
    return [p.decode("utf-8") for p in run("ls-files", "--cached", "-z").split(b"\0") if p]


def inspect(paths: list[str]) -> list[str]:
    findings: list[str] = []
    if not paths:
        return ["Git index contains no files."]
    for name in paths:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            findings.append(f"{name}: unsafe path")
            continue
        if set(path.parts) & BLOCKED_DIRS or path.name.lower() in DISALLOWED_NAMES:
            findings.append(f"{name}: private/local generated file is staged")
            continue
        if path.suffix.lower() in DISALLOWED_SUFFIXES or path.name.startswith(".env."):
            findings.append(f"{name}: forbidden file type staged")
            continue
        file = ROOT / path
        if file.stat().st_size > MAX_TEXT_BYTES:
            findings.append(f"{name}: unexpectedly large source file")
            continue
        content = file.read_bytes()
        if b"\x00" in content[:4096] and file.suffix.lower() not in {".ico", ".png", ".jpg", ".jpeg"}:
            findings.append(f"{name}: unexpected binary file")
            continue
        if path.suffix.lower() in {".ico", ".png", ".jpg", ".jpeg"}:
            if not path.as_posix().startswith("packaging/"):
                findings.append(f"{name}: unreviewed binary asset")
            continue
        for category, expression in PATTERNS.items():
            match = expression.search(content)
            if match:
                line_number = content.count(b"\n", 0, match.start()) + 1
                findings.append(f"{name}:{line_number}: {category}")
    return findings


def main() -> int:
    try:
        paths = staged_paths()
        issues = inspect(paths)
    except (subprocess.CalledProcessError, OSError, UnicodeError):
        print("Audit could not inspect the Git index.", file=sys.stderr)
        return 2
    if issues:
        print("BLOCKED: review the following findings (secret values not shown):", file=sys.stderr)
        for line in issues:
            print(" - " + line, file=sys.stderr)
        return 1
    print(f"PASS: {len(paths)} staged files reviewed; no flagged secrets or private file types.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
