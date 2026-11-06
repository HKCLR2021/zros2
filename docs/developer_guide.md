# zros2 Internal Developer Guide

> Applies to **zros2 2.0.0** · Python ≥ 3.12
> This guide is for maintainers and contributors. User-facing documentation:
> [SDK guide (English)](./sdk_development.md) and
> [SDK guide (Chinese)](./sdk_development_zh.md). The Chinese contributor
> guide is [developer_guide_zh.md](./developer_guide_zh.md). **`.rules` is the
> authoritative source for project conventions**; if this guide conflicts with
> it, `.rules` wins.

---

## Table of contents

1. [Project overview and repository layout](#1-project-overview-and-repository-layout)
2. [Runtime architecture](#2-runtime-architecture)
3. [Generator architecture](#3-generator-architecture)
4. [Public / private API conventions](#4-public--private-api-conventions)
5. [Codegen ↔ runtime ABI contract](#5-codegen--runtime-abi-contract)
6. [Type-system rules](#6-type-system-rules)
7. [Coding conventions](#7-coding-conventions)
8. [Test organization](#8-test-organization)
9. [Benchmarks](#9-benchmarks)
10. [Development environment and verification](#10-development-environment-and-verification)
11. [CI and release](#11-ci-and-release)
12. [Pre-commit checklist](#12-pre-commit-checklist)
13. [Commit and PR conventions](#13-commit-and-pr-conventions)
14. [Typical change walkthroughs](#14-typical-change-walkthroughs)

---

## 1. Project overview and repository layout

**zros2** is a client-side ROS 2-style communication library over Zenoh. Its
runtime provides publish/subscribe, service-client, action-client, and
liveliness discovery primitives. The bundled `zros2-gen` generator statically
compiles `.msg` / `.srv` / `.action` files into typed Python dataclasses backed
by `pycdr2.IdlMeta` and CDR serialization.

```text
src/zros2/
├── __init__.py          # top-level public API re-exports (__all__)
├── _client.py           # ZRosClient: factory methods + readiness delegation
├── _namespace.py        # join_name / graph-name normalization (sync + async)
├── _session.py          # ZenohSessionProxy: protected shared session
├── _action_msgs.py      # built-in action_msgs protocol messages
├── exceptions.py        # exception hierarchy rooted at ZRos2Exception
├── endpoints/           # Publisher / Subscriber / ServiceClient / Action
│   ├── _action_state.py     # GoalHandle, goal state helpers
│   ├── _action_transport.py # internal action service/subscriber plumbing
│   └── _action_keys.py      # action_key: five `_action/` channels
├── types/               # RosMessage, RosService, RosAction, containers
├── discovery/           # Liveliness, Qos, LivelinessKey, readiness probes
├── asyncio/             # optional asyncio facade (AsyncRobotClient, ...)
└── generator/           # zros2-gen: parsing → semantics → codegen → pipeline
    ├── parsing/         # Lark grammar → IR
    ├── semantics/       # type/literal/default/bound semantics
    ├── codegen/         # IR → Python AST / .pyi
    │   ├── _message/    # context, plan, defaults, methods, assembly
    │   ├── _merge.py    # generic source-only AST merger
    │   ├── _service_merge.py # render + merge service/action families
    │   ├── _service_action.py
    │   ├── _stubs.py
    │   └── ...
    ├── pipeline/        # collect, plan, generate, write
    └── assets/builtin_msgs/  # bundled IDL per distro
tests/                   # pytest suite, including golden and architecture tests
benchmarks/              # pytest-benchmark suites
```

Implementation modules use a leading `_`; private symbols also use `_` and are
never listed in `__all__`.

---

## 2. Runtime architecture

### 2.1 Session ownership and proxy

`ZRosClient.__init__` opens and owns a `zenoh.Session`; `close()` is idempotent
and checks `is_closed()` first. Endpoints receive a `ZenohSessionProxy`, never
the raw session:

- the proxy delegates attribute access through `__getattr__`, but forbids
  `close` / `destroy` / `__del__` / `undeclare` (raises `PermissionError`);
- `__setattr__` is rejected (`PermissionError`);
- endpoints therefore cannot accidentally close the shared session; lifecycle
  belongs to `ZRosClient` alone.

Factory methods (and their asyncio counterparts) use
`_namespace.join_name(namespace, name)`: slashes on both namespace and name are
normalized; an empty namespace still strips the leading `/` from the name; a
non-empty namespace produces `{namespace}/{name}`. Do not duplicate this logic
inside endpoints.

### 2.2 Endpoint design notes

| Endpoint | Notes |
|---|---|
| `Publisher` | Declares the Zenoh publisher at construction; `publish` calls `data.serialize()`; `destroy()` is idempotent and a later `publish` raises `RuntimeError`. |
| `Subscriber` | Callbacks run on Zenoh threads and must be synchronous. A coroutine is closed and rejected with `TypeError` (avoiding a "never awaited" leak). An `RLock` protects subscription state; a second `subscribe` raises `ValueError`; deserialization failures are logged. |
| `ServiceClient` | Uses Zenoh `get`; an error reply raises `ServiceInvokeException`, no reply raises `ServiceNotAvailableException`, and `zenoh.ZError` is wrapped in `ServiceInvokeException`. |
| `Action` | `_action_state.py` owns `GoalHandle` state; `_action_transport.py` owns the three internal service calls and two subscriptions. Channel keys come from `endpoints/_action_keys.action_key`; `_make_srv_type` caches minimal service types by `(name, request, response)`. Goal IDs are `os.urandom(16)`, normalized to `bytes`; `_active_goal_ids` filters feedback; cancel-all uses an all-zero 16-byte ID. |
| `Liveliness` | Keys are built/parsed by `LivelinessKey`: `@/{zenoh_id}/@ros2_lv/{MP,MS,SS,SC,AS,AC}/...`; `/` in names/types is escaped as `§`; service/action keys carry no QoS, pub/sub keys do (`Qos.to_key_expr` / `from_key_expr`). |

Service-readiness polling lives in `discovery/_readiness.py`;
`ZRosClient.service_is_ready()` and `wait_for_service()` are thin delegates.

### 2.3 Built-in action messages

The generator does not emit `action_msgs` types, so `_action_msgs.py` defines
`GoalInfo` / `GoalStatus` / `GoalStatusArray` / `CancelGoal_Request` /
`CancelGoal_Response` (plus `Time`) by hand. They are normal
`pycdr2.IdlStruct` classes that structurally satisfy `RosMessage`.
`GoalInfo.goal_id` uses `array[uint8, 16]` instead of
`unique_identifier_msgs/UUID`; the CDR encoding is identical and matches the
generator's `GOAL_ID_TYPE`. The class layout mirrors generated code
(`@dataclass(init=False)` plus a handwritten `__init__`).

### 2.4 asyncio facade (`zros2.asyncio`)

The core API is synchronous; the facade does not change it:

- blocking calls are offloaded with `asyncio.to_thread`
  (`invoke_service`, `query_liveliness`, `AsyncPublisher.publish`);
- Zenoh-thread callbacks are bridged into the loop through **bounded queues
  (capacity 100)** using `loop.call_soon_threadsafe(_put_nowait, ...)`;
  `QueueFull` drops the oldest entry. The `put_nowait` failure must be handled
  on the loop thread, which is why it is wrapped in `call_soon_threadsafe`;
- generator cleanup (`invoke_action` / `watch_liveliness` /
  `AsyncSubscriber.__anext__`) explicitly closes the inner generator so
  endpoint context managers always undeclare;
- events are frozen dataclasses: `ActionFeedback(feedback)` and
  `ActionResult(status, result)`.

---

## 3. Generator architecture

Four stages: `parsing` → `semantics` → `codegen` → `pipeline`. Generated Python
is always built with the **`ast` module**, never string templates.

```text
.msg / .srv / .action
        │
        ▼
┌─────────────┐
│   parsing    │  Lark → IR (MsgField / MsgDefinition; .action → ActionSource)
└──────┬──────┘
       ▼
┌─────────────┐
│  semantics   │  expand_action (8 action types) + type/literal/bound semantics
└──────┬──────┘
       ▼
┌─────────────┐
│   codegen    │  Python AST → source (dataclasses + .pyi + registry)
└──────┬──────┘
       ▼
┌─────────────┐
│  pipeline    │  collect / plan / validate / generate / write
└─────────────┘
```

### 3.1 Responsibilities

- **parsing/** — Lark parses `.msg` / `.srv` / `.action`. `.action` yields only
  `ActionSource` (Goal / Result / Feedback); it never encodes transport fields.
  `_discovery.py` defines `VALID_DISTROS`, `find_msg_dirs`, file iteration, and
  dependency validation. It does not collect types and does not import
  `semantics`.
- **semantics/** — `expand_action` / `ACTION_SPEC` / `GOAL_ID_TYPE` are the
  single source of truth for action IDL expansion. `_resolve_types.py` owns
  `ResolvedType`; `_literal_values.py` turns `.msg` text into Python values
  (without importing `ast`); `_type_context.py` centralizes constants and
  bounds; `_native_types.py` provides the runtime/stub Python type mapping;
  `_field_semantics.py` provides `FieldSemantics`. `_utilities.py` keeps only
  header/naming/default helpers and no longer builds AST.
- **codegen/** —
  - `_file.py`: frozen `GeneratedFile(path, content)` DTO; `pipeline`/`writer`
    depend only on this DTO;
  - `_message/`: `__init__.py` (public entry) → `_context.py` (semantic
    context) → `_plan.py` (field plans) → `_defaults.py` (default AST) →
    `_methods.py` (`to_dict`/`from_dict`) → `_assemble.py` (module assembly);
  - `_stubs.py`: consumes only `semantics` `native_stub_type` /
    `stub_annotation` / literal values; it must not import `_message`;
  - `_merge.py`: generic, **source-only** AST merge (import deduplication,
    self-reference removal, body concatenation); it must not import renderers;
  - `_service_merge.py`: renders each sub-type and delegates to `_merge.py`;
  - `_service_action.py`: service/action wrappers and registry calls;
    `_wrapper.py`: wrapper-class AST;
  - `_root_init.py`: root package `__init__.py` policy;
  - `_registry.py`: assembles `REGISTRY_AST`; sections live in
    `_registry_common.py`, `_registry_messages.py`, `_registry_services.py`,
    and `_registry_actions.py`; `_package_init.py`: package-level
    `__init__.py`.
- **pipeline/** — `_collect.py` collects and expands types; `build_plan` →
  `GenerationPlan`; `execute_plan(plan, dry_run=...)`; `generate_all` is the
  six-stage orchestration. Action package export filtering uses
  `ACTION_WIRE_SUFFIXES`.

### 3.2 CLI

`_cli.py` provides `build_parser()` / `main()`; entry points are `zros2-gen`
(from `pyproject.toml`) and `python -m zros2.generator` (`__main__.py`).
Options: `--msg-dirs`, `--output`, `--ros-version`
(choices=`VALID_DISTROS`), `--root-package`, `--dry-run`. `--msg-dirs` accepts
package directories or a workspace whose immediate children contain `msg/`,
`srv/`, or `action/`; the CLI errors out when no package is found.

### 3.3 Bundled message assets

`assets/builtin_msgs/` bundles official IDL per distro. Builds include these
assets (see `[tool.setuptools.package-data]` in `pyproject.toml`). User types
override builtin types with the same name.

---

## 4. Public / private API conventions

### Public surface

Public API consists **only** of symbols re-exported through each package's
`__init__.py` and `__all__`:

- `zros2`: `ZRosClient`; endpoints (`Publisher`, `Subscriber`, `ServiceClient`,
  `Action`, `GoalHandle`); discovery (`Liveliness`, `LivelinessType`, `Qos`);
  type protocols/containers; built-in action protocol messages (`GoalInfo`,
  `GoalStatus`, `GoalStatusArray`, `CancelGoal_Request`,
  `CancelGoal_Response`); `__version__`; and Zenoh's `Reply` / `Sample` /
  `SampleKind`.
- `zros2.exceptions`: `ZRos2Exception` and the `Service*Exception` /
  `Action*Exception` subclasses.
- `zros2.asyncio`: `AsyncRobotClient` (accepts a `ZRosClient` or session
  proxy), `ActionFeedback` / `ActionResult`, `AsyncPublisher` /
  `AsyncSubscriber`. No module-level entry points.
- `zros2.types`: exactly six symbols — `RosMessage`, `RosService`,
  `RosAction`, `RosActionView`, `ServiceTypes`, `ActionTypes`.
- `zros2.generator`: `VALID_DISTROS`, `parse_*` functions, `ActionSource`,
  `expand_action`, `ResolvedType` / `resolve_type`, `generate_all`.
- `zros2.generator.codegen`: `GeneratedFile` and the `generate_*` functions
  (programmatic API).

The protocols (`RosMessage` / `RosService` / `RosAction` / `RosActionView`) are
the public type contract: generated classes and downstream code satisfy them
**structurally**, without inheriting from zros2.

### Private implementation

- Implementation modules use a leading `_` (`_client.py`,
  `endpoints/_publisher.py`, `types/_protocols.py`,
  `generator/**/_*.py`, `_cli.py`); private symbols are `_`-prefixed and never
  enter `__all__`.
- Internal modules may be moved freely, but public import paths (through
  `__init__.py` re-exports) must not change. Do **not** keep compatibility
  shims for symbols that already live in a subpackage.
- **Documentation is a contract**: README and docstring examples must never
  import `_`-prefixed modules (e.g. `zros2.types._utils`, `zros2._session`).
  Promote a capability to the public surface before documenting it.

### Change checklist for public symbols

When adding or removing a public symbol, update in one change:

1. the owning package `__init__.py` and its `__all__`;
2. the README (protocol table / usage examples);
3. `.rules`;
4. the `tests/test_runtime_contract.py` whitelist if the generator hardcodes
   a reference to the symbol.

---

## 5. Codegen ↔ runtime ABI contract

The generator hardcodes a small set of runtime symbols into generated output
(the generation ABI):

- `zros2.types` → `RosMessage`, `ServiceTypes`, `ActionTypes`
- `zros2.types._utils` → `from_attributes` (the only `_`-prefixed symbol in the
  ABI; moving that private module requires regenerating output)

`RUNTIME_CONTRACT` in `tests/test_runtime_contract.py` is the authoritative
whitelist. The contract tests have four groups:

| Test group | Checks |
|---|---|
| `TestStaticImportContract` | Every `zros2.*` import emitted by the generator is whitelisted **and** resolves against the installed runtime; the whitelist cannot drift silently. |
| `TestRegistryContract` | `REGISTRY_AST` defines every registry function re-exported by the root `__init__.py`. |
| `TestContainerFieldContract` | Keyword names in generated `ServiceTypes(...)` / `ActionTypes(...)` calls match the container dataclass fields. |
| `TestProtocolContract` | Generated message classes satisfy `RosMessage`; service/action wrappers expose every `RosService` / `RosAction` / `RosActionView` member. |

**Changing either side requires updating the whitelist in the same change**;
the test fails loudly otherwise. For example, moving `from_attributes` to a
public module requires updating both the generator and `RUNTIME_CONTRACT`, then
regenerating existing output.

---

## 6. Type-system rules

- Use **PEP 695 type parameters** bound to `RosMessage`
  (`class Publisher[MsgT: RosMessage]`,
  `def create_publisher[MsgT: RosMessage](...)`). Do **not** define or export
  shared module-level `TypeVar`s — each class/function declares its own.
- `RosActionView` is the three-parameter semantic view of an action type
  (`GoalT` / `ResultT` / `FeedbackT`) for generic consumers that forward goals
  or observe results/feedback without touching the five transport sub-types.
- `@runtime_checkable` performs **presence checks only**: applying `isinstance`
  to member protocols (`RosService`, `RosAction`, `RosActionView`) only tests
  `hasattr(Request/Response/Goal/...)` and must not be used as runtime
  validation.
- Prefer structural protocols over ABCs; use `isinstance(x, RosMessage)` only
  when a runtime check is genuinely needed.
- `RosService` / `RosAction` / `RosActionView` describe generated **class
  objects**, not instances. Their members are plain attributes; `ClassVar`
  cannot reference a protocol's own type parameters. Pass the class object
  directly (`action_type: RosAction[...]`), not `type[RosAction[...]]`.
  `pyrightconfig.json` type-checks `src` only; tests and benchmarks are
  intentionally outside the type-check scope.

---

## 7. Coding conventions

- Prefer **modern Python 3.12 syntax**: PEP 695 type parameters, PEP 673
  (`Self`), PEP 604 (`X | Y`), PEP 698 (`typing.override`), PEP 692 (TypedDict
  `**kwargs`), PEP 654 (`ExceptionGroup`), PEP 646 (`TypeVarTuple`). Avoid
  `Optional[X]` / `Union[X, Y]` / `typing.List` and similar legacy forms.
- Type annotations are mandatory on every function signature and public class
  attribute.
- Use double quotes consistently, including docstrings and error messages.
- Every `.py` file has a module-level docstring describing its purpose.
- Docstrings follow Google style (`Args:` / `Raises:` / `Returns:`); write
  docstrings for public APIs, keep internal ones lean.
- Line length: soft 88, hard 99.
- Naming: `snake_case` for functions/methods/variables; `PascalCase` for
  classes/protocols/dataclasses; `UPPER_CASE` for constants and ROS constant
  fields; private symbols use a leading `_`.
- Imports: standard library → third-party → local, separated by blank lines.
  Cross-package imports are absolute (`from zros2.types...`); only
  same-package `.` relative imports are allowed. Parent-relative imports
  (`..` / `...`) are forbidden and enforced by `tests/test_architecture.py`.
  Import classes/functions rather than modules unless documented otherwise.
- Exceptions are rooted at `ZRos2Exception` (see SDK guide §11); raise specific
  exceptions and catch broadly only at public API boundaries.
- **Context managers must be idempotent** (`destroy()` checks for `None` before
  undeclaring).
- Comments explain non-obvious intent/constraints/trade-offs, not what the code
  already says.

### Type checking (pyright)

`pyrightconfig.json` type-checks **`src` only**; `reportUnusedImport` is an
error. Tests and benchmarks are intentionally excluded from static type
checking and are validated by runtime tests instead. Do not add `# pyright:
ignore` comments: fix the annotation or the underlying type boundary. Zenoh's
own incomplete type surface is an external dependency issue; do not model it
in zros2 or use it as a reason to lower the global checking mode.

---

## 8. Test organization

pytest only — no `unittest.TestCase`. Test classes use `TestPascalCase` to
describe the unit under test; files are `test_<module_name>.py`; fixtures live
in `conftest.py`.

| Test files | Coverage |
|---|---|
| `test_parser_unit.py` / `test_type_grammar.py` / `test_action_expand_unit.py` | Lark grammar, type expressions, field parsing, action IDL expansion |
| `test_codegen_msg_unit.py` / `test_codegen_init_unit.py` / `test_codegen_pyi_unit.py` / `test_codegen_registry_unit.py` / `test_codegen_srv_action_unit.py` | message modules, init modules, stubs, registry, service/action wrappers |
| `test_pipeline_plan_unit.py` / `test_codegen_orchestrator_unit.py` / `test_generator.py` | plan building, orchestration, validation, generator integration |
| `test_publisher_unit.py` / `test_subscriber_unit.py` / `test_service_unit.py` / `test_action_unit.py` / `test_action_msgs_unit.py` | endpoint behavior (including `action_key` channel mapping) |
| `test_client_unit.py` / `test_namespace_unit.py` | `ZRosClient` factory methods, readiness, `join_name` |
| `test_liveliness_unit.py` | key-expression building/parsing, QoS |
| `test_protocols.py` / `test_runtime_structure_unit.py` / `test_runtime_contract.py` | protocol structure, runtime structure, ABI contract |
| `test_type_map_unit.py` / `test_utilities.py` / `test_utils_unit.py` / `test_semantics_units.py` | type mapping, defaults, `from_attributes`, semantic-layer units |
| `test_asyncio_*.py` | asyncio facade (service/action/endpoints/liveliness/client) |
| `test_integration.py` | pub/sub, service, action over two local Zenoh peers |
| `test_proxies_unit.py` | `ZenohSessionProxy` protection semantics |
| `test_architecture.py` | generator import-direction rules |
| `test_golden_codegen.py` / `golden/` | normalized generated `.py` / `.pyi` snapshots |
| `test_regressions.py` | root-cause regression coverage |

New features/fixes require tests. New `_`-prefixed functions must either be
covered by tests (a named ignore is then justified) or be removed.

---

## 9. Benchmarks

`benchmarks/benchmarks.py` and `compare.py` use pytest-benchmark:

```bash
pytest benchmarks/ --benchmark-only   # expects 96 tests
```

Run the full benchmark when generator output changes to confirm there is no
performance regression.

---

## 10. Development environment and verification

```bash
pip install -e ".[dev]"

# all tests
pytest

# lint/import sorting
ruff check src tests benchmarks

# type checking: 0 errors / 0 warnings, including touched files
pyright                 # or: npx pyright

# generator smoke test
python -m zros2.generator --help

# generation ABI contract
pytest tests/test_runtime_contract.py -v

# benchmark collection check
pytest benchmarks/ --benchmark-only --collect-only
```

---

## 11. CI and release

`.github/workflows/ci.yml` runs on pushes / PRs to `master` (changes limited to
`*.md` and `docs/**` are ignored). It uses a Python **3.12 / 3.13 / 3.14**
matrix, installs `.[dev]`, runs `pytest tests/` with a 95% coverage gate and
uploads `coverage.xml`, runs a separate `type-check` job with `pyright`, and a
separate `package` job that builds a wheel, installs it, and verifies bundled
assets. Before committing locally, tests and pyright must be green.

`.github/workflows/release.yml` runs when a tag matching `v*` is pushed. It
checks that the tag (`vX.Y.Z`) matches `pyproject.toml`, runs the full test
suite, builds a `py3-none-any` wheel with `python -m build --wheel`, and creates
a **draft** GitHub Release with the wheel attached. Review the draft and click
Publish when ready. zros2 is pure Python, so one wheel covers all
OSes/architectures. It is not published to PyPI.

Release steps:

1. set `pyproject.toml` `version` to the target version (e.g. `2.0.0`) and
   commit it;
2. create and push the tag: `git tag v2.0.0 && git push origin v2.0.0`;
3. the workflow creates a draft Release with
   `zros2-2.0.0-py3-none-any.whl`; review the notes and Publish.

---

## 12. Pre-commit checklist

- [ ] **Full test suite**: `pytest` passes with no new failures.
- [ ] **Lint/imports**: `ruff check src tests benchmarks` passes (import
      blocks sorted, no unused imports).
- [ ] **Type checking**: `pyright` reports 0 errors / 0 warnings for the whole
      project, including touched/affected files.
- [ ] **Public API completeness**: if public symbols changed, update the
      owning `__init__.py` + `__all__`, README (protocol table/examples),
      `.rules`, and the contract whitelist.
- [ ] **Contract tests**: `tests/test_runtime_contract.py` passes — every
      hardcoded `zros2.*` import still resolves.
- [ ] **Generator smoke test**: if the generator changed, `python -m
      zros2.generator --help` works and `pytest benchmarks/ --benchmark-only`
      still collects (96); run the full benchmark when output changed.
- [ ] **Documentation is a contract**: README/docstring examples import no
      `_`-prefixed modules.
- [ ] **No dead code**: new `_`-prefixed functions are either tested (with a
      justified named ignore) or removed.
- [ ] **Diff review**: `git --no-pager diff` contains only intended changes; no
      stray files or debug leftovers.
- [ ] **Commit message**: imperative, ≤ 72-char subject, scoped prefix.

---

## 13. Commit and PR conventions

- Commit messages: **imperative mood**, capitalized, subject ≤ 72 characters.
  - Good: `Add bounded string support to parser`
  - Bad: `fixed bug` / `more changes`
- Scope prefixes are encouraged: `parser:`, `codegen:`, `types:`, `docs:`,
  `test:`, etc.

---

## 14. Typical change walkthroughs

### Scenario A: add a public symbol (e.g. expose a utility)

1. Import it in the owning package's `__init__.py` and add it to `__all__`.
2. Update README (protocol table or examples) and `.rules`.
3. If the generator hardcodes it, update `RUNTIME_CONTRACT` and regenerate
   output in the same change.
4. Add tests (structural/unit), then run `pytest` and `pyright`.
5. Complete the checklist in §12 and commit.

### Scenario B: add a new type form to the generator

1. `parsing/`: update the Lark grammar and `MsgField` model if the field shape
   is new.
2. `semantics/`: add the `resolve_type` branch and the `ResolvedType`
   annotation expression; keep literal/bound handling in the semantic layer.
3. `codegen/`: update `generate_message_module` / wrapper AST and the `.pyi`
   stub; stubs consume `TypeInfo` and must not re-parse annotation strings.
4. `pipeline/`: confirm collection/validation/writing need no adjustment.
5. Tests: parser unit → codegen unit → contract → integration; run the full
   benchmark.
6. If generated output adds a `zros2.*` import, update `RUNTIME_CONTRACT`.

### Scenario C: move a runtime internal module

1. Update relative imports and `__init__.py` re-exports.
2. If the generator hardcodes it (currently only `zros2.types._utils` /
   `from_attributes`), update `RUNTIME_CONTRACT` and regenerate output in the
   same change; otherwise contract tests fail.
3. Confirm README/docstring examples do not reference `_`-prefixed paths.

### Scenario D: change the ROS action transport layout

1. Change **only** `semantics/_action.py`'s `ACTION_SPEC` / `GOAL_ID_TYPE`;
   the parser must not hardcode `uint8[16]` or `SendGoal_*`.
2. Derive codegen suffix tables and pipeline export filtering from that spec;
   do not duplicate them.
3. Runtime Zenoh channel paths live in `endpoints/_action_keys.py`, separate
   from IDL expansion. `_action_msgs.py`'s `goal_id` layout must match
   `GOAL_ID_TYPE`.
4. Add `test_action_expand_unit.py` coverage, then run generator integration
   tests. Changing `GOAL_ID_TYPE` changes the wire format; validate it against
   `zenoh-bridge-ros2dds` first.
