# saneconfig

[![CI](https://github.com/yourname/saneconfig/actions/workflows/ci.yml/badge.svg)](https://github.com/yourname/saneconfig/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-sphinx-blue)](https://github.com/yourname/saneconfig/tree/main/docs)
[![PyPI](https://img.shields.io/pypi/v/saneconfig.svg)](https://pypi.org/project/saneconfig/)

Dead-simple typed config loader for **dataclasses**:
- defaults
- TOML file(s)
- environment variables

with **great errors** and **provenance** ("where did this value come from?").

Python **3.11+**.

Core package has zero runtime dependencies; optional extras:
- `saneconfig[dotenv]` for `.env` file support.

## Install

```bash
pip install saneconfig
# optional .env support
pip install "saneconfig[dotenv]"
```

## Quick start

```python
from dataclasses import dataclass
from saneconfig import load, REQUIRED


@dataclass
class AppConfig:
    debug: bool = False
    port: int = 8080
    database_url: str = REQUIRED


cfg = load(
    AppConfig,
    env_prefix="APP",
    files=["config.toml", "config.local.toml"],
)

print(cfg.port)
```

## Precedence (highest wins)

1. CLI args (`argv=True` or `argv=[...]`)
2. Environment variables
3. `.env` file values (when `dotenv` is enabled)
4. TOML files (later overrides earlier)
5. Dataclass defaults

## TOML example

```toml
debug = true
port = 9000
database_url = "postgresql://user:pass@localhost:5432/mydb"
```

Nested dataclasses map to TOML tables:

```toml
[db]
host = "localhost"
port = 5432
```

## Env var mapping

With `env_prefix="APP"`:

- `APP_PORT=9000` -> `port`
- `APP_DEBUG=true` -> `debug`
- nested via `__`: `APP_DB__HOST=localhost` -> `db.host`

Booleans accept: `true/false`, `yes/no`, `on/off`, `1/0` (case-insensitive).

Lists in env vars use JSON:

```bash
APP_ALLOWED='["a","b"]'
```


## CLI overrides

Enable CLI parsing by passing `argv=True` (uses `sys.argv[1:]`) or provide a list explicitly:

```python
cfg = load(
    AppConfig,
    env_prefix="APP",
    argv=["--port=9001", "--db.host=db.internal"],
)
```

Supported form: `--key=value` with dotted nesting (`--db.host=x`).

## Provenance / debugging

```python
cfg, report = load(
    AppConfig,
    env_prefix="APP",
    files=["config.toml", "config.local.toml"],
    return_report=True,
)

print(report)
```

Example output:

```text
database_url='postgresql://...' (env:APP_DATABASE_URL)
debug=False (default)
port=9000 (file:config.toml)
```

## Schema docs

You can include richer docs using dataclass metadata:

```python
from dataclasses import dataclass, field

@dataclass
class AppConfig:
    port: int = field(default=8080, metadata={"help": "HTTP listen port"})
```

```python
from saneconfig import dump_schema
print(dump_schema(AppConfig, env_prefix="APP"))
```

`dump_schema(...)` includes a `Help` column using `field(metadata={"help": ...})`.

## Errors that help

If a value cannot be converted:

```text
ConfigError: port expected int but got "eighty"
  source: env:APP_PORT
  hint: Use a valid int value.
```

If required values are missing:

```text
ConfigError: missing required configuration values:
  - database_url
```

## Supported types (v0.1)

- `str`, `int`, `float`, `bool`
- `Optional[T]`
- `list[T]` (TOML arrays or JSON arrays in env)
- `Literal[...]`
- nested dataclasses
- `pathlib.Path`
- `dict[str, T]` (TOML table or JSON object in env)

## Non-goals (by design)

- profiles/composition systems
- interpolation DSLs
- frameworks and global state

MIT Licensed.

---

## A tiny example you can run

```python
from dataclasses import dataclass
from typing import Literal, Optional

from saneconfig import REQUIRED, load


@dataclass
class DB:
    host: str = "localhost"
    port: int = 5432


@dataclass
class App:
    mode: Literal["dev", "prod"] = "dev"
    debug: bool = False
    port: int = 8080
    api_key: str = REQUIRED
    db: DB = DB()
    notes: Optional[str] = None


cfg, report = load(App, env_prefix="APP", files=["config.toml"], return_report=True)
print(cfg)
print(report)
```
