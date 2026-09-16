# zros2 内部开发者指南 / Contributor Guide

> 适用版本：**zros2 2.0.0** · Python ≥ 3.12
> 本文面向 zros2 的维护者与扩展者。使用方开发指南见 [sdk_development.md](./sdk_development.md)（中文）与 [sdk_development_en.md](./sdk_development_en.md)（英文）。**本文件的约定以 `.rules` 为权威来源**，两者冲突时以 `.rules` 为准。

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
├── _session.py          # ZenohSessionProxy：防破坏的共享 session 代理
├── _action_msgs.py      # 内置 action_msgs 协议消息（GoalInfo/GoalStatus/...）
├── exceptions.py        # 异常层次（ZRos2Exception 根）
├── endpoints/           # Publisher / Subscriber / ServiceClient / Action / GoalHandle
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

### 2.2 端点设计要点

| 端点            | 要点                                                                                                                                                                                                                                                                             |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Publisher`     | 构造时即 `declare_publisher`；`publish` 调用 `data.serialize()`；`destroy()` 幂等，销毁后再 publish 抛 `RuntimeError`                                                                                                                                                            |
| `Subscriber`    | 回调运行在 Zenoh 线程，**只接受同步回调**：检测到协程先 `close()` 再抛 `TypeError`（避免 “coroutine was never awaited” 泄漏）；`RLock` 保护订阅状态；重复 `subscribe` 抛 `ValueError`；反序列化异常只记日志                                                                      |
| `ServiceClient` | 基于 zenoh `get`；错误应答抛 `ServiceInvokeException`，无应答抛 `ServiceNotAvailableException`，`zenoh.ZError` 包装为 `ServiceInvokeException`                                                                                                                                   |
| `Action`        | 三个内部服务传输 + 两个订阅；通道路径由 `endpoints/_action_keys.action_key` 生成；`_make_srv_type` 动态构造最小服务类型类并按 `(name, request, response)` 缓存；`goal_id` 用 `os.urandom(16)` 生成；`_active_goal_ids` 集合按 goal_id 过滤反馈；取消全部使用全零通配 `(0,) * 16` |
| `Liveliness`    | key 表达式由 `LivelinessKey` 构造/解析：`@/{zenoh_id}/@ros2_lv/{MP                                                                                                                                                                                                               | MS  | SS  | SC  | AS  | AC}/...`，名称/类型中的 `/`转义为`§`；服务/动作 key 不带 QoS，发布/订阅 key 携带（`Qos.to_key_expr`/`from_key_expr`） |

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
│   parsing    │  Lark 语法 → IR 模型（MsgField, MsgDefinition）
└──────┬──────┘
       ▼
┌─────────────┐
│  semantics   │  resolve_type / ResolvedType：类型字符串 → pycdr2 注解表达式
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

- **parsing/**：Lark 语法解析 `.msg` / `.srv` / `.action`；`.action` 只产出 `ActionSource`（Goal / Result / Feedback 三段）。`_discovery.py` 定义 `VALID_DISTROS`，收集类型时调用 `expand_action` 以便依赖校验看到完整集合。
- **semantics/**：`resolve_type` 解析出 `ResolvedType`；`expand_action` / `ACTION_SPEC` 是 ROS action IDL 展开的唯一来源（5 个传输类型在这里合成，不在 parser 里）；`_utilities.py` 提供默认值表达式、元数据语句、文件头注释等。
- **codegen/**：
  - `_message.py`：`GeneratedFile(path, content)` 冻结 dataclass + `generate_message_module`；
  - `_registry.py`：`REGISTRY_AST` 是注册表的 AST 蓝图（`register`、`register_service`、`register_action`、`get_type`、`has_type`、`iter_types`、`get_service`、`get_action`）；
  - `_service_action.py`：服务/动作 wrapper 合并生成（`SRV_SUFFIXES`、`generate_service_wrappers` / `generate_action_wrappers`；动作后缀表来自 `semantics._action.ACTION_SUFFIXES`）；
  - `_package_init.py`、`_stubs.py`：包初始化模块与 `.pyi` stub。
- **pipeline/**：`build_plan(user_dirs, output_dir, distro, root_package)` → `GenerationPlan`；`execute_plan(plan, dry_run=...)`；`generate_all(types, output_dir, root_package="", distro="")` 六阶段编排，并调用 `_update_root_init` 把注册表函数再导出到根 `__init__.py`。

### 3.2 CLI

`_cli.py`：`build_parser()` / `main()`；入口 `zros2-gen`（`pyproject.toml` 的 `[project.scripts]`）与 `python -m zros2.generator`（`__main__.py`）。参数：`--msg-dirs`、`--output`、`--ros-version`（choices=`VALID_DISTROS`）、`--root-package`、`--dry-run`。

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
- 注意协议内的 `ClassVar` 不能引用类自身类型参数（pyright 限制）——`_protocols.py` 中带具名 `# pyright: ignore[reportGeneralTypeIssues]` 注释，勿删。

---

## 7. 编码规范

- **Python 3.12 现代语法**优先：PEP 695（类型参数）、PEP 673（`Self`）、PEP 604（`X | Y`）、PEP 698（`typing.override`）、PEP 692（TypedDict `**kwargs`）、PEP 654（`ExceptionGroup`）、PEP 646（`TypeVarTuple`）。避免 `Optional[X]` / `Union[X, Y]` / `typing.List` 等旧写法。
- **所有函数签名与公共类属性必须有类型注解**。
- 字符串统一**双引号**（含 docstring 与错误消息）。
- 每个 `.py` 文件有**模块级 docstring** 说明用途。
- docstring 用 Google 风格（`Args:` / `Raises:` / `Returns:`）；**只给公开 API 写 docstring**，内部函数尽量精简。
- 行长：软 88、硬 99。
- 命名：函数/方法/变量 `snake_case`；类/协议/dataclass `PascalCase`；常量与 ROS 常量字段 `UPPER_CASE`；私有符号 `_` 前缀。
- 导入顺序：标准库 → 第三方 → 本地（空行分隔）；优先绝对导入，同包内允许相对导入；`import` 类/函数而非模块（另有说明除外）。
- 异常层次根为 `ZRos2Exception`（见使用方文档第 11 节）；抛具体异常，只在公开 API 边界宽捕获。
- **上下文管理器必须幂等**（`destroy()` 先检查 `None` 再 undeclare）。
- 注释只解释非显然的意图/约束/权衡，不重复代码。

### 类型检查（pyright）

`pyrightconfig.json` 固定策略：`include` 为 `src`、`tests`、`benchmarks`；`reportUnusedFunction` 全局开启；`tests/` 与 `benchmarks/` **不**启用 unknown-type 规则（mock 密集代码会合法产生 `Unknown`）。`# pyright: ignore[...]` 只在规则实际触发处添加并具名规则。

---

## 8. 测试组织

pytest，无 `unittest.TestCase`；测试类用 `TestPascalCase` 描述被测单元；文件名 `test_<module_name>.py`；fixtures 集中在 `conftest.py`。

| 测试文件                                                                                                                                                    | 覆盖                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `test_parser_unit.py` / `test_type_grammar.py`                                                                                                              | Lark 语法、类型表达式、字段级解析                          |
| `test_codegen_msg_unit.py` / `test_codegen_init_unit.py` / `test_codegen_pyi_unit.py` / `test_codegen_registry_unit.py` / `test_codegen_srv_action_unit.py` | 消息模块、初始化模块、stub、注册表、服务/动作 wrapper 生成 |
| `test_pipeline_plan_unit.py` / `test_codegen_orchestrator_unit.py` / `test_generator.py`                                                                    | plan 构建、编排、校验、生成器集成                          |
| `test_publisher_unit.py` / `test_subscriber_unit.py` / `test_service_unit.py` / `test_action_unit.py` / `test_action_msgs_unit.py`                          | 端点行为                                                   |
| `test_client_unit.py`                                                                                                                                       | `ZRosClient` 工厂方法与就绪探测                            |
| `test_liveliness_unit.py`                                                                                                                                   | key 表达式构建与解析、QoS                                  |
| `test_protocols.py` / `test_runtime_structure_unit.py` / `test_runtime_contract.py`                                                                         | 协议结构性检查、运行时结构与 ABI 契约                      |
| `test_type_map_unit.py` / `test_utilities.py` / `test_utils_unit.py`                                                                                        | 类型映射、默认值、`from_attributes` 等工具                 |
| `test_asyncio_*.py`                                                                                                                                         | asyncio 门面（service/action/endpoints/liveliness/client） |
| `test_integration.py`                                                                                                                                       | 端到端生成 + 校验                                          |
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

`.github/workflows/ci.yml`：push / PR 到 `master` 触发（`*.md` 与 `docs/**` 变更不触发）；Python 3.14；`pip install -e ".[dev]"` + `pytest-cov`；运行 `pytest tests/` 并产出 `coverage.xml`（上传为 artifact）。本地提交前至少保证测试与 pyright 全绿。

---

## 12. 提交前检查清单

- [ ] **完整测试套件**：`pytest` 通过，无新增失败。
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
3. `codegen/`：`generate_message_module` 或 wrapper 生成的 AST 逻辑 + `.pyi` stub；
4. `pipeline/`：确认收集/校验/写盘无需调整；
5. 测试：parser 单测 → codegen 单测 → 契约测试 → 集成测试；基准全跑；
6. 若生成产物新增了 `zros2.*` 导入，更新 `RUNTIME_CONTRACT`。

### 场景 C：移动一个运行时内部模块

1. 移动后更新包内相对导入与 `__init__.py` 再导出；
2. 若该模块被生成器硬编码引用（当前仅 `zros2.types._utils` 的 `from_attributes`），在**同一次变更**中更新 `RUNTIME_CONTRACT` 并重新生成产物，否则契约测试会失败；
3. 检查 README/docstring 示例不引用 `_` 前缀路径。
