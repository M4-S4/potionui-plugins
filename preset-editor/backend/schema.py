from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

from . import paths

MAX_NAME_LENGTH = 120


def _stripped(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _blank_is_none(value: Any) -> Any:
    value = _stripped(value)
    return value or None


Stripped = Annotated[str, BeforeValidator(_stripped)]
OptionalStripped = Annotated[Optional[str], BeforeValidator(_blank_is_none)]


class DraftCreate(BaseModel):
    mode: Literal["copy"]
    from_id: Stripped = Field(min_length=3, max_length=64)
    name: Stripped = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    preset_id: OptionalStripped = None
    model_dir: Stripped = Field(min_length=1, max_length=64)
    variant_dir: OptionalStripped = Field(None, max_length=64)

    @field_validator("from_id", "preset_id")
    @classmethod
    def _preset_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            paths.check_preset_id(value)
        return value

    @model_validator(mode="after")
    def _target(self) -> "DraftCreate":
        paths.target_dir(self.model_dir, self.variant_dir)
        return self

    @property
    def target_dir(self) -> str:
        return paths.target_dir(self.model_dir, self.variant_dir)


class PublishRequest(BaseModel):
    install: Optional[bool] = None
