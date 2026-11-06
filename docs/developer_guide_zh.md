# zros2 内部开发者指南 / Contributor Guide

> 适用版本：**zros2 2.0.0** · Python ≥ 3.12
> 本文面向 zros2 的维护者与扩展者。使用方开发指南见 [sdk_development_zh.md](./sdk_development_zh.md)（中文）与 [sdk_development.md](./sdk_development.md)（英文）；英文版开发者指南见 [developer_guide.md](./developer_guide.md)。**本文件的约定以 `.rules` 为权威来源**，两者冲突时以 `.rules` 为准。

---

## 目录

1. [项目概览与仓库布局](#1-项目概览与仓库布局)
2. [运行时架构](#2-运行时架构)
3. [生成器架构](#3-生成器架构)
4. [公共 / 私有 API 设计约定](#4-公共--私有-api-设计约定)
5. [Codegen ↔ Runtime ABI 契约](#5-codegen--runtime-abi-契约)
6. [类型系统规则](#6-类型系统规则)
7. [编码规范](#7-编码规范)
8. [测试组织](#8-测试组织)
9. [基准测试](#9-基准测试)
10. [开发环境与验证](#10-开发环境与验证)
11. [CI 说明](#11-ci-说明)
12. [提交前检查清单](#12-提交前检查清单)
13. [提交与 PR 约定](#13-提交与-pr-约定)
14. [典型变更走查](#14-典型变更走查)

---

## 1. 项目概览与仓库布局

**zros2** 是一个基于 Zenoh 的轻量级 ROS 2 风格通信库：运行时提供发布/订阅、服务、动作、发现原语；`zros2-gen` 生成器把 `.msg` / `.srv` / `.action` 文件静态编译为 Python dataclass（`pycdr2.IdlMeta`，CDR 序列化）。

```
src/zros2/
├── __init__.py          # 顶层公开 API 再导出（__all__）
├── _client.py           # ZRosClient：统一入口、工厂方法、服务就绪探测
├── _namespace.py        # join_name：设备命名空间与图名称拼接（sync/async 共用）
├── _session.py          # ZenohSessionProxy：防破坏的共享 session 代理
├── _action_msgs.py      # 内置 action_msgs 协议消息（GoalInfo/GoalStatus/...）
├── exceptions.py        # 异常层次（ZRos2Exception 根）
├── endpoints/           # Publisher / Subscriber / ServiceClient / Action / GoalHandle
│   └── _action_keys.py  # action_key：Zenoh 上五条 `_action/` 通道
├── types/               # RosMessage 协议、RosService/RosAction/RosActionView、容器
├── discovery/           # Liveliness / LivelinessType / Qos / LivelinessKey
├── asyncio/             # 可选 asyncio 门面（AsyncRobotClient 等）
└── generator/           # zros2-gen：parsing/ → semantics/ → codegen/ → pipeline/
    └── assets/builtin_msgs/   # 各发行版捆绑 IDL（humble/iron/jazzy/kilted/lyrical）
tests/                   # pytest 套件
benchmarks/              # pytest-benchmark 套件（benchmarks.py, compare.py）
```

模块命名规则：实现模块一律 `_` 前缀（`_client.py`、`types/_protocols.py`），私有符号一律 `_` 前缀，且从不进入 `__all__`。

---

## 2. 运行时架构

### 2.1 会话所有权与代理

`ZRosClient.__init__` 打开 `zenoh.Session` 并持有它；`close()` 幂等（先检查 `is_closed()`）。所有端点只接收 `ZenohSessionProxy` 而非原生 session：

- 代理通过 `__getattr__` 委托属性访问，但禁止 `close` / `destroy` / `__del__` / `undeclare`（抛 `PermissionError`）；
- `__setattr__` 一律拒绝（`PermissionError`）；
- 这样端点无法误关共享 session，生命周期只归 `ZRosClient` 管。

工厂方法（以及 asyncio 门面的对应入口）用 `_namespace.join_name(namespace, name)` 拼图名称：namespace 与 name 两侧的 `/` 都会规范化；空命名空间也会去掉 `name` 的前导 `/`，非空时拼成 `{namespace}/{name}`。不要在各端点再复制这一行。

### 2.2 端点设计要点

| 端点            | 要点                                                                                                                                                                                                                                                                             |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Publisher`     | 构造时即 `declare_publisher`；`publish` 调用 `data.serialize()`；`destroy()` 幂等，销毁后再 publish 抛 `RuntimeError`                                                                                                                                                            |
| `Subscriber`    | 回调运行在 Zenoh 线程，**只接受同步回调**：检测到协程先 `close()` 再抛 `TypeError`（避免 “coroutine was never awaited” 泄漏）；`RLock` 保护订阅状态；重复 `subscribe` 抛 `ValueError`；反序列化异常只记日志                                                                      |
| `ServiceClient` | 基于 zenoh `get`；错误应答抛 `ServiceInvokeException`，无应答抛 `ServiceNotAvailableException`，`zenoh.ZError` 包装为 `ServiceInvokeException`                                                                                                                                   |
| `Action`        | `_action_state.py` 持有 `GoalHandle`；`_action_transport.py` 负责三个内部服务传输与两个订阅；通道路径由 `endpoints/_action_keys.action_key` 生成；`_make_srv_type` 按 `(name, request, response)` 缓存；`goal_id` 用 `os.urandom(16)` 生成且统一为 `bytes`；`_active_goal_ids` 过滤反馈；取消全部使用全零 `b"\x00" * 16` |
| `Liveliness`    | key 表达式由 `LivelinessKey` 构造/解析：`@/{zenoh_id}/@ros2_lv/{MP,MS,SS,SC,AS,AC}/...`；名称/类型中的 `/` 转义为 `§`；服务/动作 key 不带 QoS，发布/订阅 key 携带（`Qos.to_key_expr` / `from_key_expr`）                                                                         |

服务就绪轮询在 `discovery/_readiness.py`；`ZRosClient.service_is_ready()` / `wait_for_service()` 只做委托。

### 2.3 内置 action_msgs

生成器不产出 `action_msgs` 类型，因此 `_action_msgs.py` 手工定义了 `GoalInfo` / `GoalStatus` / `GoalStatusArray` / `CancelGoal_Request` / `CancelGoal_Response`（外加 `Time`）。它们是普通 `pycdr2.IdlStruct`，结构性满足 `RosMessage`；`GoalInfo.goal_id` 用 `array[uint8, 16]` 替代 `unique_identifier_msgs/UUID`（CDR 编码相同，与生成器 `GOAL_ID_TYPE` 对齐）。类布局刻意镜像生成器的输出（`@dataclass(init=False)` + 手写 `__init__`）。

### 2.4 asyncio 门面（`zros2.asyncio`）

核心 API 同步阻塞，门面不改变核心：

- 阻塞调用用 `asyncio.to_thread` 卸载（`invoke_service`、`query_liveliness`、`AsyncPublisher.publish`）；
- Zenoh 线程回调通过**有界队列（容量 100）** 桥接进事件循环：`loop.call_soon_threadsafe(_put_nowait, ...)`，`QueueFull` 时丢最旧——注意 `put_nowait` 的异常捕获必须发生在 loop 线程上，这正是 `call_soon_threadsafe` 包一层的原因；
- 生成器（`invoke_action` / `watch_liveliness` / `AsyncSubscriber.__anext__`）的清理编排：外层 `async for` 结束后显式 `await inner.aclose()`，保证端点上下文管理器一定 undeclare；
- 事件：`ActionFeedback(feedback)`、`ActionResult(status, result)` 为冻结 dataclass。

---

## 3. 生成器架构

四阶段管线：`parsing` → `semantics` → `codegen` → `pipeline`。生成 Python 一律使用 **`ast` 模块**构造（无字符串模板）。

```
.msg / .srv / .action 文件
        │
        ▼
┌─────────────┐
│   parsing    │  Lark → IR（MsgField / MsgDefinition；.action → ActionSource）
└──────┬──────┘
       ▼
┌─────────────┐
│  semantics   │  expand_action（8 个 action 类型）+ resolve_type → pycdr2 注解
└──────┬──────┘
       ▼
┌─────────────┐
│   codegen    │  Python ast → 源码（dataclass + .pyi stub + 注册表）
└──────┬──────┘
       ▼
┌─────────────┐
│  pipeline    │  build_plan / execute_plan / generate_all：收集、合并、校验、写盘
└─────────────┘
       │
       ▼
生成后的 Python 模块
```

### 3.1 各阶段职责

- **parsing/**：Lark 语法解析 `.msg` / `.srv` / `.action`。`.action` **只**产出 `ActionSource`（Goal / Result / Feedback），不编码传输字段。`_discovery.py` 定义 `VALID_DISTROS`、`find_msg_dirs`、文件迭代与依赖校验；不再负责类型收集，也不依赖 `semantics`。
- **semantics/**：`expand_action` / `ACTION_SPEC` / `GOAL_ID_TYPE` 是 ROS action IDL 展开的**唯一来源**。`_resolve_types.py` 负责 `ResolvedType`；`_literal_values.py` 把 `.msg` 文本解析为 Python 值（不 import `ast`）；`_type_context.py` 统一常量表与 bound；`_native_types.py` 提供 runtime/stub 共用的 Python 类型映射；`_field_semantics.py` 提供 `FieldSemantics`。`_utilities.py` 只保留 header/命名/default helper，不再产出 AST。
- **codegen/**：
  - `_file.py`：`GeneratedFile(path, content)` 冻结 dataclass；pipeline/writer **只**依赖此 DTO；
  - `_message/`：`__init__.py`（公开入口）→ `_context.py`（语义上下文）→ `_plan.py`（字段计划）→ `_defaults.py`（默认值 AST）→ `_methods.py`（to_dict/from_dict）→ `_assemble.py`（模块组装）；
  - `_stubs.py`：只消费 `semantics` 的 `native_stub_type` / `stub_annotation` / `literal`，**不 import** `_message`；
  - `_merge.py`：通用、**只接收源码**的 AST 合并（import 去重、自引用删除、body 拼接），不得 import renderer；
  - `_service_merge.py`：渲染各子类型并委托 `_merge.py` 合并；
  - `_service_action.py`：service/action wrapper 与注册调用；`_wrapper.py`：wrapper class AST；
  - `_root_init.py`：root package `__init__.py` 策略；
  - `_registry.py`：组装 `REGISTRY_AST`；各 section 分别在 `_registry_common.py`、`_registry_messages.py`、`_registry_services.py`、`_registry_actions.py`；`_package_init.py`：包级 `__init__.py`。
- **pipeline/**：`_collect.py` 收集并展开类型；`build_plan` → `GenerationPlan`；`execute_plan(plan, dry_run=...)`；`generate_all` 六阶段编排。action 子包 `__init__` 的导出过滤使用 `ACTION_WIRE_SUFFIXES`。

### 3.2 CLI

`_cli.py`：`build_parser()` / `main()`；入口 `zros2-gen`（`pyproject.toml` 的 `[project.scripts]`）与 `python -m zros2.generator`（`__main__.py`）。参数：`--msg-dirs`、`--output`、`--ros-version`（choices=`VALID_DISTROS`）、`--root-package`、`--dry-run`。`--msg-dirs` 可以是包目录，也可以是 workspace（扫描直接子目录里含 `msg/` / `srv/` / `action/` 的包）；找不到任何包时 CLI 报错退出。

### 3.3 内置消息资产

`assets/builtin_msgs/` 按发行版捆绑官方 IDL。构建产物包含这些资产（见 `pyproject.toml` 的 `[tool.setuptools.package-data]`）。用户类型与内置类型同名时用户类型覆盖。

---

## 4. 公共 / 私有 API 设计约定

### 公开面（Public surface）

公开 API **只**由各包 `__init__.py` 通过 `__all__` 再导出：

- `zros2`：`ZRosClient`、端点（`Publisher`、`Subscriber`、`ServiceClient`、`Action`、`GoalHandle`）、发现（`Liveliness`、`LivelinessType`、`Qos`）、类型协议/容器、内置动作协议消息（`GoalInfo`、`GoalStatus`、`GoalStatusArray`、`CancelGoal_Request`、`CancelGoal_Response`），以及 `zenoh` 的 `Reply` / `Sample` / `SampleKind`。
- `zros2.exceptions`：`ZRos2Exception` 及 `Service*Exception` / `Action*Exception` 子类。
- `zros2.asyncio`：`AsyncRobotClient`（接受 `ZRosClient` 或 session 代理）、`ActionFeedback` / `ActionResult` 事件、`AsyncPublisher` / `AsyncSubscriber`；**无模块级入口函数**。
- `zros2.types`：恰好六个符号——`RosMessage`、`RosService`、`RosAction`、`RosActionView`、`ServiceTypes`、`ActionTypes`。
- `zros2.generator`：`VALID_DISTROS`、`parse_*` 函数、`ActionSource`、`expand_action`、`ResolvedType` / `resolve_type`、`generate_all`。
- `zros2.generator.codegen`：`GeneratedFile` 与 `generate_*` 函数（编程式 API）。

协议（`RosMessage` / `RosService` / `RosAction` / `RosActionView`）是公开类型契约：生成的消息类与下游代码**结构性**满足它们，不需要继承 zros2。

### 私有实现（Private implementation）

- 实现模块 `_` 前缀（`_client.py`、`endpoints/_publisher.py`、`types/_protocols.py`、`generator/**/_*.py`、`_cli.py`）；私有符号 `_` 前缀且从不进入 `__all__`。
- 内部模块可以自由改名/移动——但公开导入路径（经 `__init__.py` 再导出）不得改变；**不要**为已经移入子包的符号保留兼容 shim。
- **文档即契约**：README 与 docstring 示例严禁出现 `_` 前缀模块的导入（如 `zros2.types._utils`、`zros2._session`）。下游需要某能力时，先提升到公开面。

### 变更清单（新增/删除公开符号时，一次改动内同步更新）

1. 所属包 `__init__.py` 及其 `__all__`；
2. README（协议表 / 用法示例）；
3. `.rules`；
4. 生成器硬编码引用该符号时，同步更新 `tests/test_runtime_contract.py` 的白名单。

---

## 5. Codegen ↔ Runtime ABI 契约

生成器把少量运行时符号**硬编码**进生成产物（生成 ABI）：

- `zros2.types` → `RosMessage`、`ServiceTypes`、`ActionTypes`
- `zros2.types._utils` → `from_attributes`（ABI 中唯一的 `_` 前缀符号：私有模块移动后必须重新生成产物）

`tests/test_runtime_contract.py` 的 `RUNTIME_CONTRACT` 是权威白名单，契约测试分四组：

| 测试组                       | 校验内容                                                                                                      |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `TestStaticImportContract`   | 生成器产出的每个 `zros2.*` 导入必须命中白名单**且**在已安装运行时中可解析；白名单不得静默漂移                 |
| `TestRegistryContract`       | `REGISTRY_AST` 必须定义根 `__init__.py` 再导出的全部注册表函数                                                |
| `TestContainerFieldContract` | `ServiceTypes(...)` / `ActionTypes(...)` 生成调用中的关键字必须等于容器 dataclass 字段名                      |
| `TestProtocolContract`       | 生成的消息类满足 `RosMessage`；服务/动作 wrapper 暴露 `RosService` / `RosAction` / `RosActionView` 的全部成员 |

**改哪边都必须同步改白名单，测试会在失败时大声报错。** 例如把 `from_attributes` 移到公开模块：生成器与 `RUNTIME_CONTRACT` 要在同一次变更中更新，并重新生成既有产物。

---

## 6. 类型系统规则

- 泛型使用 **PEP 695 类型参数语法**并绑定 `RosMessage`（`class Publisher[MsgT: RosMessage]`、`def create_publisher[MsgT: RosMessage](...)`）。**不**定义/导出共享的模块级 TypeVar——每个类或函数各自声明。
- `RosActionView` 是动作类型的 3 参数语义视图（`GoalT` / `ResultT` / `FeedbackT`），给只转发 goal 或观察结果/反馈的泛型消费代码用，隐藏 5 个传输子类型。
- `@runtime_checkable` 只做**存在性检查**：`isinstance` 作用于成员协议（`RosService`、`RosAction`、`RosActionView`）只测 `hasattr(Request/Response/Goal/...)`，**不得用于运行时校验**。
- 用结构化协议而非 ABC；`isinstance(x, RosMessage)` 仅在确实需要运行时检查时使用。
- `RosService` / `RosAction` / `RosActionView` 描述的是生成后的**类对象**，不是实例；成员使用普通属性（`ClassVar` 不能引用协议自身的类型参数）。因此直接传类对象（`action_type: RosAction[...]`），不再写 `type[RosAction[...]]`。`pyrightconfig.json` 只检查 `src`；`tests` / `benchmarks` 明确不在类型检查范围内。

---

## 7. 编码规范

- **Python 3.12 现代语法**优先：PEP 695（类型参数）、PEP 673（`Self`）、PEP 604（`X | Y`）、PEP 698（`typing.override`）、PEP 692（TypedDict `**kwargs`）、PEP 654（`ExceptionGroup`）、PEP 646（`TypeVarTuple`）。避免 `Optional[X]` / `Union[X, Y]` / `typing.List` 等旧写法。
- **所有函数签名与公共类属性必须有类型注解**。
- 字符串统一**双引号**（含 docstring 与错误消息）。
- 每个 `.py` 文件有**模块级 docstring** 说明用途。
- docstring 用 Google 风格（`Args:` / `Raises:` / `Returns:`）；**只给公开 API 写 docstring**，内部函数尽量精简。
- 行长：软 88、硬 99。
- 命名：函数/方法/变量 `snake_case`；类/协议/dataclass `PascalCase`；常量与 ROS 常量字段 `UPPER_CASE`；私有符号 `_` 前缀。
- 导入顺序：标准库 → 第三方 → 本地（空行分隔）；跨包一律绝对导入（`from zros2.types...`），只有同包 `.` 相对导入允许；`..` / `...` 父级相对导入禁止，由 `tests/test_architecture.py` 强制；`import` 类/函数而非模块（另有说明除外）。
- 异常层次根为 `ZRos2Exception`（见使用方文档第 11 节）；抛具体异常，只在公开 API 边界宽捕获。
- **上下文管理器必须幂等**（`destroy()` 先检查 `None` 再 undeclare）。
- 注释只解释非显然的意图/约束/权衡，不重复代码。

### 类型检查（pyright）

`pyrightconfig.json` 只检查 **`src`**；`reportUnusedImport` 为 error。`tests/` 与 `benchmarks/` 明确不参与静态类型检查，只靠运行时测试验证。禁止添加 `# pyright: ignore`；应修正注解或类型边界。Zenoh 自身的类型信息不完整属于外部依赖问题，不在 zros2 内建模，也不得作为降低全局检查等级的理由。

---

## 8. 测试组织

pytest，无 `unittest.TestCase`；测试类用 `TestPascalCase` 描述被测单元；文件名 `test_<module_name>.py`；fixtures 集中在 `conftest.py`。

| 测试文件                                                                                                                                                    | 覆盖                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `test_parser_unit.py` / `test_type_grammar.py` / `test_action_expand_unit.py`                                                                               | Lark 语法、类型表达式、字段级解析、action IDL 展开         |
| `test_codegen_msg_unit.py` / `test_codegen_init_unit.py` / `test_codegen_pyi_unit.py` / `test_codegen_registry_unit.py` / `test_codegen_srv_action_unit.py` | 消息模块、初始化模块、stub、注册表、服务/动作 wrapper 生成 |
| `test_pipeline_plan_unit.py` / `test_codegen_orchestrator_unit.py` / `test_generator.py`                                                                    | plan 构建、编排、校验、生成器集成                          |
| `test_publisher_unit.py` / `test_subscriber_unit.py` / `test_service_unit.py` / `test_action_unit.py` / `test_action_msgs_unit.py`                          | 端点行为（含 `action_key` 通道映射）                       |
| `test_client_unit.py` / `test_namespace_unit.py`                                                                                                            | `ZRosClient` 工厂方法、就绪探测、`join_name`               |
| `test_liveliness_unit.py`                                                                                                                                   | key 表达式构建与解析、QoS                                  |
| `test_protocols.py` / `test_runtime_structure_unit.py` / `test_runtime_contract.py`                                                                         | 协议结构性检查、运行时结构与 ABI 契约                      |
| `test_type_map_unit.py` / `test_utilities.py` / `test_utils_unit.py`                                                                                        | 类型映射、默认值、`from_attributes` 等工具                 |
| `test_asyncio_*.py`                                                                                                                                         | asyncio 门面（service/action/endpoints/liveliness/client） |
| `test_integration.py`                                                                                                                                       | 本机两个 Zenoh peer 的 pub/sub、service、action 互通       |
| `test_proxies_unit.py`                                                                                                                                      | `ZenohSessionProxy` 保护语义                               |

新增功能/修复必须配套测试；新 `_` 前缀函数要么被测试覆盖（具名 ignore 才合理），要么删除。

---

## 9. 基准测试

`benchmarks/benchmarks.py` + `compare.py`，基于 pytest-benchmark：

```bash
pytest benchmarks/ --benchmark-only   # 应收集 96 个测试
```

生成器输出发生变化时必须完整运行一遍基准，确认无性能回退。

---

## 10. 开发环境与验证

```bash
pip install -e ".[dev]"

# 全部测试
pytest

# 导入排序 / lint
ruff check src tests benchmarks

# 类型检查：0 错误 0 警告（含改动波及文件）
npx pyright

# 生成器冒烟
python -m zros2.generator --help

# 契约测试（生成 ABI）
pytest tests/test_runtime_contract.py -v

# 基准收集检查
pytest benchmarks/ --benchmark-only --collect-only
```

---

## 11. CI 说明

`.github/workflows/ci.yml`：push / PR 到 `master` 触发（`*.md` 与 `docs/**` 变更不触发）；Python **3.12 / 3.13 / 3.14** matrix；`pip install -e ".[dev]"`；运行 `pytest tests/`（覆盖率门槛 95%）并产出 `coverage.xml`；独立 `type-check` job 运行 `pyright`；独立 `package` job 构建 wheel、安装并验证内置 assets。本地提交前至少保证测试与 pyright 全绿。

`.github/workflows/release.yml`：推送匹配 `v*` 的 tag 时触发。校验 tag（`vX.Y.Z`）与 `pyproject.toml` 的 `version` 一致，跑完整测试，再 `python -m build --wheel` 打出 `py3-none-any` wheel，并创建带该 wheel 的 **draft** GitHub Release。确认后手动点 Publish。zros2 是纯 Python，一份 wheel 覆盖各 OS / 架构；不发布到 PyPI。

发版步骤：

1. 把 `pyproject.toml` 的 `version` 改成目标版本（例如 `2.0.0`）并提交；
2. 打 tag 并推送：`git tag v2.0.0 && git push origin v2.0.0`；
3. workflow 自动创建 draft Release，附带 `zros2-2.0.0-py3-none-any.whl`；检查 release notes 后点 Publish。

---

## 12. 提交前检查清单

- [ ] **完整测试套件**：`pytest` 通过，无新增失败。
- [ ] **Lint / 导入排序**：`ruff check src tests benchmarks` 通过（import block 已排序、无未使用导入）。
- [ ] **类型检查**：`npx pyright` 全项目 0 错误 0 警告（含改动波及文件）。
- [ ] **公开 API 完整性**：公共符号有变更时，所属包 `__init__.py` + `__all__`、README（协议表/示例）、`.rules`、契约白名单同步更新。
- [ ] **契约测试**：`tests/test_runtime_contract.py` 通过——生成器硬编码的每个 `zros2.*` 导入仍可解析。
- [ ] **生成器冒烟**：生成器有变更时 `python -m zros2.generator --help` 可运行，且 `pytest benchmarks/ --benchmark-only` 正常收集（96 个）；生成输出变化时完整运行基准。
- [ ] **文档即契约**：README/docstring 示例无 `_` 前缀模块导入。
- [ ] **无死代码**：新 `_` 前缀函数要么被测试覆盖（具名 ignore 合理）要么删除。
- [ ] **Diff 审查**：`git --no-pager diff` 只有预期改动，无杂散文件/调试残留。
- [ ] **提交信息**：祈使语气，≤ 72 字符主题，按提交约定带 scope 前缀。

---

## 13. 提交与 PR 约定

- 提交信息：**祈使语气**、首字母大写、主题 ≤ 72 字符。
  - 好：`Add bounded string support to parser`
  - 坏：`fixed bug` / `more changes`
- Scope 前缀鼓励使用：`parser:`、`codegen:`、`types:`、`docs:`、`test:` 等。

---

## 14. 典型变更走查

### 场景 A：新增一个公开符号（如公开一个工具函数）

1. 在所属包 `__init__.py` 中导入并加入 `__all__`；
2. 同步更新 README（协议表或用法示例）、`.rules`；
3. 若生成器会硬编码引用它，同一次变更更新 `RUNTIME_CONTRACT` 并重新生成产物；
4. 补测试（结构/单元），跑 `pytest` + `npx pyright`；
5. 走完第 12 节检查清单后提交。

### 场景 B：给生成器新增一种类型形态

1. `parsing/`：Lark 语法与 `MsgField` 模型（若需要新字段形态）；
2. `semantics/`：`resolve_type` 的分支与 `ResolvedType` 注解表达式；
3. `codegen/`：`generate_message_module` 或 wrapper 生成的 AST 逻辑 + `.pyi` stub（stub 走 `TypeInfo`，不要对注解字符串再 regex）；
4. `pipeline/`：确认收集/校验/写盘无需调整；
5. 测试：parser 单测 → codegen 单测 → 契约测试 → 集成测试；基准全跑；
6. 若生成产物新增了 `zros2.*` 导入，更新 `RUNTIME_CONTRACT`。

### 场景 C：移动一个运行时内部模块

1. 移动后更新包内相对导入与 `__init__.py` 再导出；
2. 若该模块被生成器硬编码引用（当前仅 `zros2.types._utils` 的 `from_attributes`），在**同一次变更**中更新 `RUNTIME_CONTRACT` 并重新生成产物，否则契约测试会失败；
3. 检查 README/docstring 示例不引用 `_` 前缀路径。

### 场景 D：改 ROS action 传输类型布局

1. **只改** `semantics/_action.py` 的 `ACTION_SPEC` / `GOAL_ID_TYPE`（parser 不得再写 `uint8[16]` 或 `SendGoal_*`）；
2. codegen 后缀表与 pipeline 导出过滤从该 spec 推导，不要另写一份；
3. runtime 的 Zenoh 通道路径在 `endpoints/_action_keys.py`，与 IDL 展开分开；`_action_msgs.py` 的 `goal_id` 布局与 `GOAL_ID_TYPE` 对齐；
4. 补 `test_action_expand_unit.py`，再跑生成器集成测试。改 `GOAL_ID_TYPE` 等于改 wire，需要与 `zenoh-bridge-ros2dds` 对打后再做。
