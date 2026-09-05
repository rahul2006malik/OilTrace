"""
SIH26143 — Attribution subsystem
Single source of truth for where cache/capture files live on disk.

WHY THIS FILE EXISTS
---------------------
Two independent "find the project root" heuristics had appeared —
`gfw_client._find_default_cache_dir()` and `aisstream_client._find_capture_dir()`
— each walking up from `__file__` and guessing project root by checking
whether `data/cache` (or `data/raw`) *already exists* alongside a sibling
`docs/` folder. That's backwards: it requires the directory to exist before
it can find where the directory should be, and `data/raw/` is gitignored
(PROJECT_STATE.md), so a fresh clone never has it pre-created. On a fresh
clone or CI box, both heuristics silently fall through to a CWD-relative
path — exactly the split-cache bug they were written to prevent, just moved
earlier in the project's lifecycle where it's harder to notice.

The actual repo layout is fixed and documented (Execution doc, Section 1):
    <project_root>/{detection,drift,attribution,backend,frontend,data,notebooks,docs}
`attribution/` is always exactly one level under project root — that's not
a guess, it's the whole point of the documented structure. So project root
is unconditionally `Path(__file__).resolve().parent.parent` from this file,
no existence checks, no fallback path that silently means something
different from what the caller asked for.

Every module that reads/writes data/cache or data/raw/aisstream_capture
should import from here, not roll its own resolver.
"""

from __future__ import annotations

from pathlib import Path

# This file lives at <project_root>/attribution/project_paths.py.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
AISSTREAM_CAPTURE_DIR = DATA_DIR / "raw" / "aisstream_capture"

# Sanity check, cheap and import-time-only: warn (don't crash) if the
# resolved root doesn't look like this project, so a genuinely unusual
# deployment layout is visible immediately rather than causing a mysterious
# empty-cache bug three files away.
_expected_siblings = {"detection", "drift", "backend", "frontend"}
_actual_siblings = {p.name for p in PROJECT_ROOT.iterdir()} if PROJECT_ROOT.exists() else set()
if _actual_siblings and not (_expected_siblings & _actual_siblings):
    import warnings
    warnings.warn(
        f"project_paths.PROJECT_ROOT resolved to {PROJECT_ROOT}, which doesn't "
        f"contain any of the expected sibling directories {_expected_siblings}. "
        "If attribution/ has been moved or nested differently than the "
        "documented repo layout, cache/capture paths below may be wrong — "
        "check PROJECT_ROOT manually.",
        stacklevel=2,
    )
