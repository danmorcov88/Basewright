"""Substituting what a profile leaves open into what one request settles.

A profile is written once for every instance an engine will ever provision, so it names
what varies rather than repeating it. A path, a package name, a service unit and the
location of a secret are all written the same way::

    /var/lib/basewright/{{ engine }}/{{ instance }}/data
    exampledb-server-{{ version }}
    basewright/{{ host }}/{{ instance }}/admin

Substitution is all this does. There is no logic here and there is not going to be any:
every value in a plan is decided in Python, and a profile that could branch would be a
profile that decides.

Two mistakes are told apart, because they are fixed by different people. A placeholder
the vocabulary does not have is a defect in the profile: a directory called
``{{ instnace }}`` would be created without complaint by everything downstream and found
six months later. A placeholder the vocabulary does have but this host did not report is
a fact nobody collected, and the message says so rather than sending its reader to look
for a spelling mistake that is not there.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

#: ``{{ name }}`` or ``{{ group.name }}``, with any amount of space inside the braces.
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+(?:\.[a-z_]+)?)\s*\}\}")


class PlaceholderError(ValueError):
    """A template that cannot be filled in: an unknown placeholder, or an unreported one."""


def substitute(template: str, values: Mapping[str, str | None], *, noun: str) -> str:
    """Fill in every placeholder of one template.

    ``noun`` is what the template is, in words, so that the refusal names the thing being
    written rather than the function that was writing it.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            known = ", ".join(sorted(values))
            raise PlaceholderError(
                f"{template!r} uses {{{{ {name} }}}}, which is not a placeholder {noun} has. "
                f"The ones {noun} has are: {known}."
            )
        value = values[name]
        if value is None:
            raise PlaceholderError(
                f"{template!r} uses {{{{ {name} }}}}, which this host did not report. Collect "
                "it, or write the template so that it does not depend on it."
            )
        return value

    filled = _PLACEHOLDER.sub(replace, template)
    if "{{" in filled or "}}" in filled:
        raise PlaceholderError(
            f"{template!r} has a placeholder that was not closed. Write it as {{{{ name }}}}."
        )
    return filled
