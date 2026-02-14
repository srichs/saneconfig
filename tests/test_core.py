from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Union

import pytest

from saneconfig import REQUIRED, dump_schema, load
from saneconfig._errors import ConfigError, MissingRequiredError


@dataclass
class DBConfig:
    host: str = "localhost"
    port: int = 5432


@dataclass
class AppConfig:
    debug: bool = False
    port: int = 8000
    api_key: str = REQUIRED
    db: DBConfig = field(default_factory=DBConfig)


@dataclass
class TypesConfig:
    mode: Literal["dev", "prod"] = "dev"
    ratio: float = 1.5
    enabled: bool = True
    names: list[str] = field(default_factory=lambda: ["a"])
    tags: dict[str, int] = field(default_factory=dict)
    out_dir: Path = Path(".")
    note: Optional[str] = None


def test_load_uses_defaults_and_required_validation() -> None:
    with pytest.raises(MissingRequiredError) as exc:
        load(AppConfig)

    assert exc.value.missing_paths == ["api_key"]


def test_precedence_env_over_file_over_defaults(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
port = 9000
api_key = "from-file"
[db]
host = "db-from-file"
""".strip()
    )

    cfg = load(
        AppConfig,
        files=[cfg_file],
        env_prefix="APP",
        env={
            "APP_PORT": "9100",
            "APP_DB__PORT": "7000",
            "APP_API_KEY": "from-env",
        },
    )

    assert cfg.port == 9100
    assert cfg.api_key == "from-env"
    assert cfg.db.host == "db-from-file"
    assert cfg.db.port == 7000


def test_nonexistent_files_are_ignored() -> None:
    cfg = load(
        AppConfig,
        files=["this-file-does-not-exist.toml"],
        env_prefix="APP",
        env={"APP_API_KEY": "x"},
    )

    assert cfg.port == 8000


def test_return_report_contains_sources_and_values(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('port = 7777\napi_key = "from-file"\n')

    cfg, report = load(
        AppConfig,
        files=[cfg_file],
        env_prefix="APP",
        env={"APP_PORT": "8888", "APP_API_KEY": "from-env"},
        return_report=True,
    )

    assert cfg.port == 8888
    assert report.source_of("port") == "env:APP_PORT"
    assert report.value_of("api_key") == "from-env"
    assert "port=8888 (env:APP_PORT)" in str(report)


def test_dump_schema_for_nested_types() -> None:
    schema = dump_schema(AppConfig, env_prefix="APP")

    assert "`port`" in schema
    assert "`db.host`" in schema
    assert "`APP_DB__HOST`" in schema
    assert "`REQUIRED`" in schema


def test_dump_schema_includes_help_metadata() -> None:
    @dataclass
    class Cfg:
        port: int = field(default=8080, metadata={"help": "HTTP listen port"})

    schema = dump_schema(Cfg, env_prefix="APP")
    assert "Help" in schema
    assert "HTTP listen port" in schema


def test_invalid_dataclass_type_for_load_and_schema() -> None:
    with pytest.raises(TypeError):
        load(dict)

    with pytest.raises(TypeError):
        dump_schema(dict)


def test_bool_parsing_from_env_variants() -> None:
    @dataclass
    class Cfg:
        enabled: bool = False
        api_key: str = REQUIRED

    truthy = ["true", "1", "yes", "y", "on"]
    falsy = ["false", "0", "no", "n", "off"]

    for val in truthy:
        cfg = load(Cfg, env_prefix="APP", env={"APP_ENABLED": val, "APP_API_KEY": "k"})
        assert cfg.enabled is True

    for val in falsy:
        cfg = load(Cfg, env_prefix="APP", env={"APP_ENABLED": val, "APP_API_KEY": "k"})
        assert cfg.enabled is False


def test_invalid_bool_raises_config_error() -> None:
    @dataclass
    class Cfg:
        enabled: bool = False
        api_key: str = REQUIRED

    with pytest.raises(ConfigError) as exc:
        load(Cfg, env_prefix="APP", env={"APP_ENABLED": "maybe", "APP_API_KEY": "k"})

    assert exc.value.path == "enabled"
    assert exc.value.expected == "bool"


def test_literal_validation() -> None:
    cfg = load(TypesConfig, env_prefix="APP", env={"APP_MODE": "prod"})
    assert cfg.mode == "prod"

    with pytest.raises(ConfigError):
        load(TypesConfig, env_prefix="APP", env={"APP_MODE": "staging"})


def test_list_and_dict_from_env_json() -> None:
    cfg = load(
        TypesConfig,
        env_prefix="APP",
        env={"APP_NAMES": '["x", "y"]', "APP_TAGS": '{"a": 1, "b": 2}'},
    )

    assert cfg.names == ["x", "y"]
    assert cfg.tags == {"a": 1, "b": 2}


def test_invalid_list_json_raises_config_error() -> None:
    with pytest.raises(ConfigError) as exc:
        load(TypesConfig, env_prefix="APP", env={"APP_NAMES": "not-json"})

    assert exc.value.path == "names"


def test_invalid_dict_json_raises_config_error() -> None:
    with pytest.raises(ConfigError) as exc:
        load(TypesConfig, env_prefix="APP", env={"APP_TAGS": "[1,2]"})

    assert exc.value.path == "tags"


def test_optional_empty_string_becomes_none() -> None:
    cfg = load(TypesConfig, env_prefix="APP", env={"APP_NOTE": ""})
    assert cfg.note is None


def test_path_support_from_env() -> None:
    cfg = load(TypesConfig, env_prefix="APP", env={"APP_OUT_DIR": "/tmp/data"})
    assert cfg.out_dir == Path("/tmp/data")


def test_nested_dataclass_requires_table_or_env_nesting(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text('api_key = "x"\ndb = "not-a-table"\n')

    with pytest.raises(ConfigError) as exc:
        load(AppConfig, files=[bad])

    assert exc.value.path == "db"
    assert exc.value.expected == "table/object"


def test_union_coercion_works() -> None:
    @dataclass
    class Cfg:
        value: Union[int, str] = "x"

    cfg_int = load(Cfg, env_prefix="APP", env={"APP_VALUE": "42"})
    cfg_str = load(Cfg, env_prefix="APP", env={"APP_VALUE": "abc"})

    assert cfg_int.value == 42
    assert cfg_str.value == "abc"


def test_pep604_union_coercion_works() -> None:
    @dataclass
    class Cfg:
        value: int | str = "x"

    cfg_int = load(Cfg, env_prefix="APP", env={"APP_VALUE": "42"})
    cfg_str = load(Cfg, env_prefix="APP", env={"APP_VALUE": "abc"})

    assert cfg_int.value == 42
    assert cfg_str.value == "abc"


def test_dash_and_case_insensitive_env_keys() -> None:
    @dataclass
    class Cfg:
        service_name: str = "default"

    cfg = load(Cfg, env_prefix="APP", env={"app_SERVICE-NAME": "my-service"})
    assert cfg.service_name == "my-service"


def test_argv_overrides_env_and_files(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('port = 7000\napi_key = "file"\n[db]\nhost = "from-file"\n')

    cfg = load(
        AppConfig,
        files=[cfg_file],
        env_prefix="APP",
        env={"APP_PORT": "8000", "APP_API_KEY": "from-env", "APP_DB__HOST": "from-env"},
        argv=["--port=9001", "--db.host=from-argv"],
    )

    assert cfg.port == 9001
    assert cfg.db.host == "from-argv"
    assert cfg.api_key == "from-env"


def test_argv_true_reads_sys_argv_and_ignores_invalid_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @dataclass
    class Cfg:
        value: int = 1

    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--value=10",
            "--value",
            "--.bad=11",
            "not-an-option",
        ],
    )

    cfg = load(Cfg, argv=True)

    assert cfg.value == 10


def test_dotenv_values_are_loaded_when_enabled(tmp_path: Path) -> None:
    pytest.importorskip("dotenv")

    env_file = tmp_path / ".env"
    env_file.write_text("APP_PORT=9100\nAPP_API_KEY=from-dotenv\n")

    cfg = load(AppConfig, env_prefix="APP", dotenv=env_file)

    assert cfg.port == 9100
    assert cfg.api_key == "from-dotenv"


def test_env_overrides_dotenv_when_both_present(tmp_path: Path) -> None:
    pytest.importorskip("dotenv")

    env_file = tmp_path / ".env"
    env_file.write_text("APP_API_KEY=from-dotenv\n")

    cfg, report = load(
        AppConfig,
        env_prefix="APP",
        dotenv=env_file,
        env={"APP_API_KEY": "from-env"},
        return_report=True,
    )

    assert cfg.api_key == "from-env"
    assert report.source_of("api_key") == "env:APP_API_KEY"


def test_dotenv_without_optional_dependency_raises_helpful_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    original_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "dotenv":
            raise ImportError("blocked in test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    env_file = tmp_path / ".env"
    env_file.write_text("APP_API_KEY=from-dotenv\n")

    with pytest.raises(ImportError, match=r"saneconfig\[dotenv\]"):
        load(AppConfig, env_prefix="APP", dotenv=env_file)


def test_missing_required_error_string_format() -> None:
    err = MissingRequiredError(["a", "b.c"])
    text = str(err)
    assert "missing required" in text
    assert "- a" in text
    assert "- b.c" in text


def test_config_error_string_includes_source_and_hint() -> None:
    err = ConfigError(path="port", expected="int", value="x", source="env:APP_PORT", hint="Use int")
    text = str(err)
    assert "port expected int" in text
    assert "source: env:APP_PORT" in text
    assert "hint: Use int" in text


def test_bool_value_is_not_accepted_for_int_field() -> None:
    @dataclass
    class Cfg:
        count: int = 0

    with pytest.raises(ConfigError) as exc:
        load(Cfg, files=[], env_prefix="APP", env={"APP_COUNT": "true"})

    assert exc.value.path == "count"
    assert exc.value.expected == "int"


def test_invalid_path_value_raises_config_error(tmp_path: Path) -> None:
    @dataclass
    class Cfg:
        output: Path = Path(".")

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("output = 1\n")

    with pytest.raises(ConfigError) as exc:
        load(Cfg, files=[cfg_file])

    assert exc.value.path == "output"
    assert exc.value.expected == "path"


def test_pep604_optional_type_is_detected() -> None:
    @dataclass
    class Cfg:
        note: str | None = None

    cfg = load(Cfg, env_prefix="APP", env={"APP_NOTE": ""})
    assert cfg.note is None


def test_unsupported_target_type_raises_config_error() -> None:
    @dataclass
    class Cfg:
        payload: bytes = b"x"

    with pytest.raises(ConfigError) as exc:
        load(Cfg, env_prefix="APP", env={"APP_PAYLOAD": "abc"})

    assert exc.value.path == "payload"
    assert "Unsupported type" in (exc.value.hint or "")


def test_missing_optional_field_without_default_becomes_none() -> None:
    @dataclass
    class Cfg:
        note: str | None

    cfg = load(Cfg)
    assert cfg.note is None


def test_missing_non_optional_field_without_default_is_none() -> None:
    @dataclass
    class Cfg:
        count: int

    cfg = load(Cfg)
    assert cfg.count is None


def test_invalid_dict_json_string_raises_config_error() -> None:
    with pytest.raises(ConfigError) as exc:
        load(TypesConfig, env_prefix="APP", env={"APP_TAGS": "not-json"})

    assert exc.value.path == "tags"
    assert "JSON object" in exc.value.expected


def test_env_prefix_none_does_not_apply_env_values() -> None:
    @dataclass
    class Cfg:
        port: int = 1234

    cfg = load(Cfg, env={"APP_PORT": "9999"})
    assert cfg.port == 1234


def test_dotenv_true_uses_default_dotenv_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    calls: list[object] = []
    original_import = builtins.__import__

    class FakeDotenvModule:
        @staticmethod
        def dotenv_values(path: object) -> dict[str, str]:
            calls.append(path)
            return {"APP_API_KEY": "from-dotenv"}

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "dotenv":
            return FakeDotenvModule
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    cfg = load(AppConfig, env_prefix="APP", dotenv=True)

    assert cfg.api_key == "from-dotenv"
    assert calls == [".env"]
