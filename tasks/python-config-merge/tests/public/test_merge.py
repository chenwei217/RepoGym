from configmerge import merge_config


def test_scalar_override() -> None:
    assert merge_config({"port": 80}, {"port": 443}) == {"port": 443}


def test_nested_mappings_merge() -> None:
    base = {"http": {"host": "localhost", "port": 80}}
    override = {"http": {"port": 8080}}
    assert merge_config(base, override) == {"http": {"host": "localhost", "port": 8080}}


def test_lists_are_replaced() -> None:
    assert merge_config({"plugins": ["a"]}, {"plugins": ["b"]}) == {"plugins": ["b"]}


def test_none_deletes_a_key() -> None:
    assert merge_config({"host": "localhost", "debug": True}, {"debug": None}) == {
        "host": "localhost"
    }
