"""Regenerate the golden plans, and the refusals, that the tuning decisions are reviewed by.

A golden is one fixture host, put through the whole pipeline against one profile, with the
answer committed. It exists because a change to a sizing rule is a decision about somebody
else's production database, and the way to review such a decision is to read the diff it
makes to a plan rather than to read the arithmetic and imagine one.

Three kinds are written. A host that can carry the instance gets its plan, as JSON,
exactly as `basewright plan --json` would write it, and the rendering of that plan, as
text, so that a change to how a plan reads is a diff like any other. A host that cannot
gets the refusal, because refusal is a first-class outcome and a change that quietly stops
refusing a host is the change most worth noticing.

A fourth is written for the other end of the loop: a verify report, in both forms, over a
committed reading of an instance this repository's own test run really provisioned. A
change to how a verdict reads is then a diff like any other too -- and unlike a plan, this
one is not derived from a fixture host, because there is no way to derive what a running
database will say. It is a reading, kept.

Two more files are written and neither is a golden. `test/fixtures/plan/edited.json` is the
first plan with a value changed and its name left alone -- a plan is named after a digest of
its own content, so that file is what a plan tampered with looks like.
`test/fixtures/observations/changed.json` is the real reading with one parameter widened,
which is what an instance somebody changed behind the plan's back looks like. Both are
generated here rather than committed by hand, because a hand-written copy falls behind the
thing it is a copy of.

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
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from basewright.facts import load_facts  # noqa: E402
from basewright.planner import build_plan, rendered  # noqa: E402
from basewright.preflight import evaluate  # noqa: E402
from basewright.profiles import load_profile  # noqa: E402
from basewright.report.plan import render_plan  # noqa: E402
from basewright.report.preflight import render_preflight  # noqa: E402
from basewright.report.verify import render_verify  # noqa: E402
from basewright.request import resolve_request  # noqa: E402
from basewright.verify import document as verification  # noqa: E402
from basewright.verify import load_observation, read_observation, verify  # noqa: E402

GOLDEN = ROOT / "test" / "golden"
HOSTS = ROOT / "test" / "fixtures" / "hosts"
EDITED = ROOT / "test" / "fixtures" / "plan" / "edited.json"

#: The other end of the loop, and the one pair of inputs in this repository that nobody
#: wrote: the plan the apply scenario built for a container, and what that container said
#: when verify read it back. Committed as they came off the run, exactly as two of the
#: fixture hosts are, so that "an instance verified is an instance like any other" is a
#: check rather than a claim.
APPLIED = ROOT / "test" / "fixtures" / "plan" / "applied.json"
OBSERVED = ROOT / "test" / "fixtures" / "observations" / "observed.json"

#: The same reading with one parameter widened, which is what an instance somebody changed
#: behind the plan's back looks like. Generated rather than committed by hand, and the
#: parameter is the one the molecule scenario really alters on the running cluster.
CHANGED = ROOT / "test" / "fixtures" / "observations" / "changed.json"
WIDENED = ("work_mem", 67108864)

#: The profiles every fixture host is put through, and the directory each one's answers
#: are written under. The two do different jobs. The fictional engine exercises the
#: pipeline and the schema without implying anything about anybody's production database;
#: the real one is where the tuning decisions live, and its diff is the review.
#: The plan the tampered fixture is made from. Named rather than taken as whichever
#: golden happens to sort first, so that adding an engine cannot silently change which
#: artifact the tamper check is exercised against.
TAMPERED_FROM = GOLDEN / "exampledb" / "plan" / "typical.json"

PROFILES: tuple[tuple[str, Path], ...] = (
    ("exampledb", ROOT / "test" / "fixtures" / "profiles" / "exampledb"),
    ("postgresql", ROOT / "profiles" / "postgresql"),
)

#: The moment every golden claims to have been generated at, and the date every rule that
#: reads the calendar is evaluated against. Pinned, so that the only thing a diff can show
#: is a decision that changed.
PINNED = datetime(2026, 1, 15, 9, 30, 0, tzinfo=UTC)

#: Which fixture hosts are put through the pipeline, in the order they are written.
FIXTURES: tuple[str, ...] = ("typical", "large", "rocky", "small", "crowded")


def build() -> dict[Path, str]:
    """Render every golden. Keys are paths relative to the repository root."""
    goldens: dict[Path, str] = {}

    for engine, directory in PROFILES:
        profile = load_profile(directory)
        under = GOLDEN / engine

        for name in FIXTURES:
            facts = load_facts(HOSTS / f"{name}.json")
            request = resolve_request(profile, host=facts.host, environment="production")
            preflight = evaluate(facts, profile, request, today=PINNED.date(), now=PINNED)

            if preflight.blocked:
                goldens[under / "refused" / f"{name}.txt"] = render_preflight(preflight) + "\n"
                continue

            plan = build_plan(facts, profile, request, preflight, now=PINNED)
            goldens[under / "plan" / f"{name}.json"] = rendered(plan)
            goldens[under / "rendered" / f"{name}.txt"] = render_plan(plan) + "\n"

    goldens[EDITED] = _tampered_with(goldens)
    goldens[CHANGED] = _widened()
    goldens.update(_verified(goldens))
    return goldens


def _widened() -> str:
    """The committed reading with one parameter changed, and nothing else touched.

    The parameter is the one the molecule scenario really widens on the running cluster, so
    the picture in the documentation and the case CI proves are the same case.
    """
    reading = json.loads(OBSERVED.read_text(encoding="utf-8"))
    name, value = WIDENED
    reading["observations"]["parameters"]["settings"][name] = value
    return json.dumps(reading, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _verified(goldens: dict[Path, str]) -> dict[Path, str]:
    """The verify report over the committed reading, and over the changed one.

    Both, because a report that only ever passes has not been shown to be looking, and the
    diff on the failing one is where a change to how a refusal reads shows up.
    """
    plan = json.loads(APPLIED.read_text(encoding="utf-8"))
    profile = load_profile(ROOT / "profiles" / plan["request"]["engine"])
    under = GOLDEN / plan["request"]["engine"] / "verified"

    written: dict[Path, str] = {}
    readings = {
        "observed": load_observation(OBSERVED),
        "changed": read_observation(json.loads(goldens[CHANGED]), CHANGED),
    }
    for name, observation in readings.items():
        result = verify(plan, profile, observation)
        document = verification(result, verified_at=PINNED)
        written[under / f"{name}.json"] = (
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        )
        written[under / f"{name}.txt"] = render_verify(result) + "\n"
    return written


def _tampered_with(goldens: dict[Path, str]) -> str:
    """The first plan, with one value changed and its name left as it was.

    Not a golden: a plan that is wrong on purpose, so that the check which notices a plan
    has been edited has something real to notice. Derived from a plan rather than written
    by hand, because a hand-written copy falls behind the thing it is a copy of.
    """
    plan = json.loads(goldens[TAMPERED_FROM])
    parameter = plan["parameters"][0]
    parameter["value"] = parameter["value"] * 2
    parameter["display"] = "somebody edited this"
    return json.dumps(plan, indent=2, ensure_ascii=True) + "\n"


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
        # Every committed artifact, however deep, rather than a list of directory names
        # that stops being the right list the moment the layout changes -- which is what
        # happened the first time a second engine was added.
        extra = [
            path
            for path in sorted(GOLDEN.rglob("*"))
            if path.is_file() and path.suffix in {".json", ".txt"} and path not in goldens
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
