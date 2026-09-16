"""Single source of truth for the agent's tool surface.

Before this module the tool surface was maintained in three separate places
inside ``graph.py``: the adapter ``def`` blocks, the ``tools = [...]`` bind
list, and the ``tool_func_map`` dispatch dictionary.  Adding one tool meant
editing all three by hand, and forgetting one was a runtime failure that no
type checker could catch.

An adapter now declares itself exactly once::

    @registry.tool("factor")
    def _search_factors(query: str) -> str:
        \"\"\"Search the factor library by natural language query.\"\"\"
        ...

The bind list and the dispatch map are both derived from that registration, so
the three-way bookkeeping is gone.

Two invariants are preserved deliberately:

* ``tool()`` returns the function **unchanged**.  Adapters therefore stay plain
  Python functions, and LangChain derives each tool's name (``__name__``),
  description (``__doc__``) and argument schema (type hints) exactly as it did
  before this module existed.
* Registration order is preserved.  The list handed to ``bind_tools`` keeps a
  stable order, so the tool schema sent to the model is byte-for-byte the same
  as the previous hand-written list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Iterator

# An adapter maps JSON-friendly arguments to a JSON string for the model.
ToolFunc = Callable[..., str]


@dataclass(frozen=True)
class ToolEntry:
    """One registered agent tool."""

    name: str
    """LLM-facing tool name — the adapter's ``__name__``."""

    func: ToolFunc
    """The adapter itself, registered for dispatch."""

    domain: str
    """Capability domain, used for grouping and domain-scoped binding."""

    description: str
    """Tool description shown to the model — the adapter's docstring."""


class ToolRegistry:
    """Collects agent tools and derives the surfaces the graph needs."""

    def __init__(self) -> None:
        self._entries: dict[str, ToolEntry] = {}

    # ── registration ───────────────────────────────────────────────

    def tool(self, domain: str) -> Callable[[ToolFunc], ToolFunc]:
        """Decorator registering an adapter under ``domain``.

        Returns the function unchanged so adapters remain plain functions.
        """

        def decorator(func: ToolFunc) -> ToolFunc:
            self.add(func, domain=domain)
            return func

        return decorator

    def add(self, func: ToolFunc, *, domain: str) -> ToolFunc:
        """Register ``func``, failing loudly on a contract violation."""
        name = func.__name__
        if name in self._entries:
            raise ValueError(
                f"duplicate agent tool name {name!r}: already registered "
                f"in domain {self._entries[name].domain!r}"
            )
        doc = func.__doc__
        if not doc or not doc.strip():
            # The docstring is the tool description the model reads. A missing
            # one silently degrades tool selection, so reject it here.
            raise ValueError(
                f"agent tool {name!r} has no docstring; the model uses it as "
                f"the tool description"
            )
        self._entries[name] = ToolEntry(
            name=name, func=func, domain=domain, description=doc
        )
        return func

    # ── derived surfaces ───────────────────────────────────────────

    def entries(self, domains: Iterable[str] | None = None) -> list[ToolEntry]:
        """Registered entries in registration order, optionally domain-filtered."""
        selected = self._select(domains)
        return list(selected.values())

    def bind(self, domains: Iterable[str] | None = None) -> list[ToolFunc]:
        """The list handed to ``bind_tools``."""
        return [entry.func for entry in self.entries(domains)]

    def dispatch(self, domains: Iterable[str] | None = None) -> dict[str, ToolFunc]:
        """Tool name → adapter, for executing the model's tool calls."""
        return {entry.name: entry.func for entry in self.entries(domains)}

    def names(self, domains: Iterable[str] | None = None) -> list[str]:
        """Registered tool names in registration order."""
        return [entry.name for entry in self.entries(domains)]

    def domains(self) -> dict[str, list[str]]:
        """Domain → tool names, for inventories and routing."""
        grouped: dict[str, list[str]] = {}
        for entry in self._entries.values():
            grouped.setdefault(entry.domain, []).append(entry.name)
        return grouped

    def domain_names(self) -> list[str]:
        """Known domain keys in first-registration order."""
        return list(self.domains())

    # ── internals ──────────────────────────────────────────────────

    def _select(self, domains: Iterable[str] | None) -> dict[str, ToolEntry]:
        if domains is None:
            return self._entries
        wanted = list(domains)
        available = self.domains()
        unknown = [d for d in wanted if d not in available]
        if unknown:
            raise ValueError(
                f"unknown tool domain(s) {unknown}; available: {sorted(available)}"
            )
        keep = set(wanted)
        return {
            name: entry
            for name, entry in self._entries.items()
            if entry.domain in keep
        }

    # ── dunder helpers ─────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[ToolEntry]:
        return iter(self._entries.values())

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def __repr__(self) -> str:
        return (
            f"ToolRegistry({len(self._entries)} tools, "
            f"{len(self.domains())} domains)"
        )
