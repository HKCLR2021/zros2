# zros2 — Zenoh ROS 2 Bridge

A lightweight Python library for ROS 2-like communication
over [Zenoh](https://zenoh.io/).

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
![tests](https://github.com/HKCLR2021/zros2/actions/workflows/ci.yml/badge.svg)

---

## Overview

**zros2** provides ROS 2 communication primitives (publishers, subscribers,
service clients, action clients) using **Zenoh** as the underlying transport
middleware. Message types are statically generated from `.msg` / `.srv` /
`.action` files via the bundled `zros2-gen` code generator and serialized
with `pycdr2` (CDR).

### Design Positioning

**zros2** is designed to be used **together with `zenoh-plugin-ros2dds` /
`zenoh-bridge-ros2dds`**: the bridge translates ROS 2 DDS traffic into Zenoh
on the ROS 2 side, and zros2 is the counterpart implementation on the Zenoh
side — letting systems that do **not** run ROS 2 communicate directly with
ROS 2 systems.

- **Interfaces modeled after rclpy** — the client and endpoints follow the
  structure of the ROS 2 reference implementation, so ROS 2 developers get
  up to speed almost instantly.
- **Serialization via pycdr2** — `.msg` / `.srv` / `.action` files are
  statically compiled into typed Python dataclasses: IDE-friendly, no
  runtime type-resolution overhead, high performance.
- **Lightweight by design** — aimed at upper-layer systems (robot
  applications, cloud services, test frameworks, …) that must talk to ROS 2
  systems directly without depending on ROS 2 implementations such as rclpy.
- **Capability boundary** — zros2 provides service / action **client**
  capabilities only; it deliberately does **not** provide service / action
  **server** functionality callable from the ROS 2 side (servers are hosted
  by ROS 2 nodes and exposed through the bridge). This is a design choice,
  not a missing feature.

### Features

- **Spec-compliant parser** — `.msg` / `.srv` / `.action` files are fully
  parsed per the ROS 2 interface spec, including all 15 built-in types,
  fixed/bounded/unbounded arrays, bounded strings, constant-reference bounds
  (`int32[COUNT]`, `string<=MAX_LEN`, `sequence<uint8,N>`), nested types,
  and default-value expressions.
- **rclpy-compatible codegen** — type resolution and code emission match
  the behaviour of ROS 2's reference Python implementation.
- **Static message types** — generate Python dataclasses with full IDE type
  hints (`.pyi` stubs included).
- **Zenoh transport** — publish, subscribe, service call, and action
  communication over Zenoh.
- **Runtime type registry** — look up types by string name at runtime
  (`get_type`, `get_service`, `get_action`).
- **CDR serialization** — via `pycdr2`, with bounds enforced at
  serialisation time.
- **Protocols for type safety** — `RosMessage`, `RosService`, `RosAction`
  protocols for static type checking.
- **Optional asyncio facade** — `zros2.asyncio.AsyncRobotClient` adapts
  the threaded action, service, and liveliness APIs for asyncio
  consumers, with typed feedback and result events for actions.
- **Bundled ROS 2 definitions** — built-in types for Humble through Lyrical
  are included; no external download required.

---

## Installation

```bash
pip install zros2
```

Or install in editable mode for development:

```bash
pip install -e ".[dev]"
```

---

## Usage

### 1. Generate message types

Generate Python message classes from `.msg` / `.srv` / `.action` files:

```bash
zros2-gen \
  --msg-dirs ./my_msgs/my_package \
  --ros-version humble \
  --root-package zros2_msgs \
  --output ./zros2_msgs
```

All standard ROS 2 built-in types (`std_msgs`, `geometry_msgs`, `builtin_interfaces`,
etc.) for the selected distro are automatically bundled.

### 2. Publish / Subscribe

```python
from zros2 import Publisher, Subscriber
from zros2_msgs.std_msgs.msg import String
from zros2_msgs.builtin_interfaces.msg import Time
from zros2_msgs.geometry_msgs.msg import Twist, Vector3
from zros2_msgs.my_package.msg import MyMessage

# Publish
pub = Publisher(session, topic="/chatter", message_type=String)
pub.publish(String(data="hello"))

# Publish nested types
pub_twist = Publisher(session, topic="/cmd_vel", message_type=Twist)
pub_twist.publish(Twist(
    linear=Vector3(x=0.5, y=0.0, z=0.0),
    angular=Vector3(x=0.0, y=0.0, z=0.0),
))

# Subscribe
def callback(msg: MyMessage):
    print(f"Received: {msg}")

sub = Subscriber(session, topic="/battery", message_type=MyMessage)
sub.subscribe(callback)
```

### 3. Services

Services are defined via `.srv` files. The generated module exports `Request`
and `Response` message classes plus the parent service class.

```python
from zros2 import ServiceClient
from zros2.types import ServiceTypes
from zros2_msgs.my_package.srv import MyService

# Pass the service type *class* — it satisfies the RosService protocol
srv = ServiceClient(
    session,
    service_name="/add_two_ints",
    service_type=MyService,
)
result: MyService.Response = srv.send_request(MyService.Request(a=10, b=20))
print(result)  # MyService.Response(sum=30)
```

Using the `ServiceTypes` container (alternative):

```python
srv = ServiceClient(
    session,
    service_name="/add_two_ints",
    service_type=ServiceTypes(MyService.Request, MyService.Response),
)
result = srv.send_request(MyService.Request(a=10, b=20))
```

### 4. Actions

Actions are defined via `.action` files (goal / result / feedback sections).
One `.action` file compiles into a single generated module holding **eight**
sub-types plus a wrapper class:

| Generated name                                     | Purpose                                           |
| -------------------------------------------------- | ------------------------------------------------- |
| `Foo_Goal` / `Foo_Result` / `Foo_Feedback`         | User-facing goal / result / feedback payloads     |
| `Foo_FeedbackMessage`                              | Feedback transport (goal_id + feedback)           |
| `Foo_SendGoal_Request` / `Foo_SendGoal_Response`   | Internal SendGoal service pair                    |
| `Foo_GetResult_Request` / `Foo_GetResult_Response` | Internal GetResult service pair                   |
| `Foo`                                              | Wrapper class satisfying the `RosAction` protocol |

Pass the wrapper class directly as the action type:

```python
from zros2 import Action
from zros2_msgs.my_package.action import Fibonacci

action = Action(
    session,
    action_name="/fibonacci",
    action_type=Fibonacci,
    timeout=5000,
)

# Send a goal and get the result (each send_goal gets a fresh goal ID)
handle = action.send_goal(Fibonacci.Goal(order=10))
result = action.get_result(handle)
```

`send_goal` returns a `GoalHandle` carrying the goal's unique 16-byte ID
and whether the server accepted it. An `Action` instance can be reused
for multiple goals, and feedback callbacks only receive feedback for
goals sent through that client (filtered by `goal_id`). Following ROS 2
semantics, `get_result` blocks until the goal terminates; pass a
`timeout` in milliseconds to bound the wait (`None` waits indefinitely).

Goals can be cancelled and lifecycle status observed:

```python
from zros2 import GoalStatus, CancelGoal_Response

# Cancel one goal, or all active goals (returns an ERROR_* code)
result = action.cancel_goal(handle)
result = action.cancel_all_goals()
if result.return_code != CancelGoal_Response.ERROR_NONE:
    print("cancel failed:", result.return_code)

# Track the goal lifecycle via the /action/status topic
statuses = []
action.status_callback = lambda array: statuses.append(array)
# each array.status_list entry carries a GoalStatus.STATUS_* code
```

The `action_msgs` message types (`GoalInfo`, `GoalStatus`,
`GoalStatusArray`, `CancelGoal_Request`, `CancelGoal_Response`) are
built into zros2 and exported at the top level — cancellation and
status observation therefore need no generated code at all.

The client talks to the action server over five Zenoh keys:

| Key                            | Direction       | Payload type                                |
| ------------------------------ | --------------- | ------------------------------------------- |
| `{action}/_action/send_goal`   | client → server | generated `SendGoal_Request` / `_Response`  |
| `{action}/_action/get_result`  | client → server | generated `GetResult_Request` / `_Response` |
| `{action}/_action/cancel_goal` | client → server | built-in `CancelGoal_Request` / `_Response` |
| `{action}/_action/feedback`    | server → client | generated `FeedbackMessage`                 |
| `{action}/_action/status`      | server → client | built-in `GoalStatusArray`                  |

Feedback and status subscriptions are **lazy**: the feedback topic is
subscribed on the first `send_goal` when a `feedback_callback` is set,
and the status topic only when a `status_callback` is assigned. Use the
action as a context manager to tear both subscriptions down on exit:

```python
with action:
    handle = action.send_goal(Fibonacci.Goal(order=10))
    result = action.get_result(handle)
# feedback/status subscriptions released
```

When using `ZRosClient`, create actions with `client.create_action_client(...)`
(namespace-aware) — see section 5 below.

Using the `ActionTypes` container:

```python
from zros2 import Action
from zros2.types import ActionTypes

action = Action(
    session,
    action_name="/fibonacci",
    action_type=ActionTypes(
        Goal=Fibonacci.Goal,
        Result=Fibonacci.Result,
        Feedback=Fibonacci.Feedback,
        FeedbackMessage=Fibonacci.FeedbackMessage,
        SendGoal_Request=Fibonacci.SendGoal_Request,
        SendGoal_Response=Fibonacci.SendGoal_Response,
        GetResult_Request=Fibonacci.GetResult_Request,
        GetResult_Response=Fibonacci.GetResult_Response,
    ),
)
```

For an asyncio-style `async for` stream of feedback and result events,
see section 10 below.

### 5. Using the client factory

`ZRosClient` provides a unified entry point that manages the Zenoh session
and creates communication primitives with namespace support.

```python
from zros2 import ZRosClient
from zros2.types import RosService, RosAction
from zros2_msgs.std_msgs.msg import String
from zros2_msgs.my_package.srv import MyService
from zros2_msgs.my_package.action import Fibonacci

client = ZRosClient("./zenoh.json5")

pub = client.create_publisher("/chatter", String, namespace="robot_01")
sub = client.create_subscriber("/battery", String, namespace="robot_01")
srv = client.create_service_client(
    "/add", MyService,
    namespace="robot_01",
)
act = client.create_action_client(
    "/fib", Fibonacci,
    namespace="robot_01",
)
```

All factory methods require an explicit `namespace` argument. Pass
`namespace=""` to use un-namespaced topics.

`ZRosClient` owns the Zenoh session. Release it with `close()`
(idempotent — safe to call multiple times) or use the client as a
context manager:

```python
with ZRosClient("./zenoh.json5") as client:
    ...
# session closed on exit
```

Service availability can be probed through Zenoh liveliness tokens
(no service type class needed) — the server declares a `SERVICE_SERVER`
token for its name, and the probe matches **both** name and type:

```python
# Blocks until a server of this exact type appears
# (timeout_ms=None waits indefinitely)
srv_type = MyService.__ros_name__  # e.g. "my_pkg/srv/MyService"
if not client.wait_for_service("/add", srv_type, timeout_ms=5000):
    raise TimeoutError("service not available")

# Non-blocking probe
if client.service_is_ready("/add", srv_type):
    result = srv.send_request(MyService.Request(a=10, b=20))
```

### 6. Runtime reflection

The generated package root (`zros2_msgs`) provides runtime type lookup:

```python
from zros2_msgs import get_type, get_service, get_action, has_type, iter_types

# Look up types by string name
String = get_type("std_msgs/msg/String")
Srv = get_service("my_pkg/srv/MyService")
Act = get_action("my_pkg/action/MyAction")

# Check existence
if has_type("std_msgs/msg/Header"):
    ...

# List all registered types
for name in iter_types():
    print(name)
```

### 7. Dict conversion

Every generated message provides `to_dict()` and `from_dict()`:

```python
msg = String(data="hello")
d = msg.to_dict()              # {"data": "hello"}
restored = String.from_dict(d)
```

Messages also provide `from_attributes()` for converting from arbitrary
attribute-based objects:

```python
class Obj:
    data = "world"

restored = String.from_attributes(Obj)
```

### 8. Liveliness & Discovery

Monitor ROS 2 entity presence over Zenoh:

```python
from zros2 import LivelinessType, Qos, ZRosClient

client = ZRosClient("./zenoh.json5")

# Discover all publishers on /chatter
lv = client.create_liveliness(
    LivelinessType.PUBLISHER,
    name="/chatter",
    ros2_type="std_msgs/msg/String",
    qos=Qos.any(),
)

# Query currently alive entities
samples = lv.get()

# Subscribe to liveliness changes
lv.subscribe(lambda sample: print(f"Entity changed: {sample}"))
```

### 9. Exception handling

All zros2 exceptions inherit from `ZRos2Exception`:

```python
from zros2.exceptions import (
    ZRos2Exception,
    ServiceException,
    ServiceNotAvailableException,
    ServiceInvokeException,
    ActionException,
    ActionInvokeException,
    ActionNotAvailableException,
)

try:
    result = srv.send_request(MyService.Request(a=10, b=20))
except ServiceNotAvailableException:
    print("Service is not available")
except ServiceInvokeException:
    print("Service invocation failed")
except ServiceException:
    print("Generic service error")
```

### 10. Async invocation (`zros2.asyncio`)

The core zros2 API is synchronous. For asyncio applications, the
optional `zros2.asyncio` subpackage adapts the threaded clients into
the event loop: blocking calls run in worker threads, so actions and
topic streams can be consumed with `async for` and service calls can
be awaited directly.
`AsyncRobotClient` binds a `ZRosClient` (or session proxy) once, so
repeated invocations do not need to thread the client through every
call.

```python
from zros2 import ZRosClient
from zros2.asyncio import ActionFeedback, ActionResult, AsyncRobotClient
from zros2_msgs.my_package.action import Fibonacci
from zros2_msgs.my_package.srv import QueryTrajectory

client = ZRosClient("./zenoh.json5")
zros = AsyncRobotClient(client)

async def run() -> None:
    # Service call: returns the typed response dataclass.
    response = await zros.invoke_service(
        "/query_trajectory", QueryTrajectory,
        timeout=5000,
        namespace="robot_01",
    )

    # Action: yields feedback updates, then the final result.
    async for event in zros.invoke_action(
        "/fib", Fibonacci,
        goal=Fibonacci.Goal(order=10),
        namespace="robot_01",
    ):
        if isinstance(event, ActionFeedback):
            print("feedback:", event.feedback)
        elif isinstance(event, ActionResult):
            print("status:", event.status, "result:", event.result)
```

`invoke_action` yields an `ActionFeedback` for every update and finally
one `ActionResult`. It raises `ActionInvokeException` when the goal is
rejected or a send-goal / get-result service call fails. Feedback is
dropped (bounded queue, oldest first) when the consumer is slower than
the server. `invoke_service` returns the typed response (or an empty
request when `body` is `None`) and raises the regular
`ServiceInvokeException` / `ServiceNotAvailableException` on failure.

For entity discovery, `query_liveliness` runs the blocking liveliness
query on a worker thread and returns the currently alive entities,
while `watch_liveliness` bridges the Zenoh-thread subscription
callback into an `async for` stream of changes (call `query_liveliness`
first for the snapshot):

```python
from zros2 import LivelinessType

async def monitor() -> None:
    alive = await zros.query_liveliness(
        LivelinessType.SERVICE_SERVER,
        name="/trigger", ros2_type="std_srvs/srv/Trigger",
        namespace="robot_01",
    )
    async for sample in zros.watch_liveliness(
        LivelinessType.ACTION_SERVER, namespace="robot_01"
    ):
        print("change:", sample)
```

Publish / subscribe is available through the `AsyncPublisher` and
`AsyncSubscriber` endpoints, created by the same factory methods the
sync client exposes:

```python
from zros2_msgs.std_msgs.msg import String

async def pubsub() -> None:
    # Async publish: declare once, publish many — blocking work runs
    # on worker threads.
    pub = zros.create_publisher("/chatter", String, namespace="robot_01")
    await pub.publish(String(data="hello"))
    await pub.aclose()  # idempotent

    # Async subscribe: async-for stream bridged from Zenoh threads.
    sub = zros.create_subscriber("/battery", String, namespace="robot_01")
    async for msg in sub:  # subscribes lazily on first iteration
        print("received:", msg.data)
        break
    await sub.aclose()
```

Like the liveliness watcher, the subscriber forwards messages through a
bounded queue — entries are dropped (oldest first) when the consumer is
slower than the topic. `aclose()` ends the stream and undeclares the
subscription.

---

## Parser compliance

The `zros2-gen` generator parses ROS 2 interface files per the
[ROS 2 Interface specification](https://docs.ros.org/en/humble/Concepts/Basic/About-Interfaces.html).

### Supported type forms

| Category                | Syntax                                     | Bound checking    |
| ----------------------- | ------------------------------------------ | ----------------- |
| Primitives              | `int32`, `float64`, `string`, `wstring`, … | —                 |
| Fixed array             | `int32[3]`                                 | —                 |
| Fixed array (const ref) | `int32[COUNT]`                             | —                 |
| Unbounded array         | `int32[]`                                  | —                 |
| Bounded array           | `int32[<=5]` / `int32[<=MAX]`              | ✅ serialise-time |
| Bounded string          | `string<=255` / `string<=MAX_LEN`          | ✅ serialise-time |
| Sequence                | `sequence<uint8>`                          | —                 |
| Bounded sequence        | `sequence<uint8,10>` / `sequence<uint8,N>` | ✅ serialise-time |
| Nested type             | `std_msgs/String`                          | —                 |

---

## Type System

The `zros2.types` subpackage defines the structural type system:

| Protocol / Type                            | Purpose                                                                                                                     |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `RosMessage`                               | Base protocol for all message dataclasses (`serialize()`, `deserialize()`, `to_dict()`, `from_dict()`, `from_attributes()`) |
| `RosService[ReqT, ResT]`                   | Protocol for service types (requires `ClassVar` members `Request` and `Response`)                                           |
| `RosAction[...]`                           | Protocol for action types (8 `ClassVar` message members)                                                                    |
| `RosActionView[GoalT, ResultT, FeedbackT]` | Semantic action view — the 3 user-facing message types, hiding transport sub-types (`SendGoal_*`, `GetResult_*`)            |
| `ServiceTypes`                             | Frozen dataclass container holding `Request` and `Response` types                                                           |
| `ActionTypes`                              | Frozen dataclass container holding all 8 action message types                                                               |

### Generics

Generic classes and functions declare their type parameters locally with
PEP 695 syntax, bound to `RosMessage` — no shared TypeVars are exported:

```python
from zros2.types import RosMessage

# Class-level: declare once, reference by name in methods
class ActionInvoker[
    GoalT: RosMessage, ResultT: RosMessage, FeedbackT: RosMessage,
]: ...

# Function-level
async def observe_action[
    GoalT: RosMessage, ResultT: RosMessage, FeedbackT: RosMessage,
](
    action_type: type[RosActionView[GoalT, ResultT, FeedbackT]],
    goal: GoalT | None = None,
) -> None: ...
```

---

## Generator architecture

`zros2-gen` follows a four-phase pipeline:

```
  .msg / .srv / .action  files
           │
           ▼
    ┌─────────────┐
    │   parsing    │  Lark grammar → IR models (MsgField, MsgDefinition)
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │  semantics   │  Type resolution, default-value computation
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │   codegen    │  Python ast → source (dataclasses + .pyi stubs)
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │  pipeline    │  Plan orchestration, validation, file writing
    └─────────────┘
           │
           ▼
   generated Python modules
```

### CLI

```
usage: zros2-gen [-h] --msg-dirs MSG_DIRS --output OUTPUT
                 --ros-version {humble,iron,jazzy,kilted,lyrical}
                 [--root-package ROOT_PACKAGE] [--dry-run]
```

| Option           | Description                                                                           |
| ---------------- | ------------------------------------------------------------------------------------- |
| `--msg-dirs`     | One or more ROS 2 package directories containing `msg/`, `srv/`, `action/` subfolders |
| `--output`       | Output directory for generated Python source files                                    |
| `--ros-version`  | ROS 2 distribution whose builtin types to bundle (required)                           |
| `--root-package` | Top-level package name (defaults to output dir name)                                  |
| `--dry-run`      | Print file list without writing                                                       |

### Programmatic API

```python
from zros2.generator.parsing import parse_msg_text, MsgDefinition
from zros2.generator.semantics import resolve_type
from zros2.generator.codegen import (
    generate_message_module,
    generate_init_module,
    generate_stub_module,
    GeneratedFile,
)
from zros2.generator.pipeline import generate_all
```

### Codegen ↔ runtime ABI

Generated modules hardcode imports of a small set of runtime symbols:
`zros2.types` (`RosMessage`, `ServiceTypes`, `ActionTypes`) and
`zros2.types._utils` (`from_attributes`). Those references form a
**generation ABI** — renaming or moving a symbol breaks already-
generated code, so the two sides are pinned to each other by the
`RUNTIME_CONTRACT` whitelist in `tests/test_runtime_contract.py`.
Change the whitelist in the same change that moves either side.

---

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run specific test file
pytest tests/test_parser_unit.py -v

# Run benchmarks
pytest benchmarks/ --benchmark-only
```

The test suite covers:

- **Parser unit tests** — grammar, type expressions, field-level parsing
- **Codegen unit tests** — message modules, init modules, stubs, service/action modules, registry
- **Pipeline unit tests** — plan build, orchestration, validation
- **Endpoint unit tests** — publisher, subscriber, service client, action client
- **Client unit tests** — `ZRosClient` factory methods
- **Protocol tests** — structural typing for `RosMessage`, `RosService`, `RosAction`
- **Integration tests** — end-to-end generation + verification
- **Type system tests** — type grammar, type map, default values, primitives
- **Liveliness/discovery tests** — key expression building and parsing

---

## License

Proprietary — all rights reserved.
