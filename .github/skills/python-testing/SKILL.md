---
name: python-testing
description: "Use when writing, structuring, or reviewing Python tests. Covers pytest conventions, Arrange-Act-Assert pattern, fixture design, multi-conftest hierarchy, and unit/integration/system test definitions. Project agnostic."
---

# Python Testing Standards

## When to Use

- Writing new tests or test modules
- Structuring a test suite from scratch
- Reviewing test quality and coverage
- Setting up conftest hierarchy and fixtures
- Deciding whether a test is unit, integration, or system level

## Test Levels

### Unit Tests

Test a **single method or function** in isolation. All collaborators are replaced with fakes.

- **Scope**: One public method or function per test.
- **Dependencies**: None — every external call is patched, stubbed, or injected as a fake.
- **Speed**: Microseconds. The full unit suite should run in seconds.
- **Location**: `tests/unit/`

```python
def test_calculate_tax_basic_rate() -> None:
    # Arrange
    income = 50_000.0
    rate = 0.2

    # Act
    result = calculate_tax(income, rate)

    # Assert
    assert result == 10_000.0
```

### Integration Tests

Test the **interaction between your code and a mocked external interface** — databases, APIs, file systems, message queues.

- **Scope**: Multiple internal components wired together, with external boundaries mocked or faked.
- **Dependencies**: Use mocks, fakes, or test-doubles for external systems. Real internal code runs.
- **Speed**: Milliseconds. May use in-memory databases or mock servers.
- **Location**: `tests/integration/`

```python
def test_user_service_creates_and_retrieves(
    mock_db: FakeDatabase,
) -> None:
    # Arrange
    service = UserService(db=mock_db)
    user = User(name="Alice", email="alice@example.com")

    # Act
    service.create(user)
    retrieved = service.get_by_email("alice@example.com")

    # Assert
    assert retrieved is not None
    assert retrieved.name == "Alice"
```

### System Tests

**Full end-to-end** tests against the real running application. No mocks — real databases, real APIs, real file systems.

- **Scope**: Complete user workflows or API call chains.
- **Dependencies**: Real infrastructure (or containerised equivalents via Docker/testcontainers).
- **Speed**: Seconds to minutes. Run separately from unit/integration suites.
- **Location**: `tests/system/`
- **Markers**: Always mark with `@pytest.mark.system` so they can be excluded from fast CI runs.

```python
@pytest.mark.system
def test_full_order_workflow(live_api_client: APIClient) -> None:
    # Arrange
    order_payload = {"item": "widget", "quantity": 3}

    # Act
    response = live_api_client.post("/orders", json=order_payload)
    order_id = response.json()["id"]
    status = live_api_client.get(f"/orders/{order_id}").json()["status"]

    # Assert
    assert response.status_code == 201
    assert status == "pending"
```

## Arrange-Act-Assert (AAA)

Every test follows three clearly separated phases:

```python
def test_descriptive_name() -> None:
    # Arrange — set up inputs, dependencies, and expected state
    account = Account(balance=100.0)

    # Act — execute the single behaviour under test
    account.withdraw(30.0)

    # Assert — verify the outcome
    assert account.balance == 70.0
```

### Rules

- **One Act per test.** If you need two Acts, write two tests.
- **Comments are mandatory** for the three sections — `# Arrange`, `# Act`, `# Assert`.
- Keep Arrange focused: build only what this specific test needs.
- Assert on behaviour and outcomes, not implementation details.
- Prefer plain `assert` statements — pytest introspection provides clear diffs.

## Directory Structure

```
tests/
├── conftest.py              # Shared fixtures: markers, session-scoped resources
├── unit/
│   ├── conftest.py          # Unit-only fixtures: fakes, stubs, builders
│   ├── test_calculator.py
│   └── test_validator.py
├── integration/
│   ├── conftest.py          # Integration fixtures: mock DBs, fake APIs
│   ├── test_user_service.py
│   └── test_order_repo.py
└── system/
    ├── conftest.py          # System fixtures: live clients, docker setup
    └── test_api_workflow.py
```

Each directory has its own `conftest.py`. Fixtures cascade — a fixture in `tests/conftest.py` is available everywhere; one in `tests/unit/conftest.py` is only available to unit tests.

## Conftest Hierarchy

### Root `tests/conftest.py`

Shared across all test levels. Contains:

- Custom marker registration
- Session-scoped resources (tmp directories, shared config)
- Shared helper fixtures used across levels

```python
"""Root test configuration — shared fixtures and markers."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "system: full end-to-end system tests")
    config.addinivalue_line("markers", "slow: tests that take > 1s")
```

### `tests/unit/conftest.py`

Fixtures that build fakes, stubs, and test data for isolated unit tests:

```python
"""Unit test fixtures — fakes and builders."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_user() -> User:
    return User(name="Test User", email="test@example.com")
```

### `tests/integration/conftest.py`

Fixtures that set up mocked external interfaces:

```python
"""Integration test fixtures — mock databases and fake services."""

from __future__ import annotations

import pytest


@pytest.fixture
def mock_db() -> FakeDatabase:
    db = FakeDatabase()
    yield db
    db.clear()
```

### `tests/system/conftest.py`

Fixtures that manage real infrastructure:

```python
"""System test fixtures — live services and clients."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def live_api_client() -> APIClient:
    client = APIClient(base_url="http://localhost:8000")
    yield client
    client.close()
```

## Pytest Configuration

Configure in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = [
    "-ra",              # show summary of all non-passing tests
    "--strict-markers",  # fail on unknown markers
    "--strict-config",   # fail on config errors
    "-q",               # quiet output by default
]
markers = [
    "system: full end-to-end system tests",
    "slow: tests that take > 1 second",
]
# Skip system tests by default — run explicitly with: pytest -m system
```

Run commands:

```bash
# Unit + integration (default fast suite)
pytest tests/unit tests/integration

# System tests only
pytest -m system

# All tests
pytest

# With coverage
pytest --cov=src --cov-report=term-missing
```

## Fixtures

### Principles

- **Smallest scope possible**: default to `function` scope. Use `session` or `module` only for expensive setup (DB connections, containers).
- **Explicit over implicit**: name fixtures clearly. `mock_db` not `db`. `sample_user` not `user`.
- **Yield for teardown**: use `yield` in fixtures that need cleanup.
- **No side effects between tests**: every test gets a clean slate.
- **Parametrize for variants**: use `@pytest.fixture(params=[...])` or `@pytest.mark.parametrize` instead of duplicating tests.

### Factory fixtures

When tests need many similar objects with small variations, use a factory fixture:

```python
@pytest.fixture
def make_user() -> Callable[..., User]:
    def _make(name: str = "Default", email: str = "default@test.com") -> User:
        return User(name=name, email=email)
    return _make


def test_user_display_name(make_user: Callable[..., User]) -> None:
    # Arrange
    user = make_user(name="Alice")

    # Act
    display = user.display_name()

    # Assert
    assert display == "Alice"
```

## Parametrize

Use `@pytest.mark.parametrize` to test multiple inputs without repeating test logic:

```python
@pytest.mark.parametrize(
    ("input_val", "expected"),
    [
        (0, "zero"),
        (1, "one"),
        (-1, "negative"),
    ],
    ids=["zero", "positive", "negative"],
)
def test_classify_number(input_val: int, expected: str) -> None:
    # Act
    result = classify(input_val)

    # Assert
    assert result == expected
```

- Always provide `ids` for readability in test output.
- Keep parameter sets focused — don't parametrize unrelated dimensions in the same decorator.

## Mocking

- Use `unittest.mock.patch` or `pytest-mock`'s `mocker` fixture.
- **Patch where the object is used**, not where it's defined:
  ```python
  # Module under test: myapp/service.py imports requests
  @patch("myapp.service.requests.get")
  def test_fetch_data(mock_get: MagicMock) -> None: ...
  ```
- Prefer dependency injection over patching — pass fakes via constructor or fixture.
- Assert on mock calls only when verifying interactions is the point of the test.
- Avoid over-mocking: if you mock more than you test, the test proves nothing.

## Naming and Organisation

- Test files mirror source files: `src/auth/login.py` → `tests/unit/test_login.py`.
- Test functions: `test_<method>_<scenario>_<expected>`:
  ```
  test_withdraw_insufficient_funds_raises_error
  test_calculate_tax_zero_income_returns_zero
  ```
- Group related tests in classes (no `__init__`):
  ```python
  class TestAccountWithdraw:
      def test_sufficient_balance_succeeds(self) -> None: ...
      def test_insufficient_balance_raises(self) -> None: ...
      def test_zero_amount_is_noop(self) -> None: ...
  ```
- One assertion concept per test — multiple `assert` lines are fine if they verify the same logical outcome.

## Assertions

- Use plain `assert` — pytest rewrites them for clear diffs.
- For floats: `assert result == pytest.approx(expected, rel=1e-6)`.
- For exceptions:
  ```python
  with pytest.raises(ValueError, match="must be positive"):
      withdraw(-10)
  ```
- For warnings: `with pytest.warns(DeprecationWarning):`.
- Avoid `assertTrue`, `assertEqual` — those are unittest style.

## Anti-Patterns to Avoid

- **Tests that test the mock**: asserting on mock return values you set up yourself.
- **Shared mutable state**: tests that depend on execution order.
- **Giant Arrange blocks**: extract setup into fixtures or factory functions.
- **No assertions**: a test that only calls code without verifying anything.
- **Testing private methods**: test through the public interface.
- **Flaky tests**: time-dependent, network-dependent, or order-dependent — fix or delete.
- **Ignoring test failures**: a red test that stays red is worse than no test.
