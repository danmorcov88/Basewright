"""The filters Ansible reaches Basewright through, and the whole of what it may call.

Ansible acts and Basewright decides (ADR-0008), so every question a role has to ask that
has a wrong answer is asked here. There is one function per question, each of them a thin
wrapper over a module pytest already covers, and the roles that call them stay lists of
things to do rather than places where a judgement is quietly made in Jinja.

Six questions, and each earns its place by being one a template could get wrong:

* **What did this host turn out to be?** Parsing what a machine printed.
* **Which repositories should it be asked to reach?** Reading them out of a profile.
* **Is it still the machine this plan describes?** Deciding which differences matter.
* **Where is the template this plan names?** Finding a file the plan refers to by name.
* **What did this instance turn out to be?** Putting the envelope round a reading.
* **Which sockets is this process holding?** Parsing what ``ss`` printed.
* **Where does this instance's pointer go in the store?** Building a path from a plan.

The template one is the only place anything on the applying side reads outside the plan,
and it reads a template rather than a value. Every value poured into that template comes
from the plan; what is looked up is the shape it is poured into (ADR-0022).

The two before it are verify's, and neither knows an engine. The role that calls them does:
it is the one that read its own instance and turned what it said into the contract's terms,
and it is the one that knows what its own process is called (ADR-0024).

The last is apply's, and it is where the split is easiest to see: this decides the path and
Ansible writes the file. Every part of that path comes from a name somebody typed into a
survey field, so deciding it is a question with a wrong answer -- and writing a line into a
file is not.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from basewright.drift import differences
from basewright.facts.collect import document
from basewright.facts.normalize import normalize
from basewright.facts.repositories import repositories
from basewright.profiles.locate import template_for
from basewright.store import instance_path
from basewright.verify.collect import observation, sockets_held

__all__ = ["FILTERS", "drifted", "pointer", "template"]


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


def pointer(plan: Mapping[str, Any], store: str) -> str:
    """Where the store keeps the note saying which plan this instance is running.

    The host and the instance come out of the plan rather than being passed in, because
    apply reads the plan and nothing else -- and because a pointer written under a name the
    plan does not use would be a pointer verify never finds.

    Only the path. Writing the file is the playbook's, which is the whole arrangement: a
    path assembled out of typed-in names is a question somebody can get wrong, and the write
    that follows is not.
    """
    return str(instance_path(Path(store), plan["request"]["host"], plan["request"]["instance"]))


#: Everything Ansible is allowed to call, and the only way in. A filter added here is a
#: question somebody decided a role may ask; anything not here is a judgement a role would
#: be making on its own.
FILTERS: Mapping[str, Callable[..., Any]] = {
    "basewright_document": document,
    "basewright_repositories": repositories,
    "basewright_drift": drifted,
    "basewright_template": template,
    "basewright_observation": observation,
    "basewright_sockets": sockets_held,
    "basewright_pointer": pointer,
}
