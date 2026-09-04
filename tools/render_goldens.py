"""Regenerate the golden plans, and the refusals, that the tuning decisions are reviewed by.

A golden is one fixture host, put through the whole pipeline against one profile, with the
answer committed. It exists because a change to a sizing rule is a decision about somebody
else's production database, and the way to review such a decision is to read the diff it
makes to a plan rather than to read the arithmetic and imagine one.

Two kinds are written. A host that can carry the instance gets its plan, as JSON, exactly
as `basewright plan --json` would write it. A host that cannot gets the refusal, as text,
because refusal is a first-class outcome and a change that quietly stops refusing a host
is the change most worth noticing.

Only one field is pinned: `generated_at`, which is the one thing two identical plans
legitimately differ in. Everything else is real, `tool_version` included, so a release
moves one line in each golden and nobody has to wonder whether the artifact still says
which tool made it.

Usage:

    python tools/render_goldens.py            # write test/golden/
    python tools/render_goldens.py --check    # fail if the committed goldens are stale
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from basewright.facts import load_facts  # noqa: E402
from basewright.planner import build_plan, rendered  # noqa: E402
from basewright.preflight import evaluate  # noqa: E402
from basewright.profiles import load_profile  # noqa: E402
from basewright.report.preflight import render_preflight  # noqa: E402
from basewright.request import resolve_request  # noqa: E402

GOLDEN = ROOT / "test" / "golden"
HOSTS = ROOT / "test" / "fixtures" / "hosts"
PROFILE = ROOT / "test" / "fixtures" / "profiles" / "exampledb"

#: The moment every golden claims to have been generated at, and the date every rule that
#: reads the calendar is evaluated against. Pinned, so that the only thing a diff can show
#: is a decision that changed.
PINNED = datetime(2026, 1, 15, 9, 30, 0, tzinfo=UTC)

#: Which fixture hosts are put through the pipeline, in the order they are written.
FIXTURES: tuple[str, ...] = ("typical", "large", "rocky", "small", "crowded")


def build() -> dict[Path, str]:
    """Render every golden. Keys are paths relative to the repository root."""
    profile = load_profile(PROFILE)
    goldens: dict[Path, str] = {}

    for name in FIXTURES:
        facts = load_facts(HOSTS / f"{name}.json")
        request = resolve_request(profile, host=facts.host, environment="production")
        preflight = evaluate(facts, profile, request, today=PINNED.date(), now=PINNED)

        if preflight.blocked:
            goldens[GOLDEN / "refused" / f"{name}.txt"] = render_preflight(preflight) + "\n"
            continue

        plan = build_plan(facts, profile, request, preflight, now=PINNED)
        goldens[GOLDEN / "plan" / f"{name}.json"] = rendered(plan)

    return goldens


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="render_goldens",
        description=__doc__.split("\n")[0] if __doc__ else None,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the committed goldens with what the pipeline produces now.",
    )
    args = parser.parse_args(argv)

    goldens = build()

    if args.check:
        stale = [
            path
            for path, content in goldens.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != content
        ]
        extra = [
            path
            for directory in ("plan", "refused")
            for path in sorted((GOLDEN / directory).glob("*"))
            if path not in goldens
        ]
        for path in stale:
            print(f"stale: {path.relative_to(ROOT).as_posix()}", file=sys.stderr)
        for path in extra:
            name = path.relative_to(ROOT).as_posix()
            print(f"not produced by any fixture: {name}", file=sys.stderr)
        if stale or extra:
            print(
                "\nThe committed golden plans no longer match what the pipeline produces. "
                "If the change was intended, run tools/render_goldens.py and read the diff: "
                "it is the review of the decision, not a chore before the review.",
                file=sys.stderr,
            )
            return 1
        print(f"{len(goldens)} goldens are current.")
        return 0

    for path, content in goldens.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {len(goldens)} goldens to {GOLDEN.relative_to(ROOT).as_posix()}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
