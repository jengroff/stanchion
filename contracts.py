from typing import Literal
from pydantic import BaseModel, ValidationError


class NodeContract(BaseModel):
    node_id: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]


class ContractViolation(Exception):
    node_id: str
    direction: Literal["input", "output"]
    raw: dict
    errors: list

    def __init__(self, node_id: str, direction: Literal["input", "output"], raw: dict, errors: list):
        self.node_id = node_id
        self.direction = direction
        self.raw = raw
        self.errors = errors
        super().__init__(f"Contract violation for {node_id} ({direction})")


class BoundaryValidator:
    def __call__(self, contract: NodeContract, direction: Literal["input", "output"], raw: dict) -> BaseModel:
        schema = contract.input_schema if direction == "input" else contract.output_schema
        try:
            return schema.model_validate(raw)
        except ValidationError as exc:
            raise ContractViolation(contract.node_id, direction, raw, exc.errors()) from exc


class ContractRegistry:
    def __init__(self) -> None:
        self._contracts: dict[str, NodeContract] = {}
        self._validator = BoundaryValidator()

    def register(self, contract: NodeContract) -> None:
        self._contracts[contract.node_id] = contract

    def get(self, node_id: str) -> NodeContract:
        return self._contracts[node_id]

    def validate_input(self, node_id: str, raw: dict) -> BaseModel:
        contract = self.get(node_id)
        return self._validator(contract, "input", raw)

    def validate_output(self, node_id: str, raw: dict) -> BaseModel:
        contract = self.get(node_id)
        return self._validator(contract, "output", raw)
