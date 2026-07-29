"""Tests for the public runtime API surface after package restructuring."""

import zros2
from zros2 import (
    Action,
    Liveliness,
    LivelinessType,
    Publisher,
    Qos,
    ServiceClient,
    Subscriber,
    ZenohSessionProxy,
    ZRosClient,
)
from zros2.discovery import (
    Liveliness as DiscoveryLiveliness,
)
from zros2.discovery import (
    LivelinessType as DiscoveryLivelinessType,
)
from zros2.discovery import (
    Qos as DiscoveryQos,
)
from zros2.endpoints import (
    Action as EndpointAction,
)
from zros2.endpoints import (
    Publisher as EndpointPublisher,
)
from zros2.endpoints import (
    ServiceClient as EndpointServiceClient,
)
from zros2.endpoints import (
    Subscriber as EndpointSubscriber,
)


def test_root_package_reexports_canonical_runtime_symbols():
    """``zros2`` should re-export the canonical runtime classes."""
    assert zros2.ZRosClient is ZRosClient
    assert zros2.Action is EndpointAction is Action
    assert zros2.Publisher is EndpointPublisher is Publisher
    assert zros2.Subscriber is EndpointSubscriber is Subscriber
    assert zros2.ServiceClient is EndpointServiceClient is ServiceClient
    assert zros2.Liveliness is DiscoveryLiveliness is Liveliness
    assert zros2.LivelinessType is DiscoveryLivelinessType is LivelinessType
    assert zros2.Qos is DiscoveryQos is Qos
    assert zros2.ZenohSessionProxy is ZenohSessionProxy
