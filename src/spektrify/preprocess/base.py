"""Preprocessing steps and pipelines.

A *step* is a small dataclass whose fields are its parameters and whose ``__call__`` maps a
:class:`~spektrify.model.Cube` to a new one. Registering it with :func:`register_step` makes
it available everywhere at once: the Python API, the CLI (``--step name:param=value``) and
the viewer's Preprocess panel, which builds its form from :func:`step_schema`.
"""

from __future__ import annotations

import dataclasses
import typing
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from spektrify.model import Cube


class Step(Protocol):
    def __call__(self, cube: Cube) -> Cube: ...


_STEPS: dict[str, Any] = {}  # name -> dataclass
_HELP: dict[str, str] = {}
T = TypeVar("T", bound=type)


def register_step(name: str, help: str) -> Callable[[T], T]:  # noqa: A002
    """Class decorator: register a dataclass step under ``name``."""

    def deco(cls: T) -> T:
        if not dataclasses.is_dataclass(cls):
            raise TypeError(f"step {name!r} must be a dataclass")
        _STEPS[name], _HELP[name] = cls, help
        return cls

    return deco


def param(default: Any, help: str) -> Any:  # noqa: A002
    """A step parameter with a help text (shown in the CLI and the viewer)."""
    return field(default=default, metadata={"help": help})


def _params(cls: Any) -> list[tuple[dataclasses.Field[Any], type]]:
    hints = typing.get_type_hints(cls)
    return [(f, hints[f.name]) for f in dataclasses.fields(cls)]


def step_schema() -> list[dict[str, Any]]:
    """Every registered step with its parameters, as plain JSON-able data."""
    return [
        {
            "name": name,
            "help": _HELP[name],
            "params": [
                {
                    "name": f.name,
                    "type": t.__name__,
                    "default": f.default,
                    "help": f.metadata["help"],
                }
                for f, t in _params(cls)
            ],
        }
        for name, cls in _STEPS.items()
    ]


def _coerce(value: Any, t: type) -> Any:
    if t is bool and isinstance(value, str):
        if value.lower() in ("1", "true", "yes", "on"):
            return True
        if value.lower() in ("0", "false", "no", "off"):
            return False
        raise ValueError(f"expected true/false, got {value!r}")
    return t(value)


def make_step(name: str, params: Mapping[str, Any] | None = None) -> Step:
    """Instantiate a registered step, converting string parameters to the right types."""
    try:
        cls = _STEPS[name]
    except KeyError:
        raise ValueError(f"unknown step {name!r}; have {sorted(_STEPS)}") from None
    types = {f.name: t for f, t in _params(cls)}
    kwargs = {}
    for k, v in (params or {}).items():
        if k not in types:
            raise ValueError(f"step {name!r} has no parameter {k!r}; have {list(types)}")
        try:
            kwargs[k] = _coerce(v, types[k])
        except (TypeError, ValueError) as e:
            raise ValueError(f"{name}.{k}: {e}") from None
    return cls(**kwargs)


def describe(step: Any) -> str:
    """``bin(factor=2)``: the step name and its parameters."""
    name = next(n for n, c in _STEPS.items() if isinstance(step, c))
    args = [f"{f.name}={getattr(step, f.name)!r}" for f in dataclasses.fields(step)]
    return f"{name}({', '.join(args)})"


@dataclass(frozen=True)
class Pipeline:
    """An ordered list of ``(step name, parameters)``; applying it never mutates the input."""

    steps: tuple[tuple[str, dict[str, Any]], ...] = ()

    @classmethod
    def parse(cls, specs: Iterable[str]) -> Pipeline:
        """From CLI specs: ``"clip"``, ``"bin:2"``, ``"crop:x0=10,x1=200"``. A bare value sets
        the step's first parameter."""
        steps = []
        for spec in specs:
            name, _, rest = spec.strip().partition(":")
            params: dict[str, Any] = {}
            for i, item in enumerate(filter(None, (p.strip() for p in rest.split(",")))):
                key, eq, value = item.partition("=")
                if not eq:
                    if i:
                        raise ValueError(f"{spec!r}: only the first parameter can be unnamed")
                    key, value = _first_param(name), key
                params[key.strip()] = value.strip()
            make_step(name, params)  # validate early
            steps.append((name, params))
        return cls(tuple(steps))

    @classmethod
    def from_json(cls, items: Iterable[Mapping[str, Any]]) -> Pipeline:
        steps = tuple((str(it["name"]), dict(it.get("params") or {})) for it in items)
        for name, params in steps:
            make_step(name, params)
        return cls(steps)

    def to_json(self) -> list[dict[str, Any]]:
        return [{"name": n, "params": p} for n, p in self.steps]

    def __bool__(self) -> bool:
        return bool(self.steps)

    def apply(self, cube: Cube) -> Cube:
        done = []
        for name, params in self.steps:
            step = make_step(name, params)
            cube = step(cube)
            done.append(describe(step))
        if done:
            cube.meta["preprocessing"] = " → ".join(done)
        return cube


def _first_param(name: str) -> str:
    cls = _STEPS.get(name)
    if cls is None:
        raise ValueError(f"unknown step {name!r}; have {sorted(_STEPS)}")
    fields = dataclasses.fields(cls)
    if not fields:
        raise ValueError(f"step {name!r} takes no parameters")
    return fields[0].name
