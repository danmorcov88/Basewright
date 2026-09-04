"""Which package repositories a host should be asked about, and how the answer is read.

Every other fact a collector gathers is a question about the machine alone: how much
memory, which mounts, what is listening. This one is not. Whether a host can reach the
place its packages would come from depends on where they would come from, and that is
written in a profile -- so the collector has to be told what is being provisioned before
it can ask (ADR-0021).

That is the whole of the awkwardness, and it is contained here. The collecting role stays
what it was: it enumerates and reports, and every judgement lives in Python where pytest
can reach it. What the role gains is one optional input, and a host collected without it
reports no repositories at all -- which is the correct answer rather than a gap, because
nobody asked.

Only the repository a rule actually compares is probed. The signing key has a url too and
it is deliberately left alone: a fact no rule consults is a fact that rots quietly, and
the one rule reading this compares the repository url exactly as the profile spells it.
"""

from __future__ import annotations

from pathlib import Path

from basewright.facts.model import HostFacts
from basewright.facts.normalize import normalize
from basewright.placeholders import substitute
from basewright.profiles.loader import load_profile
from basewright.profiles.locate import directory_for
from basewright.profiles.model import Profile

__all__ = ["RepositoryQuestionError", "repositories", "urls_for"]


class RepositoryQuestionError(ValueError):
    """The collector was asked which repositories to try, without being told whose."""


def urls_for(facts: HostFacts, profile: Profile, *, version: str | None = None) -> list[str]:
    """The repository urls this host would install from, spelled as the profile spells them.

    Spelled identically on purpose. The rule that reads the answer compares urls exactly
    rather than approximately, because two urls differing by a trailing slash are two
    different claims about what was proved, and the only thing worse than an unanswered
    question here is an answer nobody can trust.

    A profile with no packages for this host's operating system family, or one whose
    packages come from repositories the host already has, leaves nothing to ask about.
    That is not a refusal: the gate reading the answer decides it has nothing to decide,
    and it does so before it ever looks at this fact.
    """
    packages = profile.packages_for(facts.os.family)
    if packages is None or packages.repository is None:
        return []

    values = _vocabulary(facts, profile, version)
    return [substitute(packages.repository.url, values, noun="a repository url")]


def repositories(
    document: object,
    *,
    engine: str | None = None,
    profile: str | None = None,
    version: str | None = None,
) -> list[str]:
    """The bridge the collecting role reaches this module through.

    Takes an engine to look up or a profile directory to read, exactly as the command line
    does, so an operator who has learned one has learned the other. The document is read
    through the same contract every rule is written against, so a url is filled in from a
    host the core would recognise rather than from whatever the role happened to assemble.
    """
    if (engine is None) == (profile is None):
        raise RepositoryQuestionError(
            "Which repositories a host should be asked about comes from a profile, so "
            "exactly one of an engine name and a profile directory is needed. Collecting "
            "without either is allowed, and reports no repositories at all: the correct "
            "answer to a question nobody put."
        )
    directory = directory_for(engine) if engine is not None else Path(str(profile))
    return urls_for(normalize(document), load_profile(directory), version=version)


def _vocabulary(facts: HostFacts, profile: Profile, version: str | None) -> dict[str, str | None]:
    """Every name a repository url may leave open, at the one moment it can be filled in.

    Deliberately narrower than the vocabulary a plan resolves. Collecting happens before a
    request exists, so a url reaching for something only a request settles -- the
    environment it is being built for -- is refused, and the refusal names what a url does
    have. The alternative is a profile whose repository is one url while it is being
    probed and another while it is being installed from, and a fact compared against a url
    nobody ever tried.
    """
    return {
        "engine": profile.engine,
        "instance": profile.default_instance,
        "version": version or profile.default_version,
        "host": facts.host,
        "os.family": facts.os.family,
        "os.distro": facts.os.distro,
        "os.version": facts.os.version,
        "os.major": facts.os.major,
        "os.codename": facts.os.codename,
    }
