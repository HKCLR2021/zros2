# ROS 2 Builtin Message Definitions

This directory contains the standard ROS 2 `.msg` and `.srv` definition files
for distributions Humble and above.  They are **static snapshots** — no tooling
or external dependency is needed to use or maintain them.

## Source Repositories

| Repository | Packages |
|-----------|----------|
| [ros2/common_interfaces](https://github.com/ros2/common_interfaces) | `std_msgs`, `geometry_msgs`, `sensor_msgs`, `nav_msgs`, `shape_msgs`, `visualization_msgs`, `trajectory_msgs`, `stereo_msgs`, `diagnostic_msgs`, `actionlib_msgs` |
| [ros2/rcl_interfaces](https://github.com/ros2/rcl_interfaces) | `builtin_interfaces`, `rcl_interfaces`, `lifecycle_msgs`, `action_msgs` |
| [ros2/rmw_dds_common](https://github.com/ros2/rmw_dds_common) | `rmw_dds_common` |
| [ros2/rosbag2](https://github.com/ros2/rosbag2) | `rosbag2_interfaces` |
| [ros2/unique_identifier_msgs](https://github.com/ros2/unique_identifier_msgs) | `unique_identifier_msgs` |
| [ros2/common_interfaces](https://github.com/ros2/common_interfaces) (std_srvs) | `std_srvs` |
| [ros2/rcl](https://github.com/ros2/rcl) | `rosgraph_msgs`, `statistics_msgs` |
| [ros2/geometry2](https://github.com/ros2/geometry2) | `tf2_msgs` |

## Updating

To add a new ROS 2 distro or refresh a definition:

1. Go to the corresponding GitHub repo / tag (e.g. `humble`, `iron`, `jazzy`, `rolling`)
2. Copy the relevant `.msg` / `.srv` files into `{distro}/{package}/{msg,srv}/`
3. Run the test suite to verify nothing broke

All files are hand-maintained — there is no code that regenerates them.
