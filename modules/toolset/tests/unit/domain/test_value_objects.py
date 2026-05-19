import pytest

from toolset.domain.value_objects import ConnectorResponse, ExecutionTimeout, ToolInput, ToolOutput


class TestConnectorResponse:

    def test_is_success_2xx(self):
        r = ConnectorResponse(status_code=200, body=b"ok")
        assert r.is_success is True

    def test_is_success_false_4xx(self):
        r = ConnectorResponse(status_code=404, body=b"not found")
        assert r.is_success is False

    def test_default_headers_empty(self):
        r = ConnectorResponse(status_code=200, body=b"")
        assert r.headers == {}

    def test_frozen(self):
        r = ConnectorResponse(status_code=200, body=b"")
        with pytest.raises((AttributeError, TypeError)):
            r.status_code = 999


class TestExecutionTimeout:

    def test_default_and_max_are_class_vars(self):
        assert ExecutionTimeout.DEFAULT == 30
        assert ExecutionTimeout.MAX == 300

    def test_valid_seconds(self):
        t = ExecutionTimeout(seconds=60)
        assert t.seconds == 60

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            ExecutionTimeout(seconds=0)

    def test_exceeds_max_raises(self):
        with pytest.raises(ValueError):
            ExecutionTimeout(seconds=301)

    def test_default_not_in_constructor_signature(self):
        # ClassVar이므로 생성자에 DEFAULT/MAX 인자로 넘기면 TypeError
        with pytest.raises(TypeError):
            ExecutionTimeout(seconds=30, DEFAULT=10)
