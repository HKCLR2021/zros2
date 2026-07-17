# zros2 — Zenoh ROS 2 Bridge

A lightweight Python library for ROS 2-like communication
over [Zenoh](https://zenoh.io/).

## Overview

`zros2` provides ROS 2 communication primitives (publishers, subscribers,
service clients, action clients) using Zenoh as the underlying transport
middleware. Message types are statically generated from `.msg` / `.srv` /
`.action` files via `zros2-gen` and serialized with `pycdr2`.

## Features

- **Spec-compliant parser** — `.msg` / `.srv` / `.action` files are fully
  parsed per the ROS 2 interface spec, including all 15 built-in types,
  fixed/bounded/unbounded arrays, bounded strings, constant-reference bounds
  (`int32[COUNT]`, `string<=MAX_LEN`, `sequence<uint8,N>`), and nested types.
- **rclpy-compatible codegen** — type resolution and code emission matches
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

## Installation

```bash
pip install zros2
```

## Usage

## Parser compliance

The ``zros2-gen`` generator parses ROS 2 interface files per the
[ROS 2 Interface specification](https://docs.ros.org/en/humble/Concepts/Basic/About-Interfaces.html).

### Supported type forms

| Category | Syntax | Bound checking |
|----------|--------|----------------|
| Primitives | `int32`, `float64`, `string`, `wstring`, … | — |
| Fixed array | `int32[3]` | — |
| Fixed array (const ref) | `int32[COUNT]` | — |
| Unbounded array | `int32[]` | — |
| Bounded array | `int32[<=5]` / `int32[<=MAX]` | ✅ serialise-time |
| Bounded string | `string<=255` / `string<=MAX_LEN` | ✅ serialise-time |
| Sequence | `sequence<uint8>` | — |
| Bounded sequence | `sequence<uint8,10>` / `sequence<uint8,N>` | ✅ serialise-time |
| Nested type | `std_msgs/String` | — |

### 1. Generate message types

Place your `.msg` / `.srv` / `.action` files in the standard ROS 2 directory
structure and run `zros2-gen`:

```
my_msgs/
└── my_package/
    ├── msg/
    │   ├── MyMessage.msg
    │   └── ...
    ├── srv/
    │   └── MyService.srv
    └── action/
        └── MyAction.action
```

```bash
zros2-gen \
  --msg-dirs ./my_msgs/my_package \
  --ros-version humble \
  --root-package zros2_msgs \
  --output ./zros2_msgs
```

All standard ROS 2 built-in types (std_msgs, geometry_msgs, builtin_interfaces,
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

Services are defined via `.srv` files. The generator produces request and
response message types plus a wrapper class.

```python
from zros2 import ServiceClient
from zros2._types import ServiceTypes
from zros2_msgs.my_package.srv import MyService

# Using the ServiceTypes container
srv = ServiceClient(
    session,
    service_name="/add_two_ints",
    service_type=ServiceTypes(MyService.Request, MyService.Response),
)
result = srv.send_request(MyService.Request(a=10, b=20))
print(result)  # typed response, e.g. MyService.Response(sum=30)
```

### 4. Actions

Actions are defined via `.action` files (goal / result / feedback sections).
The generator produces five message types plus a wrapper class.

```python
from zros2 import Action
from zros2._types import ActionTypes
from zros2_msgs.my_package.action import Fibonacci

action = Action(
    session,
    action_name="/fibonacci",
    action_type=ActionTypes(
        send_goal_request=Fibonacci.SendGoal_Request,
        send_goal_response=Fibonacci.SendGoal_Response,
        get_result_request=Fibonacci.GetResult_Request,
        get_result_response=Fibonacci.GetResult_Response,
        feedback=Fibonacci.Feedback,
    ),
)

# Send a goal and get the result
goal_response = action.send_goal(Fibonacci.Goal(order=10))
result = action.get_result()
```

### 5. Using the client factory

```python
from zros2 import ZRosClient
from zros2._types import ServiceTypes, ActionTypes
from zros2_msgs.std_msgs.msg import String
from zros2_msgs.my_package.srv import MyService
from zros2_msgs.my_package.action import Fibonacci

client = ZRosClient("./zenoh.json5")

pub = client.create_publisher("/chatter", String, namespace="robot_01")
sub = client.create_subscriber("/battery", String, namespace="robot_01")
srv = client.create_srv_client(
    "/add", ServiceTypes(MyService.Request, MyService.Response),
    namespace="robot_01",
)
act = client.create_action_client(
    "/fib", ActionTypes(
        send_goal_request=Fibonacci.SendGoal_Request,
        send_goal_response=Fibonacci.SendGoal_Response,
        get_result_request=Fibonacci.GetResult_Request,
        get_result_response=Fibonacci.GetResult_Response,
        feedback=Fibonacci.Feedback,
    ),
    namespace="robot_01",
)
```

### 6. Runtime reflection

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

Every generated message provides `to_dict()` and `from_dict()` for
conversion to/from plain dictionaries:

```python
msg = String(data="hello")
d = msg.to_dict()          # {"data": "hello"}
restored = String.from_dict(d)
```

## CLI Reference

```
usage: zros2-gen [-h] --msg-dirs MSG_DIRS --output OUTPUT
                 --ros-version {humble,iron,jazzy,kilted,lyrical}
                 [--root-package ROOT_PACKAGE] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `--msg-dirs` | One or more ROS 2 package directories containing `msg/`, `srv/`, `action/` subfolders |
| `--output` | Output directory for generated Python source files |
| `--ros-version` | ROS 2 distribution whose builtin types to bundle (required) |
| `--root-package` | Top-level package name (defaults to output dir name) |
| `--dry-run` | Print file list without writing |

## Development

```bash
# Install in editable mode
pip install -e ".[dev]"

# Run tests
pytest
```

## License

Proprietary — all rights reserved.
