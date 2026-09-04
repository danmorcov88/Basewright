"""The filters Ansible reaches Basewright through, and the whole of what it may call.

Ansible acts and Basewright decides (ADR-0008), so every question a role has to ask that
has a wrong answer is asked here. There is one function per question, each of them a thin
wrapper over a module pytest already covers, and the roles that call them stay lists of
things to do rather than places where a judgement is quietly made in Jinja.

Four questions, and each earns its place by being one a template could get wrong:

* **What did this host turn out to be?** Parsing what a machine printed.
* **Which repositories should it be asked to reach?** Reading them out of a profile.
* **Is it still the machine this plan describes?** Deciding which differences matter.
* **Where is the template this plan names?** Finding a file the plan refers to by name.

The last one is the only place anything on the applying side reads outside the plan, and
it reads a template rather than a value. Every value poured into that template comes from
the plan; what is looked up is the shape it is poured into (ADR-0022).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from basewright.drift import differences
from basewright.facts.collect import document
from basewright.facts.normalize import normalize
from basewright.facts.repositories import repositories
from basewright.profiles.locate import template_for

__all__ = ["FILTERS", "drifted", "template"]


def drifted(plan: Mapping[str, Any], collected: Mapping[str, Any]) -> list[str]:
    """Every material way a host is no longer the machine a plan was built from.

    Ansible hands over what the host reported; what counts as drift is decided in
    :mod:`basewright.drift`, under pytest. What comes back is a list of sentences to print,
    or an empty list meaning go on. A comparison written in Jinja would be a second opinion
    about what a plan says, living where nothing can test it.
    """
    observed = normalize(collected).plan_section()
    return [str(difference) for difference in differences(plan.get("host", {}), observed)]


def template(plan: Mapping[str, Any], name: str) -> str:
    """Where the configuration template a plan names actually is.

    The plan says which file, by the name the profile gave it, and the profile is where the
    file lives. Resolving that here rather than in the role means a plan naming a template
    nothing can render is refused by name, before anything on the host has been touched,
    rather than halfway through an apply on somebody else's machine.
    """
    return str(template_for(plan["profile"]["engine"], name))


#: Everything Ansible is allowed to call, and the only way in. A filter added here is a
#: question somebody decided a role may ask; anything not here is a judgement a role would
#: be making on its own.
FILTERS: Mapping[str, Callable[..., Any]] = {
    "basewright_document": document,
    "basewright_repositories": repositories,
    "basewright_drift": drifted,
    "basewright_template": template,
}
