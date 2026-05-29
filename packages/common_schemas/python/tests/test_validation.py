import pytest
from pydantic import ValidationError as PydanticValidationError

from common_schemas.enums import ErrorCode
from common_schemas.validation import ValidationErrorItem, ValidationErrorResponse


class TestValidationErrorItem:
    def test_create(self):
        item = ValidationErrorItem(
            code=ErrorCode.E_CYCLE_DETECTED,
            message="Cycle found between nodes A and B",
            node_ids=["node_a", "node_b"],
            validator="SchemaValidation",
        )
        assert item.edge_id is None
        assert item.hint is None

    def test_invalid_validator(self):
        with pytest.raises(PydanticValidationError):
            ValidationErrorItem(
                code=ErrorCode.E_ISOLATED_NODE,
                message="Node is isolated",
                node_ids=["node_x"],
                validator="InvalidValidator",
            )


class TestValidationErrorResponse:
    def test_passed(self):
        resp = ValidationErrorResponse(validation_status="passed", errors=[])
        assert resp.validation_status == "passed"

    def test_failed_with_errors(self):
        item = ValidationErrorItem(
            code=ErrorCode.E_DUPLICATE_ID,
            message="Duplicate ID",
            node_ids=["n1", "n1"],
            validator="RuntimeValidation",
            hint="Rename one of the nodes",
        )
        resp = ValidationErrorResponse(validation_status="failed", errors=[item])
        assert len(resp.errors) == 1
        assert resp.errors[0].hint == "Rename one of the nodes"
