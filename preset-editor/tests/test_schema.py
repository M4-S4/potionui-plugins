import pytest
from pydantic import ValidationError

from backend.schema import DraftCreate, PublishRequest


def test_a_copy_request_is_stripped_and_gives_its_target_dir():
    body = DraftCreate(mode="copy", from_id=" fixture-minimal-native ", name="  My copy ", model_dir=" MyModel ", variant_dir=" ")

    assert (body.from_id, body.name, body.model_dir, body.variant_dir) == ("fixture-minimal-native", "My copy", "MyModel", None)
    assert body.target_dir == "MyModel"
    assert body.preset_id is None


def test_a_custom_id_and_a_variant_are_validated():
    body = DraftCreate(mode="copy", from_id="src-id", name="N", preset_id="my_Id-9", model_dir="M", variant_dir="v1")

    assert body.preset_id == "my_Id-9" and body.target_dir == "M/v1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"preset_id": "x"},
        {"preset_id": "has space"},
        {"from_id": "../x"},
        {"model_dir": "../x"},
        {"model_dir": ".hidden"},
        {"variant_dir": "a/b"},
        {"name": ""},
        {"name": "x" * 121},
        {"mode": "other"},
    ],
)
def test_bad_fields_are_refused(overrides):
    body = {"mode": "copy", "from_id": "src-id", "name": "N", "model_dir": "M"}
    body.update(overrides)
    with pytest.raises(ValidationError):
        DraftCreate(**body)


def test_a_blank_request_defaults_to_a_native_image_preset_with_txt2img():
    body = DraftCreate(mode="blank", name="Fresh", model_dir="Fresh")

    assert (body.engine, body.driver, body.modes, body.family, body.resolved_category) == ("native", None, ["txt2img"], None, "image")


def test_a_blank_cloud_request_takes_its_category_from_the_first_mode():
    body = DraftCreate(mode="blank", name="Cloud", model_dir="Cloud", engine="cloud", driver="cloud.openrouter", modes=["txt2video", "txt2img"])

    assert body.resolved_category == "video"
    assert DraftCreate(mode="blank", name="C", model_dir="C", engine="cloud", driver="cloud.x", modes=["txt2img"], category="utility").resolved_category == "utility"


@pytest.mark.parametrize(
    "overrides",
    [
        {"engine": "cloud"},
        {"engine": "cloud", "driver": "cloud.x", "modes": ["img2img"]},
        {"engine": "Native"},
        {"driver": "cloud.x"},
        {"modes": []},
        {"modes": ["txt2img", "txt2img"]},
        {"modes": ["Bad"]},
        {"engine": "comfyui", "family": {"family": "z", "loader_name": "model_loader/z", "generator_name": "generator/z", "model_slots": ["m"]}},
        {"family": {"family": "z", "loader_name": "model_loader/other", "generator_name": "generator/z", "model_slots": ["m"]}},
        {"family": {"family": "z", "loader_name": "model_loader/z", "generator_name": "generator/z", "model_slots": ["m", "m"]}},
        {"family": {"family": "z", "loader_name": "model_loader/z", "generator_name": "generator/z", "model_slots": ["m"], "resolution_default": "wide"}},
    ],
)
def test_bad_blank_requests_are_refused(overrides):
    body = {"mode": "blank", "name": "Fresh", "model_dir": "Fresh"}
    body.update(overrides)
    with pytest.raises(ValidationError):
        DraftCreate(**body)


def test_a_copy_request_needs_from_id():
    with pytest.raises(ValidationError):
        DraftCreate(mode="copy", name="N", model_dir="M")


def test_a_publish_request_defaults_to_the_setting():
    assert PublishRequest().install is None
    assert PublishRequest(install=False).install is False
