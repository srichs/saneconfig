from dataclasses import dataclass, field

import pytest

from saneconfig import load
from saneconfig._errors import MissingRequiredError


def test_nested_dataclass_custom_default_instance_preserves_provenance() -> None:
    @dataclass
    class DB:
        host: str = "localhost"
        port: int = 5432

    @dataclass
    class App:
        db: DB = field(default_factory=lambda: DB(host="prod-db"))

    cfg, report = load(App, return_report=True)

    assert cfg.db.host == "prod-db"
    assert report.sources_by_path.get("db.host") == "default"


def test_missing_non_optional_field_without_default_fails_fast() -> None:
    @dataclass
    class Cfg:
        port: int

    with pytest.raises(MissingRequiredError) as exc:
        load(Cfg)

    assert exc.value.missing_paths == ["port"]
