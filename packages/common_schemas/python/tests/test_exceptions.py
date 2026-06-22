import pytest

from common_schemas.exceptions import (
    AuthorizationError,
    DomainError,
    ExecutionError,
    NotFoundError,
    ValidationError,
)


class TestDomainError:
    def test_message(self):
        err = DomainError("something failed")
        assert str(err) == "something failed"

    def test_code(self):
        err = DomainError("fail", code="E_TEST")
        assert err.code == "E_TEST"

    def test_default_code_is_none(self):
        err = DomainError("fail")
        assert err.code is None


class TestSubclasses:
    @pytest.mark.parametrize(
        "cls",
        [ValidationError, AuthorizationError, ExecutionError, NotFoundError],
    )
    def test_inherits_domain_error(self, cls):
        err = cls("msg", code="E_X")
        assert isinstance(err, DomainError)
        assert err.code == "E_X"
        assert str(err) == "msg"
