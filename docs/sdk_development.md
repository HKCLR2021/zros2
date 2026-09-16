# zros2 SDK 开发文档（使用方指南）

> 适用版本：**zros2 2.0.0** · Python ≥ 3.12
> 本文面向使用 zros2 构建应用的开发者。关于 zros2 内部架构与贡献指南，参见 [developer_guide.md](./developer_guide.md)。英文版见 [sdk_development_en.md](./sdk_development_en.md)。

---

## 目录

1. [简介](#1-简介)
2. [安装](#2-安装)
3. [生成消息类型](#3-生成消息类型)
4. [客户端生命周期](#4-客户端生命周期)
5. [发布 / 订阅](#5-发布--订阅)
6. [服务](#6-服务)
7. [动作](#7-动作)
8. [发现与存活检测](#8-发现与存活检测)
9. [类型系统](#9-类型系统)
10. [运行时反射与数据转换](#10-运行时反射与数据转换)
11. [异常处理](#11-异常处理)
12. [异步开发（zros2.asyncio）](#12-异步开发zros2asyncio)
13. [最佳实践](#13-最佳实践)
14. [API 速查](#14-api-速查)
15. [常见问题（FAQ）](#15-常见问题faq)

---

## 1. 简介

zros2 是一个基于 [Zenoh](https://zenoh.io/) 的轻量级 ROS 2 风格通信库，提供发布/订阅（Publisher/Subscriber）、服务调用（ServiceClient）、动作调用（Action）等通信原语。消息类型由内置的 `zros2-gen` 代码生成器从 `.msg` / `.srv` / `.action` 文件静态生成，并通过 `pycdr2`（CDR 序列化）与 ROS 2 生态保持兼容。

### 设计定位

zros2 专为**配合 `zenoh-plugin-ros2dds` / `zenoh-bridge-ros2dds` 使用**而设计：ROS 2 节点侧通过该桥接插件把 DDS 通信翻译到 Zenoh，zros2 作为 Zenoh 侧的对端实现，让**不运行 ROS 2** 的系统也能与 ROS 2 系统直接通信。

- **接口结构参考 rclpy**：客户端（`ZRosClient`）与端点（publisher / subscriber / service client / action client）的组织方式对齐 ROS 2 参考实现，ROS 2 开发者几乎零学习成本。
- **序列化用 pycdr2 实现**：`zros2-gen` 生成器把 `.msg` / `.srv` / `.action` 静态编译为带完整类型注解的 Python dataclass——IDE 友好、无运行时类型解析开销、高性能。
- **轻量级定位**：面向上层系统（机器人应用、云端服务、测试框架等），使其能与 ROS 2 系统直接通信，而无需绑定 ROS 2 的实现（rclpy、rcl 等）。
- **能力边界**：zros2 提供 service / action 的**客户端**能力；**不提供** service / action **server** 功能供 ROS 2 端调用（服务端 / 动作服务端由 ROS 2 侧节点承载，并通过桥接对外暴露）。这是设计取舍，而非功能缺失。

### 核心特性

| 特性              | 说明                                                                     |
| ----------------- | ------------------------------------------------------------------------ |
| 静态消息类型      | 生成带完整类型注解与 `.pyi` stub 的 Python dataclass，IDE 提示完整       |
| Zenoh 传输        | 发布、订阅、服务、动作均通过 Zenoh 通信，支持设备命名空间                |
| 类型安全协议      | `RosMessage` / `RosService` / `RosAction` 结构化协议，对静态类型检查友好 |
| 运行时类型注册表  | 生成的包支持按字符串名反射查找类型（`get_type` 等）                      |
| 内置 ROS 2 定义   | Humble ~ Lyrical 各发行版内置类型全部随库携带，无需联网下载              |
| CDR 序列化        | 有界（bounded）类型在序列化时强制校验边界                                |
| 可选 asyncio 门面 | `zros2.asyncio.AsyncRobotClient` 将阻塞式 API 适配到事件循环             |

---

## 2. 安装

```bash
pip install zros2
```

开发模式安装（含测试依赖）：

```bash
pip install -e ".[dev]"
```

运行时依赖：`eclipse-zenoh>=1.9.0`、`pycdr2>=1.0.0`、`numpy>=2.4.6`、`lark>=1.3.0`。

---

## 3. 生成消息类型

### 3.1 CLI 用法

```bash
zros2-gen \
  --msg-dirs ./my_msgs/my_package \
  --ros-version humble \
  --root-package zros2_msgs \
  --output ./zros2_msgs
```

也可以把 workspace 根目录传给 `--msg-dirs`（扫描其直接子目录里含 `msg/`、`srv/` 或 `action/` 的包）：

```bash
zros2-gen --msg-dirs ./my_msgs --ros-version humble --output ./zros2_msgs
```

| 选项              | 说明                                                                                   |
| ----------------- | -------------------------------------------------------------------------------------- |
| `--msg-dirs`      | 一个或多个 ROS 2 包目录（含 `msg/`、`srv/` 和/或 `action/`），或这些包所在的 workspace |
| `--output` / `-o` | 生成源码的输出目录                                                                     |
| `--ros-version`   | ROS 2 发行版，决定捆绑的内置类型：`humble` / `iron` / `jazzy` / `kilted` / `lyrical`   |
| `--root-package`  | 顶层包名（默认取输出目录名；传 `--root-package ""` 可去掉前缀）                        |
| `--dry-run`       | 只打印将生成的文件列表，不写盘                                                         |

等价模块入口：`python -m zros2.generator --msg-dirs ... --output ... --ros-version humble`。

指定发行版的所有标准内置类型（`std_msgs`、`geometry_msgs`、`builtin_interfaces` 等）会自动捆绑；同名用户类型覆盖内置类型。

### 3.2 生成结果

每个消息生成一个 `.py` 模块 + 一个 `.pyi` stub；服务/动作生成合并的 wrapper 模块（携带 `Request` / `Response`、`Goal` / `Result` / `Feedback` 等消息类）。生成包的根 `__init__.py` 提供运行时反射函数（见第 10 节）。

生成的代码引用了固定的 zros2 运行时符号（生成 ABI），请勿手改；重新生成时直接覆盖。

### 3.3 编程式生成

```python
from pathlib import Path
from zros2.generator import expand_action, parse_action_file, parse_msg_file, generate_all

defs = parse_msg_file(Path("my_msgs/my_package/msg/MyMessage.msg"), package="my_package")
files = generate_all({"my_package/msg/MyMessage": defs}, Path("./out"))
for f in files:
    f.path.parent.mkdir(parents=True, exist_ok=True)
    f.path.write_text(f.content, encoding="utf-8")

# .action：parser 只返回 Goal / Result / Feedback；传输类型由 expand_action 补齐
source = parse_action_file(Path("my_msgs/my_package/action/Fibonacci.action"), package="my_package")
action_types = {d.full_name: d for d in expand_action(source)}
```

`zros2.generator` 同时导出 `parse_msg_text`、`parse_srv_file`、`ActionSource`、`MsgDefinition`、`MsgField`、`resolve_type`、`ResolvedType`、`VALID_DISTROS`。生成后的 action 包对用户导出 wrapper 与 `Goal` / `Result` / `Feedback`；`SendGoal_*` / `GetResult_*` / `FeedbackMessage` 仍在模块内，但不进入 `action/__init__.py`。

---

## 4. 客户端生命周期

`ZRosClient` 是统一入口：持有底层 Zenoh session，并通过工厂方法创建各种通信原语。

```python
from zros2 import ZRosClient

# 传入 Zenoh 配置文件路径（JSON5）或 zenoh.Config 对象
client = ZRosClient("./zenoh.json5")

pub = client.create_publisher("/chatter", String, namespace="robot_01")
srv = client.create_service_client("/add", MyService, namespace="robot_01")

client.close()   # 幂等，可多次调用
```

推荐使用上下文管理器，退出时自动关闭 session：

```python
with ZRosClient("./zenoh.json5") as client:
    ...
# session 已关闭
```

### 命名空间

所有工厂方法都接受 keyword-only 的 `namespace` 参数（默认 `""`）。传入非空命名空间时，主题/服务/动作名前会加上 `{namespace}/` 前缀；`namespace=""` 表示不加前缀。同名实体在不同命名空间下互不干扰，可用于多设备隔离部署。

> 注意：`client.session` 属性返回受保护的 `ZenohSessionProxy`。它禁止 `close()` / `undeclare()` 等破坏性操作，仅用于向端点类传递 session（直接构造 `Publisher(session, ...)` 等端点时使用）。

---

## 5. 发布 / 订阅

### 5.1 发布

```python
from zros2 import ZRosClient
from zros2_msgs.geometry_msgs.msg import Twist, Vector3

client = ZRosClient("./zenoh.json5")

pub = client.create_publisher("/cmd_vel", Twist, namespace="robot_01")
pub.publish(Twist(
    linear=Vector3(x=0.5, y=0.0, z=0.0),
    angular=Vector3(x=0.0, y=0.0, z=0.0),
))
pub.destroy()   # 幂等
```

- `publish(data)` 接受消息实例，内部调用 `data.serialize()` 生成 CDR 字节。
- 发布器在构造时就已声明；`destroy()` 之后调用 `publish` 会抛 `RuntimeError`。
- 也可直接构造：`Publisher(session, topic="/chatter", message_type=String)`（`session` 取 `client.session`）。

### 5.2 订阅

```python
from zros2_msgs.my_package.msg import MyMessage

def callback(msg: MyMessage) -> None:
    print(f"收到: {msg}")

sub = client.create_subscriber("/battery", MyMessage, namespace="robot_01")
sub.subscribe(callback)
...
sub.unsubscribe()   # 幂等；close() 同义
```

重要约束：

- **回调在 Zenoh 线程上执行**，必须保持轻量、不能阻塞；回调必须是**同步函数**。传入 async 函数会被拒绝（抛 `TypeError` 并记录日志）。
- 重复 `subscribe()` 抛 `ValueError`（需先 `unsubscribe()`）；session 已关闭时抛 `RuntimeError`。
- 消息会先反序列化并校验类型再进入回调；反序列化失败只记录日志，不会中断订阅。

---

## 6. 服务

服务类型由 `.srv` 文件生成，wrapper 类携带 `Request` / `Response` 两个消息类。

```python
from zros2 import ZRosClient
from zros2_msgs.my_package.srv import MyService

client = ZRosClient("./zenoh.json5")
srv = client.create_service_client("/add", MyService, namespace="robot_01")

result: MyService.Response = srv.send_request(
    MyService.Request(a=10, b=20),  # 传 None 表示空请求
    timeout=1000,                   # 毫秒；None = 无限等待
)
print(result.sum)
```

- `send_request` 默认超时 1000 ms；`timeout=None` 无限等待。
- 服务类型也可以传入 `ServiceTypes` 容器：`ServiceTypes(Request=MyService.Request, Response=MyService.Response)`。

### 服务可用性探测

服务端会声明 `SERVICE_SERVER` 存活 token；探测同时**精确匹配名称与类型**（不需要服务类型类，用类型字符串即可）：

```python
srv_type = MyService.__ros_name__   # 例如 "my_pkg/srv/MyService"

# 阻塞等待，超时返回 False；timeout_ms=None 无限等待
if not client.wait_for_service("/add", srv_type, timeout_ms=5000, namespace="robot_01"):
    raise TimeoutError("service not available")

# 非阻塞探测
if client.service_is_ready("/add", srv_type, namespace="robot_01"):
    result = srv.send_request(MyService.Request(a=10, b=20))
```

注意：服务/动作的存活 token 不携带 QoS，因此这两个探测没有 `qos` 参数。

### 异常

- 服务端返回错误 → `ServiceInvokeException`
- 超时无响应 → `ServiceNotAvailableException`
- Zenoh 通信错误 → `ServiceInvokeException`（由底层错误链引发）

---

## 7. 动作

动作类型由 `.action` 文件生成（goal / result / feedback 三段）。生成模块里共有 8 个子类型（含 `FeedbackMessage`、`SendGoal_*`、`GetResult_*` 传输类型）；`action/__init__.py` 只再导出 wrapper 与用户侧的 `Goal` / `Result` / `Feedback`。

```python
from zros2 import ZRosClient
from zros2_msgs.my_package.action import Fibonacci

client = ZRosClient("./zenoh.json5")
action = client.create_action_client(
    "/fib", Fibonacci,
    timeout=5000,               # 毫秒，默认 3000；用于 send_goal RPC
    namespace="robot_01",
)

# 发送 goal：每次调用生成全新的 goal_id
handle = action.send_goal(Fibonacci.Goal(order=10))
print(handle.accepted)          # 服务端是否接受

# 取结果：按 ROS 2 语义阻塞直到目标终止；timeout=None 无限等待
result = action.get_result(handle)
```

### 反馈与状态

```python
# 反馈回调：只收到“通过本客户端发送的 goal”的反馈（按 goal_id 过滤）
# 必须在 send_goal 之前设置；回调运行在 Zenoh 线程上，保持轻量
action.feedback_callback = lambda feedback: print("反馈:", feedback)

# 状态回调：收到该动作 status 主题上的全部 GoalStatusArray
statuses: list = []
action.status_callback = lambda array: statuses.append(array)
# array.status_list 中每一项携带 GoalStatus.STATUS_* 状态码
```

`GoalStatus` 常量：`STATUS_UNKNOWN=0`、`STATUS_ACCEPTED=1`、`STATUS_EXECUTING=2`、`STATUS_CANCELING=3`、`STATUS_SUCCEEDED=4`、`STATUS_CANCELED=5`、`STATUS_ABORTED=6`。

### 取消

```python
from zros2 import CancelGoal_Response

# 取消单个 goal，或取消全部活跃 goal
r1 = action.cancel_goal(handle)
r2 = action.cancel_all_goals()
if r1.return_code != CancelGoal_Response.ERROR_NONE:
    print("取消失败:", r1.return_code)
```

`CancelGoal_Response` 常量：`ERROR_NONE=0`、`ERROR_REJECTED=1`、`ERROR_UNKNOWN_GOAL=2`、`ERROR_GOAL_TERMINATED=3`。

### 说明

- `Action` 是上下文管理器，进入时惰性建立 feedback/status 订阅，退出时自动取消订阅。
- 动作相关调用失败时抛 `ActionInvokeException`。
- 内置的 `action_msgs` 消息（`GoalInfo`、`GoalStatus`、`GoalStatusArray`、`CancelGoal_Request`、`CancelGoal_Response`）由 zros2 顶层直接导出。
- 也可以用 `ActionTypes` 容器替代动作类型类（字段：`Goal` / `Result` / `Feedback` / `FeedbackMessage` / `SendGoal_Request` / `SendGoal_Response` / `GetResult_Request` / `GetResult_Response`）。

---

## 8. 发现与存活检测

通过 Zenoh liveliness token 发现 ROS 2 实体（发布者、订阅者、服务端/客户端、动作端/客户端）的在线状态。

```python
from zros2 import LivelinessType, Qos, ZRosClient

client = ZRosClient("./zenoh.json5")

# 发现 /chatter 上的全部发布者（可指定类型与 QoS）
lv = client.create_liveliness(
    LivelinessType.PUBLISHER,
    name="/chatter",
    ros2_type="std_msgs/msg/String",
    qos=Qos.any(),   # 通配，匹配任意 QoS
    namespace="robot_01",
)

# 查询当前在线实体：返回 zenoh.Sample 列表
samples = lv.get()

# 订阅存活变化：只报告“变化”（上线/下线），不返回当前快照
lv.subscribe(lambda sample: print(f"实体变化: {sample}"))
lv.close()   # 幂等；也支持 with 语句
```

### 实体类型（LivelinessType）

`ALL`、`PLUGIN`、`PUBLISHER`、`SUBSCRIBER`、`SERVICE_SERVER`、`SERVICE_CLIENT`、`ACTION_SERVER`、`ACTION_CLIENT`。

### QoS

`Qos` 字段：`reliability`、`durability`、`history_kind`、`history_depth`、`user_data`；`Qos.any()` 返回通配值（匹配任意 QoS）。仅发布者/订阅者的 liveliness key 携带 QoS；服务/动作的 key 不携带。

---

## 9. 类型系统

`zros2.types` 定义了结构化类型系统：生成的消息类与下游自定义类型**结构性满足**协议，无需继承 zros2 的任何基类。

| 协议 / 类型                                                                    | 用途                                                                                                                 |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| `RosMessage`                                                                   | 所有消息 dataclass 的基础协议（`serialize()` / `deserialize()` / `to_dict()` / `from_dict()` / `from_attributes()`） |
| `RosService[ReqT, ResT]`                                                       | 服务类型协议（要求 `ClassVar` 成员 `Request` 与 `Response`）                                                         |
| `RosAction[SGReqT, SGResT, GRReqT, GRResT, FBMsgT, GoalT, ResultT, FeedbackT]` | 动作类型协议（8 个 `ClassVar` 消息成员）                                                                             |
| `RosActionView[GoalT, ResultT, FeedbackT]`                                     | 动作的语义视图：只暴露 3 个面向用户的类型，隐藏 `SendGoal_*` / `GetResult_*` 等传输子类型                            |
| `ServiceTypes`                                                                 | 冻结 dataclass 容器，持有 `Request` 与 `Response` 类型                                                               |
| `ActionTypes`                                                                  | 冻结 dataclass 容器，持有全部 8 个动作消息类型                                                                       |

### 泛型

泛型类和函数用 PEP 695 语法在**各自作用域内**声明类型参数，并绑定到 `RosMessage`：

```python
from zros2.types import RosMessage, RosActionView

# 类级泛型
class ActionInvoker[
    GoalT: RosMessage, ResultT: RosMessage, FeedbackT: RosMessage,
]: ...

# 函数级泛型
async def observe_action[
    GoalT: RosMessage, ResultT: RosMessage, FeedbackT: RosMessage,
](
    action_type: type[RosActionView[GoalT, ResultT, FeedbackT]],
    goal: GoalT | None = None,
) -> None: ...
```

---

## 10. 运行时反射与数据转换

生成包的根模块提供运行时类型查找：

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

所有生成的消息提供字典转换与属性转换：

```python
msg = String(data="hello")
d = msg.to_dict()                 # {"data": "hello"}
restored = String.from_dict(d)

class Obj:
    data = "world"

restored = String.from_attributes(Obj)
```

---

## 11. 异常处理

所有 zros2 异常都继承自 `ZRos2Exception`：

```
ZRos2Exception
├── ServiceException
│   ├── ServiceNotAvailableException   # 服务不可用（超时无响应）
│   └── ServiceInvokeException         # 服务调用失败（错误返回 / 通信错误）
└── ActionException
    ├── ActionNotAvailableException
    └── ActionInvokeException          # 动作调用失败（goal 被拒 / 传输失败）
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
    print("服务不可用")
except ServiceInvokeException:
    print("服务调用失败")
except ServiceException:
    print("通用服务错误")
```

建议在公共边界处捕获具体异常；兜底可捕获 `ZRos2Exception`。

---

## 12. 异步开发（zros2.asyncio）

核心 API 是同步阻塞的。`zros2.asyncio` 是可选门面：阻塞调用在 worker 线程执行，Zenoh 线程回调通过有界队列桥接到事件循环，因此服务调用可以 `await`，动作与主题流可以用 `async for` 消费。

`AsyncRobotClient` 一次性绑定 `ZRosClient`（或 session proxy），后续调用无需再传客户端：

```python
from zros2 import ZRosClient
from zros2.asyncio import ActionFeedback, ActionResult, AsyncRobotClient
from zros2_msgs.my_package.action import Fibonacci
from zros2_msgs.my_package.srv import QueryTrajectory

client = ZRosClient("./zenoh.json5")
zros = AsyncRobotClient(client)

async def run() -> None:
    # 服务调用：返回类型化响应 dataclass
    response = await zros.invoke_service(
        "/query_trajectory", QueryTrajectory,
        timeout=5000,
        namespace="robot_01",
    )

    # 动作：先逐个产出 ActionFeedback，最后产出唯一的 ActionResult
    async for event in zros.invoke_action(
        "/fib", Fibonacci,
        goal=Fibonacci.Goal(order=10),
        namespace="robot_01",
    ):
        if isinstance(event, ActionFeedback):
            print("反馈:", event.feedback)
        elif isinstance(event, ActionResult):
            print("状态:", event.status, "结果:", event.result)
```

### 发现

```python
from zros2 import LivelinessType

async def monitor() -> None:
    # 查询当前在线实体（阻塞查询放到 worker 线程）
    alive = await zros.query_liveliness(
        LivelinessType.SERVICE_SERVER,
        name="/trigger", ros2_type="std_srvs/srv/Trigger",
        namespace="robot_01",
    )
    # 监听变化：先 query 拿快照，再 watch 收增量
    async for sample in zros.watch_liveliness(
        LivelinessType.ACTION_SERVER, namespace="robot_01",
    ):
        print("变化:", sample)
```

### 异步发布 / 订阅

```python
from zros2_msgs.std_msgs.msg import String

async def pubsub() -> None:
    pub = zros.create_publisher("/chatter", String, namespace="robot_01")
    await pub.publish(String(data="hello"))
    await pub.aclose()   # 幂等

    sub = zros.create_subscriber("/battery", String, namespace="robot_01")
    async for msg in sub:   # 首次迭代时惰性订阅
        print("收到:", msg.data)
        break
    await sub.aclose()      # 结束流并取消订阅
```

### 行为约定

- 有界队列容量 100：消费者慢于生产者时**丢弃最旧**的条目（订阅、动作反馈、liveliness 监听均如此）。
- `invoke_action` 在 goal 被服务端拒绝或 send-goal / get-result 调用失败时抛 `ActionInvokeException`。
- `invoke_service` 的 `body=None` 表示空请求；失败抛常规的 `ServiceInvokeException` / `ServiceNotAvailableException`。
- 从 `async for` 中途 `break` 或关闭生成器，会正确取消底层订阅（端点上下文管理器保证 undeclare）。

---

## 13. 最佳实践

1. **客户端生命周期**：用 `with ZRosClient(...)` 管理 session；不要手动关闭共享 session 后再复用端点。
2. **命名空间**：多设备场景统一使用 `namespace` 参数隔离，避免同名主题串扰。
3. **调用前探测**：服务首次调用前用 `wait_for_service`（带超时）或 `service_is_ready` 探测。
4. **回调保持轻量**：同步回调运行在 Zenoh 线程上——不要在回调里做耗时操作；需要异步处理时改用 `zros2.asyncio`。
5. **动作先设回调再发 goal**：`feedback_callback` 必须在 `send_goal` 前设置，否则收不到反馈（并产生告警日志）。
6. **显式超时**：`send_request` / `get_result` 的 `timeout=None` 会无限等待，生产环境请传超时值。
7. **资源释放**：端点都支持上下文管理器（`with`）或显式 `destroy()` / `unsubscribe()` / `close()`，且全部幂等；及时释放避免资源泄漏。
8. **类型检查**：为工程启用 pyright，利用 `RosMessage` / `RosActionView` 等协议获得静态类型保障。
9. **生成代码入库**：将生成目录纳入版本管理，构建时重新生成并 diff，保证与 `.msg` 文件一致。
10. **慢消费者**：订阅/反馈队列会丢最旧消息，请保证消费者吞吐或降低发布频率。

---

## 14. API 速查

### 14.1 ZRosClient（`zros2.ZRosClient`）

| 方法                    | 签名                                                                         | 说明                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| 构造                    | `ZRosClient(config: str \| zenoh.Config)`                                    | `str` 为 JSON5 配置文件路径；错误时抛 `FileNotFoundError` / `TypeError` / `zenoh.ZError` |
| `create_publisher`      | `(topic, message_type, *, namespace="") -> Publisher[MsgT]`                  | 创建发布器                                                                               |
| `create_subscriber`     | `(topic, message_type, *, namespace="") -> Subscriber[MsgT]`                 | 创建订阅器                                                                               |
| `create_service_client` | `(service_name, service_type, *, namespace="") -> ServiceClient[ReqT, ResT]` | 创建服务客户端；`service_type` 满足 `RosService` 协议                                    |
| `service_is_ready`      | `(service_name, ros2_type, *, namespace="") -> bool`                         | 服务端是否存活（名称+类型精确匹配）                                                      |
| `wait_for_service`      | `(service_name, ros2_type, timeout_ms=None, *, namespace="") -> bool`        | 阻塞等待服务就绪；`None` 无限等待                                                        |
| `create_action_client`  | `(action_name, action_type, timeout=None, *, namespace="") -> Action[...]`   | 创建动作客户端；`timeout` 毫秒，默认 3000                                                |
| `create_liveliness`     | `(entity, name="*", ros2_type="*", qos=None, *, namespace="") -> Liveliness` | 创建实体发现句柄；`qos` 默认 `Qos.any()`                                                 |
| `session`（属性）       | `-> ZenohSessionProxy`                                                       | 受保护的 session 代理（禁止 close/undeclare）                                            |
| `close()`               | `-> None`                                                                    | 关闭 session，幂等                                                                       |
| 上下文管理器            | `__enter__` / `__exit__`                                                     | 退出时自动 `close()`                                                                     |

### 14.2 端点

| 类 / 方法                                                         | 说明                                           |
| ----------------------------------------------------------------- | ---------------------------------------------- |
| `Publisher.publish(data)`                                         | 发布消息；销毁后调用抛 `RuntimeError`          |
| `Publisher.destroy()`                                             | 撤销发布器，幂等                               |
| `Subscriber.subscribe(callback)`                                  | 注册同步回调并订阅；重复订阅抛 `ValueError`    |
| `Subscriber.unsubscribe()` / `close()`                            | 取消订阅，幂等                                 |
| `ServiceClient.send_request(payload=None, timeout=1000)`          | 请求-响应调用；`payload=None` 空请求           |
| `Action.send_goal(goal=None) -> GoalHandle`                       | 发送目标，返回 `GoalHandle(goal_id, accepted)` |
| `Action.get_result(handle, timeout=None)`                         | 取结果，阻塞至目标终止                         |
| `Action.cancel_goal(handle, timeout=None)` / `cancel_all_goals()` | 取消目标，返回 `CancelGoal_Response`           |
| `Action.feedback_callback` / `status_callback`                    | 属性；设置反馈/状态回调                        |
| `Liveliness.get() -> list[Sample]`                                | 查询当前在线实体                               |
| `Liveliness.subscribe(callback)` / `close()`                      | 监听存活变化 / 释放                            |

### 14.3 生成器（`zros2.generator`）

| 符号                                                                         | 说明                                                    |
| ---------------------------------------------------------------------------- | ------------------------------------------------------- |
| `VALID_DISTROS`                                                              | `("humble", "iron", "jazzy", "kilted", "lyrical")`      |
| `parse_msg_text` / `parse_msg_file` / `parse_srv_file` / `parse_action_file` | 解析 IDL；`.action` 返回 `ActionSource`（三段用户定义） |
| `expand_action` / `ActionSource`                                             | 展开为 8 个 ROS 2 action `MsgDefinition`                |
| `MsgDefinition` / `MsgField`                                                 | 解析模型                                                |
| `resolve_type` / `ResolvedType`                                              | 类型字符串 → pycdr2 注解表达式                          |
| `generate_all(types, output_dir, root_package="", distro="")`                | 生成全部源码，返回 `GeneratedFile` 列表                 |

---

## 15. 常见问题（FAQ）

**Q1：为什么订阅收不到消息？**
检查：① 发布/订阅的 topic 与 `namespace` 是否一致；② 双方 `message_type` 是否一致（CDR 布局不同会导致反序列化失败，错误会记录在日志中）；③ 订阅是否已调用 `subscribe()`；④ session 是否已被关闭。

**Q2：回调里可以用 async 函数吗？**
不行。同步 `Subscriber` / `Action.feedback_callback` 运行在 Zenoh 线程，只接受同步回调（传入 async 函数会被拒绝并记录错误）。需要异步处理请使用 `zros2.asyncio` 的 `AsyncSubscriber` 与 `invoke_action`。

**Q3：`get_result` 一直阻塞怎么办？**
`get_result` 按 ROS 2 语义阻塞到目标终止。传入 `timeout`（毫秒）限定等待；`None` 表示无限等待。

**Q4：如何判断服务端是否在线？**
用 `wait_for_service(service_name, ros2_type, timeout_ms=...)` 阻塞探测，或 `service_is_ready(...)` 非阻塞探测。两者都要求服务端声明了 `SERVICE_SERVER` 存活 token。

**Q5：zros2 与 ROS 2 能互通吗？**
消息类型按 ROS 2 接口规范生成，使用标准 CDR（CDR_LE，含 `00 01 00 00` 封装头）序列化；通信走 Zenoh 而不是 DDS，与原生 ROS 2 节点互通需要桥接层（存活 token 的 key 格式为 `@/{zenoh_id}/@ros2_lv/...`，由桥接插件声明）。

**Q6：消息字段有界（bounded）时越界会怎样？**
有界数组/字符串/序列在**序列化时**强制校验边界，越界抛异常。

**Q7：`ActionNotAvailableException` 什么时候抛出？**
它属于异常层次中的 `ActionException` 子类，供上层按类型区分处理；动作调用失败时通常抛 `ActionInvokeException`，统一捕获 `ActionException` 即可覆盖两类。

**Q8：生成代码如何与自己的包结构集成？**
`--root-package` 决定导入前缀，例如生成到 `./zros2_msgs` 且 `--root-package zros2_msgs` 时，导入路径为 `from zros2_msgs.my_package.msg import MyMessage`。
