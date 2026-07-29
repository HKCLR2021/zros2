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

```python
from zros2 import Action
from zros2.types import ActionTypes
from zros2_msgs.my_package.action import Fibonacci

action = Action(
    session,
    action_name="/fibonacci",
    action_type=Fibonacci,
    timeout=5000,
)

# Send a goal and get the result
goal_handle = action.send_goal(Fibonacci.Goal(order=10))
result = action.get_result(goal_handle)
```

Using the `ActionTypes` container:

```python
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
srv = client.create_srv_client(
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

For converting from arbitrary attribute-based objects:

```python
from zros2.types import from_attributes

class Obj:
    data = "world"

restored = from_attributes(String, Obj)
```

### 8. Liveliness & Discovery

Monitor ROS 2 entity presence over Zenoh:

```python
from zros2 import Liveliness, LivelinessType, Qos
from zros2._session import ZenohSessionProxy

proxy = ZenohSessionProxy(zenoh_session)

# Discover all publishers on /chatter
lv = Liveliness(
    proxy,
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
from zros2 import (
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

| Protocol / Type          | Purpose                                                                                                                     |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `RosMessage`             | Base protocol for all message dataclasses (`serialize()`, `deserialize()`, `to_dict()`, `from_dict()`, `from_attributes()`) |
| `RosService[ReqT, ResT]` | Protocol for service types (requires `ClassVar` members `Request` and `Response`)                                           |
| `RosAction[...]`         | Protocol for action types (8 `ClassVar` message members)                                                                    |
| `ServiceTypes`           | Frozen dataclass container holding `Request` and `Response` types                                                           |
| `ActionTypes`            | Frozen dataclass container holding all 8 action message types                                                               |
| `SendGoalRequest[GoalT]` | Protocol for action `SendGoal` request messages                                                                             |
| `GetResultRequest`       | Protocol for action `GetResult` request messages                                                                            |

### TypeVars

Generic TypeVars are exported from `zros2.types` for type-safe generic code:

| TypeVar                                | Bound        | Used by                       |
| -------------------------------------- | ------------ | ----------------------------- |
| `MsgT`                                 | `RosMessage` | `Publisher`, `Subscriber`     |
| `ReqT`, `ResT`                         | `RosMessage` | `ServiceClient`, `RosService` |
| `SGReqT`, `SGResT`, `GRReqT`, `GRResT` | `RosMessage` | Action request/response       |
| `GoalT`, `ResultT`, `FeedbackT`        | `RosMessage` | Action goal/result/feedback   |
| `FBMsgT`                               | `RosMessage` | Action `FeedbackMessage`      |

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
from zros2.generator.semantics import resolve_type, get_default_value, is_primitive
from zros2.generator.codegen import (
    generate_message_module,
    generate_init_module,
    generate_stub_module,
    GeneratedFile,
)
from zros2.generator.pipeline import (
    build_plan,
    execute_plan,
    generate_all,
    write_generated_files,
)
```

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
