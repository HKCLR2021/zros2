# zros2 — ROS 2 client library for Zenoh

**Talk to a ROS 2 system from Python without running ROS 2.**

zros2 is a client-side library for systems that live on the Zenoh side of a
[`zenoh-bridge-ros2dds`](https://github.com/eclipse-zenoh/zenoh-plugin-ros2dds)
deployment. It provides ROS 2-style publishers, subscribers, service clients,
action clients, and liveliness discovery, with message types generated from
ROS 2 interface files.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/HKCLR2021/zros2/actions/workflows/ci.yml/badge.svg)](https://github.com/HKCLR2021/zros2/actions/workflows/ci.yml)

---

## Scope at a glance

| This project is | This project is **not** |
|---|---|
| A Python **client library** for ROS 2-style communication over Zenoh | A Zenoh router, plugin, or ROS 2/DDS bridge |
| A publisher / subscriber / service-client / action-client implementation | A service server or action server implementation |
| A generator for **static, typed** Python message classes | A runtime `.msg` loader or dynamic type system |
| A lightweight alternative to pulling in rclpy on the Zenoh side | A drop-in replacement for rclpy or a full ROS 2 runtime |
| Synchronous core + optional asyncio facade | A complete ROS 2 API (parameters, TF, rosout, lifecycle, …) |

**One-line positioning:** zros2 is the Python counterpart to the ROS 2 Zenoh
bridge — not the bridge itself.

---

## Who this is for

zros2 is for Python developers building **non-ROS 2 components** that must
communicate with a ROS 2 graph:

- cloud services, fleet services, and external control panels;
- test harnesses, simulators, and data pipelines;
- companion applications running outside the robot's ROS 2 environment;
- tooling that needs typed ROS 2 messages without installing rclpy.

Typical setup:

```text
┌──────────────────────┐        ┌──────────────┐        ┌─────────────────────────┐
│ Python application   │        │              │        │ zenoh-bridge-ros2dds    │
│ using zros2          │ ◄────► │    Zenoh     │ ◄────► │ on the ROS 2 machine    │
│ (no ROS 2 runtime)   │        │              │        │ (ROS 2 / DDS side)      │
└──────────────────────┘        └──────────────┘        └─────────────────────────┘
```

### Who this is not for

- **ROS 2 node authors** who need a normal ROS 2 client — use `rclpy`.
- **Users looking for a bridge** — deploy `zenoh-bridge-ros2dds` or
  `zenoh-plugin-ros2dds`; zros2 does not replace it.
- **Service/action server authors** — zros2 only implements the client side.
- **Users needing full ROS 2 QoS semantics** — zros2 does not expose
  publisher/subscriber QoS controls or transient-local history.
- **Users needing parameters, TF, rosout, lifecycle, or graph APIs** — those
  are outside this library's scope.

---

## Requirements

- Python **3.12+**
- A Zenoh deployment that can reach a **`zenoh-bridge-ros2dds`** instance
  when ROS 2 interoperability is required
- `eclipse-zenoh`, `pycdr2`, and `lark` (installed automatically)
- A generated message package produced by `zros2-gen`

zros2 does **not** start or configure the bridge. The bridge must already be
running and connected to the ROS 2 graph.

---

## Installation

zros2 is not currently published on PyPI. Install a wheel from the
[GitHub Releases](https://github.com/HKCLR2021/zros2/releases) page:

```bash
pip install ./zros2-2.0.0-py3-none-any.whl
```

For development:

```bash
pip install -e ".[dev]"
```

---

## Quick start

### 1. Generate typed messages

Generate Python classes from the ROS 2 packages you need:

```bash
zros2-gen \
  --msg-dirs ./ros_ws/src/my_interfaces \
  --ros-version humble \
  --root-package my_msgs \
  --output ./my_msgs
```

All standard built-in interfaces for the selected distro (`std_msgs`,
`geometry_msgs`, `builtin_interfaces`, …) are bundled. Add the **parent** of
the output directory to `PYTHONPATH`:

```bash
export PYTHONPATH="$PWD:$PYTHONPATH"
```

### 2. Connect to Zenoh

Create a Zenoh config that connects to your bridge. For a bridge running on
the default router endpoint:

```json5
// zenoh.json5
{
  mode: "client",
  connect: {
    endpoints: ["tcp/127.0.0.1:7447"],
  },
  scouting: {
    multicast: { enabled: false },
  },
}
```

```python
from zros2 import ZRosClient

client = ZRosClient("./zenoh.json5")
# use as a context manager, or call client.close() when done
```

> `ZRosClient` accepts a config file path, a `pathlib.Path`, or a
> `zenoh.Config` object.

### 3. Publish and subscribe

```python
from my_msgs.std_msgs.msg import String

publisher = client.create_publisher("/chatter", String)
publisher.publish(String(data="hello from zros2"))

subscriber = client.create_subscriber("/chatter", String)
subscriber.subscribe(lambda msg: print("received:", msg.data))
```

Subscriber callbacks run on Zenoh threads. Keep them short and synchronous;
the optional `zros2.asyncio` facade is the supported way to consume a topic
from an event loop.

ROS-style names (`"/chatter"`) and Zenoh-style names (`"chatter"`) are
normalized to the same Zenoh key. Use the `namespace` keyword to address a
bridge namespace:

```python
pub = client.create_publisher("/chatter", String, namespace="robot_01")
# effectively "robot_01/chatter"
```

### 4. Call a service

```python
from my_msgs.my_pkg.srv import AddTwoInts

service = client.create_service_client("/add_two_ints", AddTwoInts)
response = service.send_request(
    AddTwoInts.Request(a=10, b=20),
    timeout=1000,  # milliseconds
)
print(response.sum)
```

Optional readiness probe:

```python
srv_type = AddTwoInts.__ros_name__  # "my_pkg/srv/AddTwoInts"
if not client.wait_for_service("/add_two_ints", srv_type, timeout_ms=5000):
    raise TimeoutError("service is not available")
```

### 5. Use an action

```python
from my_msgs.action_tutorials_interfaces.action import Fibonacci

action = client.create_action_client("/fibonacci", Fibonacci)

def on_feedback(message: Fibonacci.FeedbackMessage) -> None:
    print("feedback:", list(message.feedback.partial_sequence))

action.feedback_callback = on_feedback

with action:
    handle = action.send_goal(Fibonacci.Goal(order=10))
    if not handle.accepted:
        raise RuntimeError("goal rejected")

    response = action.get_result(handle)  # blocks until the goal terminates
    print("status:", response.status)
    print("result:", list(response.result.sequence))
```

`get_result()` returns the action's `GetResult_Response` (`status` plus
`result`). Pass `timeout` in milliseconds to bound the wait. Cancellation and
status observation are also available:

```python
action.cancel_goal(handle)
action.cancel_all_goals()

action.status_callback = lambda statuses: print(statuses.status_list)
```

### 6. Async users

```python
from zros2.asyncio import ActionFeedback, ActionResult, AsyncRobotClient

zros = AsyncRobotClient(client)

async for event in zros.invoke_action("/fibonacci", Fibonacci):
    if isinstance(event, ActionFeedback):
        print("feedback:", event.feedback)
    elif isinstance(event, ActionResult):
        print("result:", event.result)
```

The async facade runs blocking calls on worker threads and bridges Zenoh
callbacks into bounded queues. It is optional; the core API is synchronous.

---

## Supported surface

| Capability | Status |
|---|---|
| Publish / subscribe over Zenoh | Yes |
| Service **client** | Yes |
| Action **client** (goal, feedback, result, cancel, status) | Yes |
| Liveliness / entity discovery | Yes |
| Namespace-aware factory API | Yes |
| Runtime type registry (`get_type`, `get_service`, `get_action`) | Yes |
| Generated `.pyi` stubs | Yes |
| Optional asyncio facade | Yes |
| Service server / action server | No — use ROS 2 |
| Parameter, TF, rosout, lifecycle APIs | No |
| Publisher/subscriber QoS controls, transient-local | No |
| Dynamic `.msg` loading at runtime | No |
| `wstring` message fields | No — generation rejects them |

---

## Message generation

`zros2-gen` reads `.msg`, `.srv`, and `.action` files and writes:

- typed dataclasses with CDR serialization;
- `.pyi` stubs for IDE/type-checker support;
- package `__init__.py` files with a runtime type registry.

Supported type forms include primitives, fixed/bounded/unbounded arrays,
bounded strings, `sequence<T>` / `sequence<T, N>`, nested types, constants,
field defaults, and constant-reference bounds such as `int32[COUNT]`.

`wstring` is parsed but rejected during generation: ROS 2 encodes it as
UTF-16LE, which the current `pycdr2` backend cannot represent. Use `string`
for new interfaces.

The generated package root exposes:

```python
from my_msgs import get_type, get_service, get_action, has_type, iter_types

String = get_type("std_msgs/msg/String")
Service = get_service("my_pkg/srv/MyService")
Action = get_action("my_pkg/action/Fibonacci")
```

Importing the generated package root also imports its message subpackages, so
the registry is populated immediately.

---

## Compatibility and limitations

- **Bridge contract:** zros2 uses the Zenoh key layout and CDR payloads
  expected by `zenoh-bridge-ros2dds` for topics, services, and actions. The
  bridge must be configured to expose the ROS 2 entities you need.
- **Client-only:** zros2 cannot host a service or action server for ROS 2
  clients; servers must remain on the ROS 2 side.
- **No QoS selection:** publisher/subscriber QoS (reliability, durability,
  history, transient-local) is not configurable. Latched/transient-local
  topics may not deliver pre-subscription messages.
- **Static types:** message classes are generated ahead of time. There is no
  runtime IDL parser or type discovery on the wire; use the same interface
  definitions as the ROS 2 side.
- **Name mapping:** ROS names with a leading `/` are normalized; the bridge
  expects Zenoh keys without a leading slash. Namespaces are mapped to the
  bridge's namespace prefix.
- **Timeout vs availability:** an empty Zenoh reply does not distinguish
  "no provider" from "provider did not reply". A finite timeout therefore
  raises `ServiceTimeoutException`; use `service_is_ready()` /
  `wait_for_service()` first when availability must be known before calling.
- **Validation boundary:** the repository's default tests use local Zenoh
  peers. Validate against your actual bridge/ROS 2 distribution when deploying.
- **Python and platforms:** requires Python 3.12+; platform support follows
  `eclipse-zenoh` wheels.

---

## Documentation

- [Documentation index / language map](docs/README.md)
- [SDK guide (English)](docs/sdk_development.md)
- [SDK guide (Chinese)](docs/sdk_development_zh.md)
- [Developer / architecture guide (English)](docs/developer_guide.md)
- [Internal developer guide (Chinese)](docs/developer_guide_zh.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## Development

```bash
pip install -e ".[dev]"
pytest tests/
ruff check src tests benchmarks
pyright
```

The test suite covers the parser, generated code, endpoints, client factory,
protocols, integration over local Zenoh peers, liveliness, and asyncio facade.
See the [developer guide](docs/developer_guide.md) for the generator pipeline
and contribution rules.

---

## License

Proprietary — all rights reserved. Bundled ROS 2 interface definitions retain
their upstream Apache-2.0 terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
