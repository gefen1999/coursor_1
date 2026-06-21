from abc import ABC
from dataclasses import dataclass


@dataclass
class ValidationResult:
    name: str
    passed: bool
    message: str | None = None


def validation(fn):
    fn._validation = True
    return fn


class BaseValidator(ABC):
    _validations: list[str]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._validations = [
            name
            for name, attr in cls.__dict__.items()
            if callable(attr) and getattr(attr, "_validation", False)
        ]

    def run(self, data: dict) -> list[ValidationResult]:
        results = []
        for name in self._validations:
            method = getattr(self, name)
            results.append(method(data))
        return results
