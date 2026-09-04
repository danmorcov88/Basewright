"""A small expression language, and a reader for it that cannot run anything.

Rules and sizing formulas are written by whoever knows the engine, in a file the core
loads at run time. They have to be readable by a reviewer who is not a programmer, and
they must not be able to do anything to the machine reading them:

    host.memory.total_bytes >= 2 * GiB
    1.1 if not path.data.rotational else 4.0
    (0.25 * host.memory.total_bytes) / (max_connections * 2)

``eval`` would run whatever it was handed. A template language would put the deciding in
the templates, which is the split this project exists to keep. So the syntax is borrowed
from Python -- parsed by :mod:`ast`, which brings a tested tokenizer, the precedence
everyone already expects, and a column number for every error message -- and the meaning
is supplied here, by a walk over an allowlist of node types.

Nothing is compiled and nothing is executed. A call, a subscript, a lambda, a
comprehension, an f-string or a name beginning with an underscore is refused when the
expression is read, at the column it appears at. Names resolve through nested mappings of
plain values rather than through :func:`getattr`, so an expression never holds an object
of ours and the usual walk from an attribute to the interpreter has nothing to start from.

Two failures are deliberately different, because they mean different things:

* An expression that mentions something the vocabulary does not define is **wrong**, and
  raises. A misspelled fact is a defect in the profile, not a host that fell short.
* An expression that reads a fact the vocabulary defines but the host did not report is
  **undecidable**, and raises :class:`Unreported`. The caller turns that into a skipped
  rule, which is a reportable outcome rather than a guess.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from basewright.units import UNITS

__all__ = [
    "UNREPORTED",
    "Expression",
    "ExpressionError",
    "Unreported",
    "base_scope",
]


class _Unreported:
    """A fact the vocabulary defines that this host did not report.

    A single instance stands in for every such value, so that a scope always has the
    same shape whatever a collector managed to answer. Reading one is not an error; it
    is the reason a rule reports ``skip``.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNREPORTED"


#: The marker for a fact that was not collected. Compared by identity, never by value.
UNREPORTED: Final = _Unreported()

#: What an expression is allowed to hold. Deliberately small: no objects of ours ever
#: enter an expression, so there is nothing in one to walk out of.
Value = bool | int | float | str | tuple[Any, ...] | None | _Unreported

#: A vocabulary: names, and mappings of names, down to values.
Scope = Mapping[str, Any]


class ExpressionError(ValueError):
    """An expression that cannot be read, or that asks for something undefined.

    Always a defect in the document the expression came from, which is why the message
    carries the column: it is read by the person editing that file.
    """

    def __init__(self, message: str, *, column: int | None = None) -> None:
        self.column = column
        self.detail = message
        super().__init__(message if column is None else f"column {column}: {message}")


class Unreported(Exception):  # noqa: N818 - not an error; see the docstring
    """An expression read a fact the host did not report.

    Not an error. It is the difference between "this host falls short" and "nobody can
    tell", and the two are reported differently.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"{name} was not reported by this host")


#: The operators arithmetic is allowed to use. Exponentiation is absent on purpose: it is
#: the one operator whose cost is not bounded by the length of the expression.
_BINARY: Final[dict[type[ast.operator], str]] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
}

_COMPARE: Final[tuple[type[ast.cmpop], ...]] = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)

#: What a construct is called in the refusal, so the message names what was written
#: rather than the class the parser produced.
_CONSTRUCT: Final[dict[type[ast.AST], str]] = {
    ast.Call: "a function call",
    ast.Subscript: "a subscript",
    ast.Lambda: "a lambda",
    ast.ListComp: "a comprehension",
    ast.SetComp: "a comprehension",
    ast.DictComp: "a comprehension",
    ast.GeneratorExp: "a generator",
    ast.JoinedStr: "a formatted string",
    ast.Dict: "a dict literal",
    ast.Set: "a set literal",
    ast.Starred: "unpacking",
    ast.NamedExpr: "an assignment",
    ast.Await: "await",
    ast.Slice: "a slice",
}


def base_scope() -> dict[str, Any]:
    """The names every expression has, whatever it is being evaluated about.

    The unit constants are here so that a threshold can be written the way it is spoken:
    ``2 * GiB`` rather than 2147483648, which nobody checks. ``none`` is the value an
    unset fact compares against, spelled in lower case to match the documents these
    expressions are written in.
    """
    scope: dict[str, Any] = dict(UNITS)
    scope["none"] = None
    return scope


@dataclass(frozen=True)
class Expression:
    """One expression, read once and evaluated many times.

    Parsing is where every syntactic decision is made, so an expression that exists at
    all is one whose every node is understood. Evaluation only has to resolve names and
    apply operators.
    """

    source: str
    tree: ast.expr

    @classmethod
    def parse(cls, source: str) -> Expression:
        """Read an expression, refusing anything outside the language.

        Raises :class:`ExpressionError` naming the construct and the column, which is
        what a profile author needs in order to fix it in one edit.
        """
        try:
            parsed = ast.parse(source.strip(), mode="eval")
        except SyntaxError as error:
            column = error.offset
            raise ExpressionError(
                f"{source.strip()!r} is not a readable expression: {error.msg}",
                column=column,
            ) from error

        _check(parsed.body)
        return cls(source=source.strip(), tree=parsed.body)

    def names(self) -> frozenset[str]:
        """The root names the expression reads. Used to explain what a rule depends on."""
        found = {node.id for node in ast.walk(self.tree) if isinstance(node, ast.Name)}
        return frozenset(found)

    def evaluate(self, scope: Scope) -> Any:
        """Work out what the expression says about one scope.

        Raises :class:`Unreported` when it reads a fact the host did not report, and
        :class:`ExpressionError` when it asks for something the scope does not define at
        all -- a misspelling, in other words, which must not pass for a missing fact.
        """
        return _evaluate(self.tree, scope)

    def truth(self, scope: Scope) -> bool:
        """Evaluate, and insist the answer is a yes or a no.

        A rule whose expression returns a number has been written as a sizing formula by
        mistake, and saying so is more useful than quietly calling 0 false.
        """
        value = self.evaluate(scope)
        if not isinstance(value, bool):
            raise ExpressionError(
                f"{self.source!r} evaluates to {_name_of(value)}, not a yes or a no. A rule "
                "asks a question about a host; write a comparison."
            )
        return value

    def __str__(self) -> str:
        return self.source


# --------------------------------------------------------------------------- parsing


def _check(node: ast.expr) -> None:
    """Refuse every construct outside the language, deepest first."""
    construct = _CONSTRUCT.get(type(node))
    if construct is not None:
        raise ExpressionError(
            f"{construct} is not part of this language. Expressions read facts and "
            "compare them; they do not call, index or build anything.",
            column=_column(node),
        )

    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise ExpressionError(
                f"{node.attr!r} is not a name this language reads. Names beginning with an "
                "underscore are not part of the vocabulary.",
                column=_column(node),
            )
        _check(node.value)
        return

    if isinstance(node, ast.Name):
        if node.id.startswith("_"):
            raise ExpressionError(
                f"{node.id!r} is not a name this language reads. Names beginning with an "
                "underscore are not part of the vocabulary.",
                column=_column(node),
            )
        return

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool | int | float | str) or node.value is None:
            return
        raise ExpressionError(
            f"{node.value!r} is not a value this language holds.", column=_column(node)
        )

    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINARY:
            raise ExpressionError(
                f"{_operator(node.op)} is not an operator this language has. Arithmetic is "
                f"{', '.join(_BINARY.values())}.",
                column=_column(node),
            )
        _check(node.left)
        _check(node.right)
        return

    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ast.USub | ast.UAdd | ast.Not):
            raise ExpressionError(
                f"{_operator(node.op)} is not an operator this language has.",
                column=_column(node),
            )
        _check(node.operand)
        return

    if isinstance(node, ast.BoolOp):
        for value in node.values:
            _check(value)
        return

    if isinstance(node, ast.Compare):
        for operator in node.ops:
            if not isinstance(operator, _COMPARE):
                raise ExpressionError(
                    f"{_operator(operator)} is not a comparison this language has.",
                    column=_column(node),
                )
        _check(node.left)
        for comparator in node.comparators:
            _check(comparator)
        return

    if isinstance(node, ast.IfExp):
        _check(node.test)
        _check(node.body)
        _check(node.orelse)
        return

    if isinstance(node, ast.Tuple | ast.List):
        for element in node.elts:
            _check(element)
        return

    raise ExpressionError(
        f"{type(node).__name__} is not part of this language.", column=_column(node)
    )


def _column(node: ast.expr | ast.operator | ast.unaryop | ast.cmpop) -> int | None:
    return getattr(node, "col_offset", None)


def _operator(node: ast.AST) -> str:
    return type(node).__name__


# ------------------------------------------------------------------------ evaluating


def _evaluate(node: ast.expr, scope: Scope) -> Any:
    """Apply one node. Every node here survived :func:`_check`."""
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        return _resolve(scope, node.id, node.id)

    if isinstance(node, ast.Attribute):
        container = _evaluate(node.value, scope)
        path = f"{_render(node.value)}.{node.attr}"
        if not isinstance(container, Mapping):
            raise ExpressionError(
                f"{_render(node.value)} is {_name_of(container)}, so it has no {node.attr!r}."
            )
        return _resolve(container, node.attr, path)

    if isinstance(node, ast.BinOp):
        return _arithmetic(node, scope)

    if isinstance(node, ast.UnaryOp):
        return _unary(node, scope)

    if isinstance(node, ast.BoolOp):
        return _boolean(node, scope)

    if isinstance(node, ast.Compare):
        return _comparison(node, scope)

    if isinstance(node, ast.IfExp):
        chosen = node.body if _truthy(_evaluate(node.test, scope)) else node.orelse
        return _evaluate(chosen, scope)

    if isinstance(node, ast.Tuple | ast.List):
        return tuple(_evaluate(element, scope) for element in node.elts)

    raise ExpressionError(f"{type(node).__name__} is not part of this language.")


def _resolve(scope: Scope, name: str, path: str) -> Any:
    """Look one name up, telling a misspelling apart from a fact nobody collected."""
    if name not in scope:
        known = ", ".join(sorted(key for key in scope if not key.startswith("_")))
        raise ExpressionError(f"{path!r} is not something this reads. Available here: {known}.")
    value = scope[name]
    if value is UNREPORTED:
        raise Unreported(path)
    return value


def _arithmetic(node: ast.BinOp, scope: Scope) -> int | float:
    left = _number(_evaluate(node.left, scope), node)
    right = _number(_evaluate(node.right, scope), node)
    symbol = _BINARY[type(node.op)]

    if symbol in {"/", "//", "%"} and right == 0:
        raise ExpressionError(f"{_render(node.right)} is zero, so {symbol} has no answer.")

    if symbol == "+":
        return left + right
    if symbol == "-":
        return left - right
    if symbol == "*":
        return left * right
    if symbol == "/":
        return left / right
    if symbol == "//":
        return left // right
    return left % right


def _unary(node: ast.UnaryOp, scope: Scope) -> Any:
    value = _evaluate(node.operand, scope)
    if isinstance(node.op, ast.Not):
        return not _truthy(value)
    number = _number(value, node)
    return -number if isinstance(node.op, ast.USub) else number


def _boolean(node: ast.BoolOp, scope: Scope) -> bool:
    """``and`` and ``or``, short-circuiting, and always answering with a yes or a no.

    Python would hand back the last operand instead, which is a convenience nobody wants
    in a rule: it is how a gate ends up reporting a number as its verdict.
    """
    wanted = isinstance(node.op, ast.And)
    for value in node.values:
        if _truthy(_evaluate(value, scope)) is not wanted:
            return not wanted
    return wanted


def _comparison(node: ast.Compare, scope: Scope) -> bool:
    left = _evaluate(node.left, scope)
    for operator, comparator in zip(node.ops, node.comparators, strict=True):
        right = _evaluate(comparator, scope)
        if not _compare(operator, left, right, node):
            return False
        left = right
    return True


def _compare(operator: ast.cmpop, left: Any, right: Any, node: ast.Compare) -> bool:
    if isinstance(operator, ast.Is):
        return left is right
    if isinstance(operator, ast.IsNot):
        return left is not right
    if isinstance(operator, ast.In | ast.NotIn):
        if not isinstance(right, tuple | str):
            raise ExpressionError(
                f"{_render(node.comparators[-1])} is {_name_of(right)}, which nothing can be in."
            )
        contained = left in right
        return contained if isinstance(operator, ast.In) else not contained
    if isinstance(operator, ast.Eq):
        return bool(left == right)
    if isinstance(operator, ast.NotEq):
        return bool(left != right)

    left_value, right_value = _ordered(left, right, node)
    if isinstance(operator, ast.Lt):
        return bool(left_value < right_value)
    if isinstance(operator, ast.LtE):
        return bool(left_value <= right_value)
    if isinstance(operator, ast.Gt):
        return bool(left_value > right_value)
    return bool(left_value >= right_value)


def _ordered(left: Any, right: Any, node: ast.Compare) -> tuple[Any, Any]:
    """Two values an ordering comparison can be made between.

    Numbers order against numbers and text against text. Anything else is a rule that
    would have compared a size against a name and reported something meaningless.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        raise ExpressionError(
            f"{_render(node)} orders a yes or a no against something. Compare it with == instead."
        )
    if isinstance(left, int | float) and isinstance(right, int | float):
        return left, right
    if isinstance(left, str) and isinstance(right, str):
        return left, right
    raise ExpressionError(
        f"{_render(node)} compares {_name_of(left)} against {_name_of(right)}, which have no "
        "order between them."
    )


def _number(value: Any, node: ast.expr) -> int | float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    raise ExpressionError(
        f"{_render(node)} does arithmetic on {_name_of(value)}, which is not a number."
    )


def _truthy(value: Any) -> bool:
    """What counts as a yes.

    Only a yes does. A rule that leans on an empty string being false is a rule whose
    reader has to know Python, and the point of the language is that they do not.
    """
    if not isinstance(value, bool):
        raise ExpressionError(f"{_name_of(value)} is not a yes or a no.")
    return value


def _name_of(value: Any) -> str:
    """What to call a value in a message, in words rather than in type names."""
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "a yes or a no"
    if isinstance(value, int | float):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, tuple):
        return "a list"
    if isinstance(value, Mapping):
        return "a group of facts"
    return type(value).__name__


def _render(node: ast.AST) -> str:
    """Write a node back out, so a message can quote the part that went wrong."""
    return ast.unparse(node)
