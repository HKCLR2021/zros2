"""Unit tests for :class:`zros2._client.ZRosClient` error paths."""

import os
import tempfile

import pytest

from zros2.exceptions import ZRos2Exception


class TestZRosClientInit:
    """Tests for ZRosClient constructor error handling."""

    def test_init_raises_filenotfound_for_nonexistent_path(self):
        """Passing a non-existent file path should raise FileNotFoundError."""
        from zros2 import ZRosClient

        with pytest.raises(FileNotFoundError, match="not found"):
            ZRosClient("/tmp/nonexistent_zenoh_config.json5")

    def test_init_raises_typeerror_for_invalid_type(self):
        """Passing an invalid type (e.g. int) should raise TypeError."""
        from zros2 import ZRosClient

        with pytest.raises(TypeError, match="Expected str or zenoh.Config"):
            ZRosClient(42)  # type: ignore[arg-type]

    def test_init_with_config_file(self):
        """Passing a valid config file path should succeed."""
        import tempfile
        import json

        config_data = {
            "mode": "peer",
            "scouting": {"multicast": {"enabled": False}},
            "listen": {"endpoints": ["tcp/127.0.0.1:0"]},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json5", delete=False
        ) as f:
            json.dump(config_data, f)
            tmp_path = f.name

        try:
            from zros2 import ZRosClient
            client = ZRosClient(tmp_path)
            try:
                assert client.session is not None
            finally:
                client._zenoh_session.close()
        finally:
            os.unlink(tmp_path)

    def test_init_with_config_object_succeeds(self):
        """Passing a valid zenoh.Config should not raise (integration)."""
        import zenoh

        config = zenoh.Config()
        config.insert_json5("mode", '"peer"')
        config.insert_json5("scouting/multicast/enabled", "false")
        # Use an ephemeral port so we don't conflict
        config.insert_json5("listen/endpoints", '["tcp/127.0.0.1:0"]')

        from zros2 import ZRosClient

        client = ZRosClient(config=config)
        try:
            assert client.session is not None
        finally:
            client._zenoh_session.close()

    def test_context_manager(self):
        """ZRosClient should work as a context manager."""
        import zenoh

        config = zenoh.Config()
        config.insert_json5("mode", '"peer"')
        config.insert_json5("scouting/multicast/enabled", "false")
        config.insert_json5("listen/endpoints", '["tcp/127.0.0.1:0"]')

        from zros2 import ZRosClient

        with ZRosClient(config=config) as client:
            assert client.session is not None
