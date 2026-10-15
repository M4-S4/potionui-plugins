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
        {"mode": "blank"},
    ],
)
def test_bad_fields_are_refused(overrides):
    body = {"mode": "copy", "from_id": "src-id", "name": "N", "model_dir": "M"}
    body.update(overrides)
    with pytest.raises(ValidationError):
        DraftCreate(**body)


def test_a_publish_request_defaults_to_the_setting():
    assert PublishRequest().install is None
    assert PublishRequest(install=False).install is False
