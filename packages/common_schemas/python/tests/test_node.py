from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas.node import NodeContext


class TestNodeContext:
    def test_create_with_token(self):
        ctx = NodeContext(
            execution_id=uuid4(),
            user_id=uuid4(),
            connection_token="resolved_oauth_token",
        )
        assert ctx.connection_token == "resolved_oauth_token"

    def test_token_defaults_to_none(self):
        ctx = NodeContext(execution_id=uuid4(), user_id=uuid4())
        assert ctx.connection_token is None

    def test_wipe(self):
        ctx = NodeContext(
            execution_id=uuid4(),
            user_id=uuid4(),
            connection_token="sensitive_token",
        )
        ctx.wipe()
        assert ctx.connection_token is None

    def test_mutable(self):
        ctx = NodeContext(execution_id=uuid4(), user_id=uuid4())
        ctx.connection_token = "late_bound"
        assert ctx.connection_token == "late_bound"

    def test_execution_id_required(self):
        with pytest.raises(ValidationError):
            NodeContext(user_id=uuid4())

    def test_user_id_required(self):
        with pytest.raises(ValidationError):
            NodeContext(execution_id=uuid4())
