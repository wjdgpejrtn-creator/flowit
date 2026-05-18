from __future__ import annotations

from fastapi import Depends

from nodes_graph.application.use_cases.validate_graph_use_case import ValidateGraphUseCase
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository
from nodes_graph.domain.services.graph_validator import GraphValidator

from app.dependencies.repositories import get_node_definition_repository


def get_graph_validator(
    node_def_repo: NodeDefinitionRepository = Depends(get_node_definition_repository),
) -> GraphValidator:
    return GraphValidator(node_def_repo=node_def_repo)


def get_validate_graph_use_case(
    validator: GraphValidator = Depends(get_graph_validator),
) -> ValidateGraphUseCase:
    return ValidateGraphUseCase(validator=validator)
