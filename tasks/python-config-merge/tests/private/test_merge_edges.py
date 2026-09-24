from configmerge import merge_config


def test_inputs_are_not_mutated() -> None:
    base = {"service": {"port": 80}}
    override = {"service": {"host": "api"}}
    merge_config(base, override)
    assert base == {"service": {"port": 80}}
    assert override == {"service": {"host": "api"}}


def test_replacement_list_is_deep_copied() -> None:
    override = {"items": [{"name": "first"}]}
    result = merge_config({}, override)
    result["items"][0]["name"] = "changed"
    assert override == {"items": [{"name": "first"}]}


def test_new_nested_mapping_is_deep_copied() -> None:
    override = {"feature": {"flags": ["fast"]}}
    result = merge_config({}, override)
    result["feature"]["flags"].append("safe")
    assert override == {"feature": {"flags": ["fast"]}}


def test_none_for_missing_key_is_a_noop() -> None:
    assert merge_config({"enabled": True}, {"missing": None}) == {"enabled": True}
