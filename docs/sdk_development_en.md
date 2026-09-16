# zros2 SDK Development Guide (For Users)

> Applies to: **zros2 2.0.0** · Python ≥ 3.12
> This guide is for developers building applications on top of zros2. For the internal architecture and contribution guide, see [developer_guide.md](./developer_guide.md). 中文版见 [sdk_development.md](./sdk_development.md).

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Installation](#2-installation)
3. [Generating Message Types](#3-generating-message-types)
4. [Client Lifecycle](#4-client-lifecycle)
5. [Publish / Subscribe](#5-publish--subscribe)
6. [Services](#6-services)
7. [Actions](#7-actions)
8. [Liveliness & Discovery](#8-liveliness--discovery)
9. [Type System](#9-type-system)
10. [Runtime Reflection & Data Conversion](#10-runtime-reflection--data-conversion)
11. [Exception Handling](#11-exception-handling)
12. [Async Development (`zros2.asyncio`)](#12-async-development-zros2asyncio)
13. [Best Practices](#13-best-practices)
14. [API Quick Reference](#14-api-quick-reference)
15. [FAQ](#15-faq)

---

## 1. Introduction

zros2 is a lightweight ROS 2-like communication library built on [Zenoh](https://zenoh.io/). It provides publish/subscribe, service-call, and action-call primitives. Message types are statically generated from `.msg` / `.srv` / `.action` files by the bundled `zros2-gen` code generator and serialized with `pycdr2` (CDR), remaining compatible with the ROS 2 ecosystem.

### Design Positioning

zros2 is designed to be used **together with `zenoh-plugin-ros2dds` / `zenoh-bridge-ros2dds`**: on the ROS 2 side, the bridge plugin translates DDS traffic into Zenoh; zros2 is the counterpart implementation on the Zenoh side, letting systems that do **not** run ROS 2 communicate directly with ROS 2 systems.

- **Interfaces modeled after rclpy**: the client (`ZRosClient`) and endpoints (publisher / subscriber / service client / action client) follow the structure of the ROS 2 reference implementation, so ROS 2 developers get up to speed almost instantly.
- **Serialization via pycdr2**: the `zros2-gen` generator statically compiles `.msg` / `.srv` / `.action` files into Python dataclasses with full type annotations — IDE-friendly, no runtime type-resolution overhead, and high performance.
- **Lightweight by design**: aimed at upper-layer systems (robot applications, cloud services, test frameworks, …) that must talk to ROS 2 systems directly without depending on ROS 2 implementations such as rclpy.
- **Capability boundary**: zros2 provides service / action **client** capabilities; it deliberately does **not** provide service / action **server** functionality callable from the ROS 2 side (servers are hosted by ROS 2 nodes and exposed through the bridge). This is a design choice, not a missing feature.

### Key Features

| Feature                   | Description                                                                                     |
| ------------------------- | ----------------------------------------------------------------------------------------------- |
| Static message types      | Generated Python dataclasses with full type annotations and `.pyi` stubs — complete IDE support |
| Zenoh transport           | Publish, subscribe, service, and action communication over Zenoh, with device namespaces        |
| Type-safety protocols     | Structural protocols `RosMessage` / `RosService` / `RosAction` friendly to static type checkers |
| Runtime type registry     | Generated packages support reflection lookup by string name (`get_type`, etc.)                  |
| Bundled ROS 2 definitions | Built-in types for Humble through Lyrical ship with the library — no download needed            |
| CDR serialization         | Bounds of bounded types are enforced at serialization time                                      |
| Optional asyncio facade   | `zros2.asyncio.AsyncRobotClient` adapts the blocking API to the event loop                      |

---

## 2. Installation

```bash
pip install zros2
```

Editable install with dev dependencies:

```bash
pip install -e ".[dev]"
```

Runtime dependencies: `eclipse-zenoh>=1.9.0`, `pycdr2>=1.0.0`, `numpy>=2.4.6`, `lark>=1.3.0`.

---

## 3. Generating Message Types

### 3.1 CLI Usage

```bash
zros2-gen \
  --msg-dirs ./my_msgs/my_package \
  --ros-version humble \
  --root-package zros2_msgs \
  --output ./zros2_msgs
```

`--msg-dirs` also accepts a workspace root (immediate children that contain `msg/`, `srv/`, or `action/`):

```bash
zros2-gen --msg-dirs ./my_msgs --ros-version humble --output ./zros2_msgs
```

| Option            | Description                                                                                                    |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| `--msg-dirs`      | One or more ROS 2 package directories (`msg/`, `srv/`, and/or `action/`), or a workspace of such packages      |
| `--output` / `-o` | Output directory for generated Python sources                                                                  |
| `--ros-version`   | ROS 2 distro that decides which built-in types are bundled: `humble` / `iron` / `jazzy` / `kilted` / `lyrical` |
| `--root-package`  | Top-level package name (defaults to the output dir name; pass `--root-package ""` to drop the prefix)          |
| `--dry-run`       | Print the generated file list without writing anything                                                         |

Equivalent module entry point: `python -m zros2.generator --msg-dirs ... --output ... --ros-version humble`.

All standard built-in types for the selected distro (`std_msgs`, `geometry_msgs`, `builtin_interfaces`, …) are bundled automatically; user types override builtins of the same name.

### 3.2 Generated Output

Each message produces a `.py` module plus a `.pyi` stub; services/actions produce merged wrapper modules carrying the `Request` / `Response` and `Goal` / `Result` / `Feedback` message classes. The generated package root `__init__.py` exposes runtime-reflection functions (see §10).

Generated code imports a fixed set of zros2 runtime symbols (the generation ABI) — do not edit it by hand; regenerate to overwrite.

### 3.3 Programmatic Generation

```python
from pathlib import Path
from zros2.generator import expand_action, parse_action_file, parse_msg_file, generate_all

defs = parse_msg_file(Path("my_msgs/my_package/msg/MyMessage.msg"), package="my_package")
files = generate_all({"my_package/msg/MyMessage": defs}, Path("./out"))
for f in files:
    f.path.parent.mkdir(parents=True, exist_ok=True)
    f.path.write_text(f.content, encoding="utf-8")

# .action: the parser returns Goal / Result / Feedback only; expand_action adds transport types
source = parse_action_file(Path("my_msgs/my_package/action/Fibonacci.action"), package="my_package")
action_types = {d.full_name: d for d in expand_action(source)}
```

`zros2.generator` also exports `parse_msg_text`, `parse_srv_file`, `ActionSource`, `MsgDefinition`, `MsgField`, `resolve_type`, `ResolvedType`, `VALID_DISTROS`. Generated action packages re-export the wrapper plus `Goal` / `Result` / `Feedback`; `SendGoal_*` / `GetResult_*` / `FeedbackMessage` stay in the module but are omitted from `action/__init__.py`.

---

## 4. Client Lifecycle

`ZRosClient` is the unified entry point: it owns the underlying Zenoh session and creates communication primitives via factory methods.

```python
from zros2 import ZRosClient

# Accepts a JSON5 Zenoh config file path or a zenoh.Config object.
client = ZRosClient("./zenoh.json5")

pub = client.create_publisher("/chatter", String, namespace="robot_01")
srv = client.create_service_client("/add", MyService, namespace="robot_01")

client.close()   # idempotent; safe to call multiple times
```

Prefer the context manager — the session is closed on exit:

```python
with ZRosClient("./zenoh.json5") as client:
    ...
# session closed here
```

### Namespaces

Every factory method accepts a keyword-only `namespace` parameter (default `""`). A non-empty namespace prefixes the topic/service/action name with `{namespace}/`; an empty string means no prefix. Entities with the same name in different namespaces are isolated — useful for multi-device deployments.

> Note: the `client.session` property returns a protected `ZenohSessionProxy`. Destructive operations (`close()`, `undeclare()`, …) are forbidden on it; pass it to endpoint classes as the session when constructing them directly (e.g. `Publisher(session, ...)`).

---

## 5. Publish / Subscribe

### 5.1 Publishing

```python
from zros2 import ZRosClient
from zros2_msgs.geometry_msgs.msg import Twist, Vector3

client = ZRosClient("./zenoh.json5")

pub = client.create_publisher("/cmd_vel", Twist, namespace="robot_01")
pub.publish(Twist(
    linear=Vector3(x=0.5, y=0.0, z=0.0),
    angular=Vector3(x=0.0, y=0.0, z=0.0),
))
pub.destroy()   # idempotent
```

- `publish(data)` takes a message instance and serializes it to CDR bytes internally (`data.serialize()`).
- The publisher is declared at construction time; `publish` after `destroy()` raises `RuntimeError`.
- Direct construction is also supported: `Publisher(session, topic="/chatter", message_type=String)` (`session` from `client.session`).

### 5.2 Subscribing

```python
from zros2_msgs.my_package.msg import MyMessage

def callback(msg: MyMessage) -> None:
    print(f"Received: {msg}")

sub = client.create_subscriber("/battery", MyMessage, namespace="robot_01")
sub.subscribe(callback)
...
sub.unsubscribe()   # idempotent; close() is a synonym
```

Important constraints:

- **Callbacks run on Zenoh threads**: keep them fast and non-blocking, and make them **synchronous**. Passing an async function is rejected (`TypeError`, logged).
- A second `subscribe()` raises `ValueError` (call `unsubscribe()` first); a closed session raises `RuntimeError`.
- Messages are deserialized and type-checked before your callback runs; deserialization failures are logged and do not break the subscription.

---

## 6. Services

Service types are generated from `.srv` files; the wrapper class carries the `Request` and `Response` message classes.

```python
from zros2 import ZRosClient
from zros2_msgs.my_package.srv import MyService

client = ZRosClient("./zenoh.json5")
srv = client.create_service_client("/add", MyService, namespace="robot_01")

result: MyService.Response = srv.send_request(
    MyService.Request(a=10, b=20),  # pass None for an empty request
    timeout=1000,                   # milliseconds; None waits forever
)
print(result.sum)
```

- `send_request` has a default timeout of 1000 ms; `timeout=None` waits indefinitely.
- A `ServiceTypes` container can be passed instead of the service class: `ServiceTypes(Request=MyService.Request, Response=MyService.Response)`.

### Service Readiness

Servers declare a `SERVICE_SERVER` liveliness token; readiness probes match **both name and type exactly** (no service type class needed — a type string suffices):

```python
srv_type = MyService.__ros_name__   # e.g. "my_pkg/srv/MyService"

# Block until ready; False on timeout. timeout_ms=None waits indefinitely.
if not client.wait_for_service("/add", srv_type, timeout_ms=5000, namespace="robot_01"):
    raise TimeoutError("service not available")

# Non-blocking probe
if client.service_is_ready("/add", srv_type, namespace="robot_01"):
    result = srv.send_request(MyService.Request(a=10, b=20))
```

Note: service/action liveliness tokens carry no QoS, so these probes have no `qos` parameter.

### Errors

- Server returns an error → `ServiceInvokeException`
- No response within the timeout → `ServiceNotAvailableException`
- Zenoh communication error → `ServiceInvokeException` (chained from the underlying error)

---

## 7. Actions

Action types are generated from `.action` files (goal / result / feedback sections). The generated module contains eight sub-types (including the `FeedbackMessage`, `SendGoal_*`, and `GetResult_*` transport types); `action/__init__.py` re-exports only the wrapper and the user-facing `Goal` / `Result` / `Feedback`.

```python
from zros2 import ZRosClient
from zros2_msgs.my_package.action import Fibonacci

client = ZRosClient("./zenoh.json5")
action = client.create_action_client(
    "/fib", Fibonacci,
    timeout=5000,               # milliseconds, default 3000; bounds the send_goal RPC
    namespace="robot_01",
)

# Send a goal: every call generates a fresh goal_id
handle = action.send_goal(Fibonacci.Goal(order=10))
print(handle.accepted)          # whether the server accepted the goal

# Get the result: blocks until the goal terminates (ROS 2 semantics);
# timeout=None waits indefinitely
result = action.get_result(handle)
```

### Feedback & Status

```python
# Feedback callback: receives only feedback for goals sent through this
# client (filtered by goal_id). Set it BEFORE send_goal. The callback
# runs on a Zenoh thread — keep it light.
action.feedback_callback = lambda feedback: print("feedback:", feedback)

# Status callback: receives every GoalStatusArray on the action status topic
statuses: list = []
action.status_callback = lambda array: statuses.append(array)
# each array.status_list entry carries a GoalStatus.STATUS_* code
```

`GoalStatus` constants: `STATUS_UNKNOWN=0`, `STATUS_ACCEPTED=1`, `STATUS_EXECUTING=2`, `STATUS_CANCELING=3`, `STATUS_SUCCEEDED=4`, `STATUS_CANCELED=5`, `STATUS_ABORTED=6`.

### Cancellation

```python
from zros2 import CancelGoal_Response

# Cancel one goal, or all active goals
r1 = action.cancel_goal(handle)
r2 = action.cancel_all_goals()
if r1.return_code != CancelGoal_Response.ERROR_NONE:
    print("cancel failed:", r1.return_code)
```

`CancelGoal_Response` constants: `ERROR_NONE=0`, `ERROR_REJECTED=1`, `ERROR_UNKNOWN_GOAL=2`, `ERROR_GOAL_TERMINATED=3`.

### Notes

- `Action` is a context manager: entering establishes the feedback/status subscriptions lazily; exiting unsubscribes automatically.
- Action-related failures raise `ActionInvokeException`.
- The built-in `action_msgs` messages (`GoalInfo`, `GoalStatus`, `GoalStatusArray`, `CancelGoal_Request`, `CancelGoal_Response`) are exported at the zros2 top level.
- An `ActionTypes` container can replace the action class (fields: `Goal` / `Result` / `Feedback` / `FeedbackMessage` / `SendGoal_Request` / `SendGoal_Response` / `GetResult_Request` / `GetResult_Response`).

---

## 8. Liveliness & Discovery

Discover the online status of ROS 2 entities (publishers, subscribers, service servers/clients, action servers/clients) through Zenoh liveliness tokens.

```python
from zros2 import LivelinessType, Qos, ZRosClient

client = ZRosClient("./zenoh.json5")

# Discover all publishers on /chatter (optionally constrained by type and QoS)
lv = client.create_liveliness(
    LivelinessType.PUBLISHER,
    name="/chatter",
    ros2_type="std_msgs/msg/String",
    qos=Qos.any(),   # wildcard — matches any QoS
    namespace="robot_01",
)

# Query currently alive entities: returns a list of zenoh.Sample
samples = lv.get()

# Subscribe to liveliness *changes* (up/down events); not the current snapshot
lv.subscribe(lambda sample: print(f"entity changed: {sample}"))
lv.close()   # idempotent; also supports `with` statements
```

### Entity Types (`LivelinessType`)

`ALL`, `PLUGIN`, `PUBLISHER`, `SUBSCRIBER`, `SERVICE_SERVER`, `SERVICE_CLIENT`, `ACTION_SERVER`, `ACTION_CLIENT`.

### QoS

`Qos` fields: `reliability`, `durability`, `history_kind`, `history_depth`, `user_data`; `Qos.any()` returns the wildcard (matches any QoS). Only publisher/subscriber liveliness keys carry QoS; service/action keys do not.

---

## 9. Type System

`zros2.types` defines the structural type system: generated message classes and downstream types satisfy the protocols **structurally**, without inheriting from zros2.

| Protocol / Type                                                                | Purpose                                                                                                                         |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `RosMessage`                                                                   | Base protocol for all message dataclasses (`serialize()` / `deserialize()` / `to_dict()` / `from_dict()` / `from_attributes()`) |
| `RosService[ReqT, ResT]`                                                       | Protocol for service types (requires `ClassVar` members `Request` and `Response`)                                               |
| `RosAction[SGReqT, SGResT, GRReqT, GRResT, FBMsgT, GoalT, ResultT, FeedbackT]` | Protocol for action types (8 `ClassVar` message members)                                                                        |
| `RosActionView[GoalT, ResultT, FeedbackT]`                                     | Semantic view of an action: only the 3 user-facing types, hiding transport sub-types (`SendGoal_*`, `GetResult_*`)              |
| `ServiceTypes`                                                                 | Frozen dataclass container holding `Request` and `Response` types                                                               |
| `ActionTypes`                                                                  | Frozen dataclass container holding all 8 action message types                                                                   |

### Generics

Generic classes and functions declare their type parameters locally with PEP 695 syntax, bound to `RosMessage` — no shared TypeVars are exported:

```python
from zros2.types import RosMessage, RosActionView

# Class-level generics
class ActionInvoker[
    GoalT: RosMessage, ResultT: RosMessage, FeedbackT: RosMessage,
]: ...

# Function-level generics
async def observe_action[
    GoalT: RosMessage, ResultT: RosMessage, FeedbackT: RosMessage,
](
    action_type: type[RosActionView[GoalT, ResultT, FeedbackT]],
    goal: GoalT | None = None,
) -> None: ...
```

---

## 10. Runtime Reflection & Data Conversion

The generated package root module provides runtime type lookup:

```python
from zros2_msgs import get_type, get_service, get_action, has_type, iter_types

String = get_type("std_msgs/msg/String")
Srv = get_service("my_pkg/srv/MyService")
Act = get_action("my_pkg/action/MyAction")

if has_type("std_msgs/msg/Header"):
    ...

for name in iter_types():
    print(name)
```

Every generated message supports dict and attribute conversion:

```python
msg = String(data="hello")
d = msg.to_dict()                 # {"data": "hello"}
restored = String.from_dict(d)

class Obj:
    data = "world"

restored = String.from_attributes(Obj)
```

---

## 11. Exception Handling

All zros2 exceptions inherit from `ZRos2Exception`:

```
ZRos2Exception
├── ServiceException
│   ├── ServiceNotAvailableException   # service unavailable (timeout, no response)
│   └── ServiceInvokeException         # service invocation failed (error reply / comms)
└── ActionException
    ├── ActionNotAvailableException
    └── ActionInvokeException          # action invocation failed (goal rejected / transport)
```

```python
from zros2.exceptions import (
    ZRos2Exception,
    ServiceException,
    ServiceNotAvailableException,
    ServiceInvokeException,
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

Catch specific exceptions at public boundaries; `ZRos2Exception` is the catch-all fallback.

---

## 12. Async Development (`zros2.asyncio`)

The core API is synchronous and blocking. The optional `zros2.asyncio` facade runs blocking calls on worker threads and bridges Zenoh-thread callbacks into the event loop through bounded queues, so service calls can be `await`ed and actions/topic streams consumed with `async for`.

`AsyncRobotClient` binds a `ZRosClient` (or session proxy) once, so repeated invocations do not need to thread the client through every call:

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

    # Action: yields an ActionFeedback for every update, then one final
    # ActionResult when the action completes.
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

### Discovery

```python
from zros2 import LivelinessType

async def monitor() -> None:
    # Query currently alive entities (blocking query offloaded to a worker thread)
    alive = await zros.query_liveliness(
        LivelinessType.SERVICE_SERVER,
        name="/trigger", ros2_type="std_srvs/srv/Trigger",
        namespace="robot_01",
    )
    # Watch changes: query for the snapshot first, then watch increments
    async for sample in zros.watch_liveliness(
        LivelinessType.ACTION_SERVER, namespace="robot_01",
    ):
        print("change:", sample)
```

### Async Publish / Subscribe

```python
from zros2_msgs.std_msgs.msg import String

async def pubsub() -> None:
    pub = zros.create_publisher("/chatter", String, namespace="robot_01")
    await pub.publish(String(data="hello"))
    await pub.aclose()   # idempotent

    sub = zros.create_subscriber("/battery", String, namespace="robot_01")
    async for msg in sub:   # subscribes lazily on first iteration
        print("received:", msg.data)
        break
    await sub.aclose()      # ends the stream and undeclares the subscription
```

### Behavioral Contract

- Bounded queues have capacity 100: when the consumer is slower than the producer, the **oldest** entries are dropped (subscriber, action feedback, and liveliness watch all behave this way).
- `invoke_action` raises `ActionInvokeException` when the goal is rejected or a send-goal / get-result call fails.
- `invoke_service` with `body=None` sends an empty request; failures raise the regular `ServiceInvokeException` / `ServiceNotAvailableException`.
- Breaking out of the `async for` or closing the generator properly cancels the underlying subscription (the endpoint context manager guarantees undeclare).

---

## 13. Best Practices

1. **Client lifecycle**: manage the session with `with ZRosClient(...)`; never reuse endpoints after closing the shared session.
2. **Namespaces**: in multi-device deployments, use the `namespace` parameter consistently to isolate same-named entities.
3. **Probe before calling**: use `wait_for_service` (with a timeout) or `service_is_ready` before the first service call.
4. **Keep callbacks light**: sync callbacks run on Zenoh threads — no heavy work in callbacks; use `zros2.asyncio` when you need async processing.
5. **Set the action callback first**: set `feedback_callback` before `send_goal`, otherwise no feedback is received (a warning is logged).
6. **Explicit timeouts**: `timeout=None` on `send_request` / `get_result` waits forever — always pass a timeout in production.
7. **Release resources**: endpoints are context managers (or expose `destroy()` / `unsubscribe()` / `close()`) and are all idempotent; release them promptly.
8. **Static type checking**: enable pyright in your project and leverage the `RosMessage` / `RosActionView` protocols.
9. **Check generated code into VCS**: keep the generated directory under version control; regenerate and diff against the `.msg` sources on every change.
10. **Slow consumers**: subscription/feedback queues drop the oldest entries — match your consumer throughput or reduce publish rates.

---

## 14. API Quick Reference

### 14.1 `ZRosClient` (`zros2.ZRosClient`)

| Method                  | Signature                                                                    | Description                                                                                  |
| ----------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Constructor             | `ZRosClient(config: str \| zenoh.Config)`                                    | `str` is a JSON5 config file path; raises `FileNotFoundError` / `TypeError` / `zenoh.ZError` |
| `create_publisher`      | `(topic, message_type, *, namespace="") -> Publisher[MsgT]`                  | Create a publisher                                                                           |
| `create_subscriber`     | `(topic, message_type, *, namespace="") -> Subscriber[MsgT]`                 | Create a subscriber                                                                          |
| `create_service_client` | `(service_name, service_type, *, namespace="") -> ServiceClient[ReqT, ResT]` | Create a service client; `service_type` satisfies the `RosService` protocol                  |
| `service_is_ready`      | `(service_name, ros2_type, *, namespace="") -> bool`                         | Whether a matching server (exact name + type) is alive                                       |
| `wait_for_service`      | `(service_name, ros2_type, timeout_ms=None, *, namespace="") -> bool`        | Block until a matching server appears; `None` waits indefinitely                             |
| `create_action_client`  | `(action_name, action_type, timeout=None, *, namespace="") -> Action[...]`   | Create an action client; `timeout` in ms, default 3000                                       |
| `create_liveliness`     | `(entity, name="*", ros2_type="*", qos=None, *, namespace="") -> Liveliness` | Create an entity-discovery handle; `qos` defaults to `Qos.any()`                             |
| `session` (property)    | `-> ZenohSessionProxy`                                                       | Protected session proxy (close/undeclare forbidden)                                          |
| `close()`               | `-> None`                                                                    | Close the session; idempotent                                                                |
| Context manager         | `__enter__` / `__exit__`                                                     | Closes the session on exit                                                                   |

### 14.2 Endpoints

| Class / Method                                                    | Description                                                                             |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `Publisher.publish(data)`                                         | Publish a message; raises `RuntimeError` after destroy                                  |
| `Publisher.destroy()`                                             | Undeclare the publisher; idempotent                                                     |
| `Subscriber.subscribe(callback)`                                  | Register a sync callback and start subscribing; duplicate subscribe raises `ValueError` |
| `Subscriber.unsubscribe()` / `close()`                            | Unsubscribe; idempotent                                                                 |
| `ServiceClient.send_request(payload=None, timeout=1000)`          | Request-response call; `payload=None` sends an empty request                            |
| `Action.send_goal(goal=None) -> GoalHandle`                       | Send a goal; returns `GoalHandle(goal_id, accepted)`                                    |
| `Action.get_result(handle, timeout=None)`                         | Get the result; blocks until the goal terminates                                        |
| `Action.cancel_goal(handle, timeout=None)` / `cancel_all_goals()` | Cancel goal(s); returns `CancelGoal_Response`                                           |
| `Action.feedback_callback` / `status_callback`                    | Properties; set the feedback/status callback                                            |
| `Liveliness.get() -> list[Sample]`                                | Query currently alive entities                                                          |
| `Liveliness.subscribe(callback)` / `close()`                      | Watch liveliness changes / release                                                      |

### 14.3 Generator (`zros2.generator`)

| Symbol                                                                       | Description                                                   |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `VALID_DISTROS`                                                              | `("humble", "iron", "jazzy", "kilted", "lyrical")`            |
| `parse_msg_text` / `parse_msg_file` / `parse_srv_file` / `parse_action_file` | Parse IDL; `.action` returns `ActionSource` (3 user sections) |
| `expand_action` / `ActionSource`                                             | Expand into the 8 ROS 2 action `MsgDefinition`s               |
| `MsgDefinition` / `MsgField`                                                 | Parsed models                                                 |
| `resolve_type` / `ResolvedType`                                              | Type string → pycdr2 annotation expression                    |
| `generate_all(types, output_dir, root_package="", distro="")`                | Generate all sources; returns a list of `GeneratedFile`       |

---

## 15. FAQ

**Q1: Why am I not receiving messages?**
Check: ① the topic and `namespace` match between publisher and subscriber; ② both sides use the same `message_type` (a CDR layout mismatch fails deserialization — errors are logged); ③ `subscribe()` was actually called; ④ the session has not been closed.

**Q2: Can I use an async function as a callback?**
No. The sync `Subscriber` and `Action.feedback_callback` run on Zenoh threads and only accept synchronous callbacks (async functions are rejected and logged). Use `zros2.asyncio` (`AsyncSubscriber`, `invoke_action`) for async processing.

**Q3: `get_result` blocks forever — what now?**
Per ROS 2 semantics, `get_result` blocks until the goal terminates. Pass a `timeout` (ms) to bound the wait; `None` waits indefinitely.

**Q4: How do I check whether a service server is online?**
Use `wait_for_service(service_name, ros2_type, timeout_ms=...)` (blocking) or `service_is_ready(...)` (non-blocking). Both require the server to declare a `SERVICE_SERVER` liveliness token.

**Q5: Can zros2 interoperate with ROS 2?**
Message types follow the ROS 2 interface spec and use standard CDR (CDR_LE with the `00 01 00 00` encapsulation header). Communication runs over Zenoh rather than DDS, so interop with native ROS 2 nodes requires a bridging layer (liveliness tokens use the `@/{zenoh_id}/@ros2_lv/...` key format, declared by the bridge plugin).

**Q6: What happens when a bounded field exceeds its bound?**
Bounds on bounded arrays/strings/sequences are enforced at **serialization time** — an over-bound value raises an exception.

**Q7: When is `ActionNotAvailableException` raised?**
It is a subtype of `ActionException` for type-specific handling; action failures normally raise `ActionInvokeException`. Catching `ActionException` covers both.

**Q8: How do I integrate generated code with my own package layout?**
`--root-package` decides the import prefix. For example, generating into `./zros2_msgs` with `--root-package zros2_msgs` yields imports like `from zros2_msgs.my_package.msg import MyMessage`.
