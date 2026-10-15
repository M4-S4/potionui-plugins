import re
from typing import Annotated, Any, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

from . import files, paths
from .scaffold import CATEGORIES, CLOUD_MODES, FamilyPipes

MAX_NAME_LENGTH = 120
MAX_MODES = 12
ENGINE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
DRIVER_RE = re.compile(r"^[a-z][a-z0-9_]*\.[A-Za-z0-9_.-]{1,64}$")
FAMILY_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
SLOT_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SAMPLER_RE = re.compile(r"^[A-Za-z0-9_+.-]{1,64}$")
RESOLUTION_RE = re.compile(r"^\d{2,5}x\d{2,5}$")


def _stripped(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _blank_is_none(value: Any) -> Any:
    value = _stripped(value)
    return value or None


Stripped = Annotated[str, BeforeValidator(_stripped)]
OptionalStripped = Annotated[Optional[str], BeforeValidator(_blank_is_none)]


class FamilySpec(BaseModel):
    family: Stripped = Field(min_length=1, max_length=64)
    loader_name: Stripped = Field(min_length=1, max_length=128)
    generator_name: Stripped = Field(min_length=1, max_length=128)
    model_slots: List[Stripped] = Field(min_length=1, max_length=8)
    has_loras: bool = False
    has_text_encoder_output: bool = False
    steps_default: int = Field(20, ge=1, le=500)
    guidance_key: Literal["guidance", "cfg"] = "guidance"
    guidance_default: float = Field(4.0, ge=0, le=100)
    sampler_default: Stripped = Field("euler", max_length=64)
    sampler_choices: List[Stripped] = Field(default_factory=lambda: ["euler"], min_length=1, max_length=64)
    resolution_default: Stripped = Field("1024x1024", max_length=16)

    @model_validator(mode="after")
    def _shape(self) -> "FamilySpec":
        if not FAMILY_RE.match(self.family):
            raise ValueError("family is lowercase letters, digits and '_'")
        if self.loader_name != f"model_loader/{self.family}" or not self.generator_name.startswith("generator/"):
            raise ValueError("the loader is model_loader/<family> and the generator a generator/… pipe")
        if not re.match(r"^generator/[A-Za-z0-9_./-]+$", self.generator_name):
            raise ValueError("generator name is not a pipe name")
        if any(not SLOT_RE.match(slot) for slot in self.model_slots) or len(set(self.model_slots)) != len(self.model_slots):
            raise ValueError("model slots are distinct lowercase names")
        if not SAMPLER_RE.match(self.sampler_default) or any(not SAMPLER_RE.match(choice) for choice in self.sampler_choices):
            raise ValueError("sampler names are letters, digits, '_', '+', '.' or '-'")
        if not RESOLUTION_RE.match(self.resolution_default):
            raise ValueError("the default resolution is <width>x<height>")
        return self

    def to_pipes(self) -> FamilyPipes:
        return FamilyPipes(
            family=self.family,
            loader_name=self.loader_name,
            generator_name=self.generator_name,
            model_slots=tuple(self.model_slots),
            has_loras=self.has_loras,
            has_text_encoder_output=self.has_text_encoder_output,
            steps_default=self.steps_default,
            guidance_key=self.guidance_key,
            guidance_default=self.guidance_default,
            sampler_default=self.sampler_default,
            sampler_choices=tuple(self.sampler_choices),
            resolution_default=self.resolution_default,
        )


class DraftCreate(BaseModel):
    mode: Literal["copy", "blank"]
    from_id: OptionalStripped = Field(None, max_length=64)
    name: Stripped = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    preset_id: OptionalStripped = None
    model_dir: Stripped = Field(min_length=1, max_length=64)
    variant_dir: OptionalStripped = Field(None, max_length=64)
    category: Optional[Literal["image", "video", "audio", "3d", "utility"]] = None
    engine: Stripped = Field("native", max_length=32)
    driver: OptionalStripped = Field(None, max_length=80)
    modes: List[Stripped] = Field(default_factory=lambda: ["txt2img"], min_length=1, max_length=MAX_MODES)
    family: Optional[FamilySpec] = None

    @field_validator("from_id", "preset_id")
    @classmethod
    def _preset_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            paths.check_preset_id(value)
        return value

    @field_validator("modes")
    @classmethod
    def _modes(cls, value: List[str]) -> List[str]:
        for mode in value:
            try:
                files.check_mode_name(mode)
            except files.FilesError as failure:
                raise ValueError(failure.message) from failure
        if len(set(value)) != len(value):
            raise ValueError("a mode is listed once")
        return value

    @model_validator(mode="after")
    def _rules(self) -> "DraftCreate":
        paths.target_dir(self.model_dir, self.variant_dir)
        if self.mode == "copy":
            if not self.from_id:
                raise ValueError("a copy needs from_id")
            return self
        if not ENGINE_RE.match(self.engine):
            raise ValueError("engine is lowercase letters, digits and '_'")
        if self.driver is not None:
            if not DRIVER_RE.match(self.driver) or not self.driver.startswith(f"{self.engine}."):
                raise ValueError("driver looks like '<engine>.<name>' and starts with the preset's engine")
        if self.engine == "cloud":
            if self.driver is None:
                raise ValueError("engine cloud needs a driver such as cloud.openrouter")
            unknown = [mode for mode in self.modes if mode not in CLOUD_MODES]
            if unknown:
                raise ValueError(f"unknown cloud mode(s) {unknown}; choose from {sorted(CLOUD_MODES)}")
            if self.family is not None:
                raise ValueError("a family only applies to the native chain")
        if self.family is not None and self.engine == "comfyui":
            raise ValueError("a family only applies to the native chain")
        return self

    @property
    def target_dir(self) -> str:
        return paths.target_dir(self.model_dir, self.variant_dir)

    @property
    def resolved_category(self) -> str:
        if self.category:
            return self.category
        if self.engine == "cloud":
            return CLOUD_MODES[self.modes[0]].category
        return "image"


class ModeCreate(BaseModel):
    mode: Stripped = Field(min_length=1, max_length=40)
    family: Optional[FamilySpec] = None

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        try:
            return files.check_mode_name(value)
        except files.FilesError as failure:
            raise ValueError(failure.message) from failure


class FileWrite(BaseModel):
    content: str = Field(max_length=files.MAX_TEXT_BYTES)


class PublishRequest(BaseModel):
    install: Optional[bool] = None
