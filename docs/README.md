# zros2 documentation

The language of every documentation file is explicit in its name:

| Language | File naming | Current files |
|---|---|---|
| English | no suffix | `README.md`, `docs/README.md`, `docs/sdk_development.md`, `docs/developer_guide.md` |
| Chinese | `_zh` suffix | `docs/sdk_development_zh.md`, `docs/developer_guide_zh.md` |

The repository root [README](../README.md) is English.

## User documentation

- [SDK development guide (English)](./sdk_development.md)
- [SDK guide (Chinese)](./sdk_development_zh.md)

## Contributor documentation

- [Internal developer / architecture guide (English)](./developer_guide.md)
- [Internal developer guide (Chinese)](./developer_guide_zh.md)

`.rules` remains the source of truth for project conventions; both guides
describe the same architecture and workflows.

## Scope note

zros2 is a **client-side** ROS 2 library for Zenoh. It is not the Zenoh ROS 2
bridge, a ROS 2 runtime, or an rclpy replacement. See the root README for the
full scope, target audience, and limitations.
