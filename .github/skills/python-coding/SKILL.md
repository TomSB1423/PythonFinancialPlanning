---
name: python-coding
description: "Use when writing, reviewing, or refactoring Python code. Covers PEP 8 style, type hints, mypy compliance, ruff linting, OOP design patterns, module structure, docstrings, and naming conventions. Project agnostic."
---

# Python Coding Standards

## When to Use

- Writing new Python modules, classes, or functions
- Reviewing or refactoring existing Python code
- Designing class hierarchies or choosing design patterns
- Ensuring code passes ruff and mypy checks

## Module Layout

Every Python file follows this order:

```python
"""One-line module docstring describing purpose."""

import os
from pathlib import Path

import requests

from mypackage.core import Widget
```

1. Module docstring (one line preferred, multi-line for complex modules).
2. Imports grouped: stdlib → third-party → local, separated by blank lines.
3. No wildcard imports (`from x import *`).
4. No unused imports — ruff will flag them.

### `from __future__ import annotations`

Add only when you have forward references that would otherwise require manual quoting (`-> "Node"`). Avoid it when using libraries that call `typing.get_type_hints()` at runtime (Pydantic v1, `attrs`) — they re-evaluate stringified annotations and can break if a type isn't in scope. Use `TYPE_CHECKING` guards instead for import-cycle-only cases.

## Naming Conventions (PEP 8)

| Element         | Convention   | Example               |
| --------------- | ------------ | --------------------- |
| Module          | `snake_case` | `data_loader.py`      |
| Class           | `PascalCase` | `AccountManager`      |
| Function/Method | `snake_case` | `calculate_balance()` |
| Variable        | `snake_case` | `total_amount`        |
| Constant        | `ALL_CAPS`   | `MAX_RETRIES`         |
| Private attr    | `_leading`   | `_internal_cache`     |
| Type variable   | `PascalCase` | `T`, `ResponseT`      |
| Protocol        | `PascalCase` | `Serializable`        |

- Avoid single-letter names except in comprehensions, lambdas, or well-known conventions (`i`, `k`, `v`, `x`).
- Boolean variables/functions use `is_`, `has_`, `can_`, `should_` prefixes.

## Type Hints and mypy

Type-hint **all** function signatures — parameters and return types:

```python
def calculate_tax(income: float, rate: float = 0.2) -> float:
    return income * rate
```

### Rules

- Annotate class attributes in the class body or `__init__`.
- Use `Self` (from `typing`) for fluent/builder return types.
- Use `TypeAlias` for complex type expressions.
- Avoid `Any` — if unavoidable, add a comment explaining why.
- Use `Protocol` for structural subtyping instead of ABC where only method signatures matter.
- Use `@overload` for functions whose return type depends on input types.
- Run `mypy --strict` or at minimum `mypy --disallow-untyped-defs`.

### Common patterns

```python
from typing import TypeAlias

JsonDict: TypeAlias = dict[str, object]

from typing import Protocol, runtime_checkable

@runtime_checkable
class Serializable(Protocol):
    def to_dict(self) -> JsonDict: ...

from typing import Generic, TypeVar
T = TypeVar("T")

class Repository(Generic[T]):
    def get(self, id: int) -> T | None: ...
```

## Ruff Configuration

Prefer `pyproject.toml` for all ruff configuration:

```toml
[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "RUF",  # ruff-specific rules
]
```

### Key rules to follow

- Maximum line length: 88 characters (Black-compatible).
- Use trailing commas in multi-line collections and function signatures.
- Remove unnecessary `else`/`elif` after `return`/`raise`/`continue`/`break`.

## Class Design

### Principles

- **Single Responsibility**: Each class has exactly one reason to change.
- **Composition over Inheritance**: Prefer injecting collaborators over deep hierarchies.
- **Depend on abstractions**: Accept `Protocol`/`ABC` types, not concrete classes.
- **Immutability by default**: Use `@dataclass(frozen=True)` or Pydantic `model_config = ConfigDict(frozen=True)` unless mutation is required.

### Dataclasses and Pydantic

Use `dataclasses` for simple value objects without validation. Use Pydantic `BaseModel` when validation, serialization, or schema generation is needed:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Coordinate:
    x: float
    y: float
```

```python
from pydantic import BaseModel, Field

class UserConfig(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    retries: int = Field(default=3, ge=1, le=10)
```

### Enums

Enums inherit from `(str, Enum)` for JSON serialization compatibility:

```python
from enum import Enum

class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
```

## Design Patterns

Apply patterns only when they solve an actual problem — don't over-engineer.

### Factory

Use when object creation logic is complex or depends on runtime config:

```python
class NotifierFactory:
    _registry: dict[str, type[Notifier]] = {}

    @classmethod
    def register(cls, key: str, notifier_cls: type[Notifier]) -> None:
        cls._registry[key] = notifier_cls

    @classmethod
    def create(cls, key: str, **kwargs: object) -> Notifier:
        return cls._registry[key](**kwargs)
```

### Strategy

Use when behaviour varies at runtime — pass callables or Protocol implementors:

```python
class Sorter(Protocol):
    def sort(self, data: list[float]) -> list[float]: ...

def process(data: list[float], sorter: Sorter) -> list[float]:
    return sorter.sort(data)
```

### Repository

Use to abstract data access behind a clean interface:

```python
class UserRepository(Protocol):
    def get(self, user_id: int) -> User | None: ...
    def save(self, user: User) -> None: ...
```

### Dependency Injection

Pass dependencies via `__init__` — avoid global state and service locators:

```python
class OrderService:
    def __init__(self, repo: OrderRepository, notifier: Notifier) -> None:
        self._repo = repo
        self._notifier = notifier
```

## Functions

- Keep functions short — aim for under 20 lines of logic.
- One level of abstraction per function.
- Prefer returning values over mutating arguments.
- Use early returns to reduce nesting.
- Limit parameters to 5; group related ones into a dataclass or TypedDict.
- Use `*` to force keyword-only arguments for clarity: `def fetch(*, timeout: int, retries: int)`.

## Error Handling

- Catch specific exceptions, never bare `except:` or `except Exception:` at a low level.
- Raise domain-specific exceptions that subclass `Exception`:
  ```python
  class InsufficientFundsError(Exception): ...
  ```
- Use `raise ... from err` to preserve exception chains.
- Don't use exceptions for control flow.

## Comments and Documentation

- **Module docstring**: One line at top of every file.
- **Class docstring**: Describe purpose and key behaviour. Skip for obvious dataclasses.
- **Function docstring**: Only when the signature + name aren't self-explanatory.
- **Inline comments**: Only for non-obvious logic, not for restating what the code does. Use them to explain _why_ something is done a certain way, not _what_ is being done.
- Keep comments text based for logic explaination, don't include things like lots of hypens.
- Don't comment out code — delete it; version control remembers.
- Don't write `# TODO` without a linked issue or ticket reference.

## Code Smells to Avoid

- God classes that do everything.
- "Helper" functions that are just as complex as the original function.
- "Magic numbers" — use named constants instead.
- Deep nesting (> 3 levels) — extract helper functions.
- Boolean parameters that toggle behaviour — split into two functions.
- String typing — use Enums or Literal types.
- Shadowing builtins (`list`, `dict`, `id`, `type`, `input`).
- Circular imports — restructure modules.
- `assert` for runtime validation — it's stripped with `-O`.
