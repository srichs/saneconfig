from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, cast, get_args, get_origin

from ._errors import ConfigError, MissingRequiredError
from ._report import LoadReport


class _RequiredSentinel:
    def __repr__(self) -> str:
        return "REQUIRED"


REQUIRED = _RequiredSentinel()


def load(
    config_cls: type[Any],
    *,
    env_prefix: str | None = None,
    files: list[str | os.PathLike[str]] | None = None,
    argv: bool | list[str] = False,
    dotenv: bool | str | os.PathLike[str] = False,
    env: dict[str, str] | None = None,
    return_report: bool = False,
) -> Any | tuple[Any, LoadReport]:
    """
    Load a dataclass config from defaults + TOML file(s) + environment variables.

    Precedence (highest wins):
      1) CLI args (if argv enabled)
      2) env vars
      3) .env file (if dotenv enabled)
      4) TOML files (later files override earlier)
      5) dataclass defaults

    Env mapping:
      - prefix: APP_PORT -> field 'port'
      - nesting via '__': APP_DB__HOST -> db.host
    """
    if not is_dataclass(config_cls):
        raise TypeError("load() expects a dataclass type")

    env_map = dict(env) if env is not None else dict(os.environ)
    dotenv_map = _read_dotenv(dotenv)
    argv_data, argv_sources = _read_argv(argv)

    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}

    # 1) defaults (lowest)
    _apply_defaults(config_cls, merged, sources, prefix="")

    # 2) files (middle)
    if files:
        for fp in files:
            p = Path(fp)
            if not p.exists():
                continue
            data = _read_toml(p)
            _deep_merge_with_sources(
                merged,
                data,
                sources,
                source_label=f"file:{p.as_posix()}",
            )

    # 3) env vars (highest)
    if env_prefix and dotenv_map:
        dotenv_data = _read_env(dotenv_map, env_prefix)
        _deep_merge_with_sources(
            merged,
            dotenv_data,
            sources,
            source_label="dotenv",
            per_key_sources=_env_sources(dotenv_map, env_prefix, source_prefix="dotenv"),
        )

    if env_prefix:
        env_data = _read_env(env_map, env_prefix)
        _deep_merge_with_sources(
            merged,
            env_data,
            sources,
            source_label="env",  # per-key updated below
            per_key_sources=_env_sources(env_map, env_prefix, source_prefix="env"),
        )

    if argv_data:
        _deep_merge_with_sources(
            merged,
            argv_data,
            sources,
            source_label="argv",
            per_key_sources=argv_sources,
        )

    # Build & coerce into dataclass
    values_by_path: dict[str, Any] = {}
    obj = _build_dataclass(
        config_cls,
        merged,
        sources,
        prefix_path="",
        values_by_path=values_by_path,
    )

    missing = _find_missing_required(config_cls, obj, prefix="")
    if missing:
        raise MissingRequiredError(missing)

    report = LoadReport(sources_by_path=sources, values_by_path=values_by_path)
    if return_report:
        return obj, report
    return obj


def dump_schema(config_cls: type[Any], *, env_prefix: str | None = None) -> str:
    """
    Produce a simple markdown schema for docs/README.
    """
    if not is_dataclass(config_cls):
        raise TypeError("dump_schema() expects a dataclass type")

    lines = ["| Key | Type | Default | Env | Help |", "|---|---|---|---|---|"]
    for path, f, ftype, default in _walk_fields(config_cls, prefix=""):
        env_name = ""
        if env_prefix:
            env_name = _path_to_env(env_prefix, path)
        help_text = str(f.metadata.get("help", "")).replace("|", "\\|")
        lines.append(
            f"| `{path}` | `{_type_str(ftype)}` | `{default}` | `{env_name}` | {help_text} |"
        )
    return "\n".join(lines)


# ---------------------------
# Internals
# ---------------------------


def _read_toml(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        return {}
    return data


def _apply_defaults(
    config_cls: type[Any],
    out: dict[str, Any],
    sources: dict[str, str],
    *,
    prefix: str,
) -> None:
    # defaults become initial merged dict, with "default" provenance
    for f in fields(config_cls):
        key = f.name
        path = f"{prefix}.{key}" if prefix else key
        if is_dataclass(f.type):
            out.setdefault(key, {})
            sources.setdefault(path, "default")
            _apply_defaults(
                cast(type[Any], f.type),
                out[key],
                _child_sources(sources, key),
                prefix=path,
            )
            continue

        default_val = None
        if f.default is not MISSING:
            default_val = f.default
            out[key] = default_val
            sources[path] = "default"
        elif f.default_factory is not MISSING:  # type: ignore[comparison-overlap]
            default_val = f.default_factory()  # type: ignore[misc]
            out[key] = default_val
            sources[path] = "default"
        elif default_val is None:
            # leave absent (may be required)
            pass


def _child_sources(sources: dict[str, str], key: str) -> dict[str, str]:
    # store nested sources using dotted paths in the same dict; helper returns view-like,
    # but we'll just keep dotted keys globally instead.
    return sources


def _deep_merge_with_sources(
    base: dict[str, Any],
    incoming: dict[str, Any],
    sources: dict[str, str],
    *,
    source_label: str,
    per_key_sources: dict[str, str] | None = None,
    prefix: str = "",
) -> None:
    """
    Deep merge dicts. Update sources per leaf path.
    """
    for k, v in incoming.items():
        path = f"{prefix}.{k}" if prefix else k

        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge_with_sources(
                base[k],
                v,
                sources,
                source_label=source_label,
                per_key_sources=per_key_sources,
                prefix=path,
            )
        else:
            base[k] = v
            if per_key_sources and path in per_key_sources:
                sources[path] = per_key_sources[path]
            else:
                sources[path] = source_label


def _env_sources(env_map: dict[str, str], env_prefix: str, *, source_prefix: str) -> dict[str, str]:
    """
    Map dotted paths -> exact env var name that provided it.
    """
    out: dict[str, str] = {}
    p = env_prefix.upper() + "_"
    for k in env_map.keys():
        if not k.upper().startswith(p):
            continue
        stripped = k[len(p) :]
        path = stripped.lower().replace("-", "_").replace("__", ".")
        out[path] = f"{source_prefix}:{k}"
    return out


def _read_dotenv(dotenv: bool | str | os.PathLike[str]) -> dict[str, str]:
    if not dotenv:
        return {}

    try:
        from dotenv import dotenv_values
    except ImportError as exc:
        raise ImportError(
            "dotenv support requires optional dependency. Install with: pip install saneconfig[dotenv]"
        ) from exc

    dotenv_path = ".env" if dotenv is True else dotenv
    loaded = dotenv_values(dotenv_path)
    return {k: v for k, v in loaded.items() if isinstance(v, str)}


def _read_argv(argv: bool | list[str]) -> tuple[dict[str, Any], dict[str, str]]:
    raw_args: list[str] = []
    if argv is True:
        raw_args = sys.argv[1:]
    elif isinstance(argv, list):
        raw_args = argv

    parsed: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for token in raw_args:
        if not token.startswith("--"):
            continue
        if "=" not in token:
            continue

        key, value = token[2:].split("=", 1)
        key_path = key.replace("-", "_").strip()
        if not key_path:
            continue

        parts = [p for p in key_path.split(".") if p]
        if not parts:
            continue

        cur = parsed
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value
        sources[".".join(parts)] = f"argv:--{key}"

    return parsed, sources


def _read_env(env_map: dict[str, str], env_prefix: str) -> dict[str, Any]:
    """
    Convert env vars with prefix into nested dict via '__' separators.
    """
    result: dict[str, Any] = {}
    prefix = env_prefix.upper() + "_"

    for raw_key, raw_val in env_map.items():
        if not raw_key.upper().startswith(prefix):
            continue

        key = raw_key[len(prefix) :]
        # Normalize:
        # - nesting: __
        # - case-insensitive
        # - hyphen treated as underscore
        parts = [p.lower().replace("-", "_") for p in key.split("__") if p]
        if not parts:
            continue

        cur: dict[str, Any] = result
        for p in parts[:-1]:
            nxt = cur.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[p] = nxt
            cur = nxt
        cur[parts[-1]] = raw_val

    return result


def _build_dataclass(
    cls: type[Any],
    merged: dict[str, Any],
    sources: dict[str, str],
    *,
    prefix_path: str,
    values_by_path: dict[str, Any],
) -> Any:
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        path = f"{prefix_path}.{f.name}" if prefix_path else f.name
        ftype = f.type

        if is_dataclass(ftype):
            sub_in = merged.get(f.name, {})
            if sub_in is None:
                sub_in = {}
            if not isinstance(sub_in, dict):
                raise ConfigError(
                    path=path,
                    expected="table/object",
                    value=sub_in,
                    source=sources.get(path, "unknown"),
                    hint="Use a TOML table or env vars with __ nesting.",
                )
            sub_obj = _build_dataclass(
                cast(type[Any], ftype),
                sub_in,
                sources,
                prefix_path=path,
                values_by_path=values_by_path,
            )
            kwargs[f.name] = sub_obj
            continue

        if f.name in merged:
            raw = merged[f.name]
            src = sources.get(path, sources.get(f.name, "unknown"))
        else:
            raw = MISSING
            src = sources.get(path, "default")

        if raw is MISSING:
            # might be REQUIRED or no default; we'll set None and validate REQUIRED later
            if f.default is REQUIRED:
                kwargs[f.name] = REQUIRED
                values_by_path[path] = REQUIRED
            else:
                # if dataclass has no default, dataclass ctor would error; we instead set None
                # and let required validation happen (or Optional coerce later)
                kwargs[f.name] = _default_for_missing(ftype)
                values_by_path[path] = kwargs[f.name]
            continue

        coerced = _coerce_value(path, raw, ftype, src)
        kwargs[f.name] = coerced
        values_by_path[path] = coerced

    return cls(**kwargs)


def _default_for_missing(ftype: Any) -> Any:
    # If Optional, default to None; else leave REQUIRED marker-like None.
    if _is_optional(ftype):
        return None
    return None


def _coerce_value(path: str, raw: Any, target_type: Any, source: str) -> Any:
    """
    Coerce raw value into target_type.
    Raw may be:
      - Python type from TOML
      - str from env
    """
    # REQUIRED passthrough
    if raw is REQUIRED:
        return REQUIRED

    origin = get_origin(target_type)
    args = get_args(target_type)

    # Optional[T]
    if _is_optional(target_type):
        inner = _optional_inner(target_type)
        if raw is None:
            return None
        # env often uses empty string to mean unset; treat "" as None for Optional[str]?
        if isinstance(raw, str) and raw.strip() == "":
            return None
        return _coerce_value(path, raw, inner, source)

    # Literal
    if origin is Literal:
        # compare coerced-to-type-of-literals if possible
        lit_vals = list(args)
        # Attempt coercion to the type of the first literal (common case)
        if lit_vals:
            t0 = type(lit_vals[0])
            try:
                candidate = _coerce_scalar(path, raw, t0, source)
            except ConfigError:
                candidate = raw
        else:
            candidate = raw

        if candidate not in lit_vals:
            raise ConfigError(
                path=path,
                expected=f"one of {lit_vals!r}",
                value=raw,
                source=source,
                hint="Use one of the allowed literal values.",
            )
        return candidate

    # list[T]
    if origin is list and len(args) == 1:
        inner = args[0]
        if isinstance(raw, str):
            # env lists should be JSON
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ConfigError(
                    path=path,
                    expected=f"JSON array for list[{_type_str(inner)}]",
                    value=raw,
                    source=source,
                    hint=f'Provide a JSON array like ["a","b"]. ({e.msg})',
                )
            raw_list = parsed
        else:
            raw_list = raw

        if not isinstance(raw_list, list):
            raise ConfigError(
                path=path,
                expected=f"list[{_type_str(inner)}]",
                value=raw,
                source=source,
                hint="Provide a TOML array or a JSON array in env vars.",
            )
        return [
            _coerce_value(f"{path}[{i}]", item, inner, source) for i, item in enumerate(raw_list)
        ]

    # dict[str, T] (handy, still small)
    if origin is dict and len(args) == 2 and args[0] is str:
        inner = args[1]
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ConfigError(
                    path=path,
                    expected=f"JSON object for dict[str, {_type_str(inner)}]",
                    value=raw,
                    source=source,
                    hint=f'Provide a JSON object like {{"k": "v"}}. ({e.msg})',
                )
            raw_dict = parsed
        else:
            raw_dict = raw

        if not isinstance(raw_dict, dict):
            raise ConfigError(
                path=path,
                expected=f"dict[str, {_type_str(inner)}]",
                value=raw,
                source=source,
                hint="Provide a TOML table/object or a JSON object in env vars.",
            )
        out: dict[str, Any] = {}
        for k, v in raw_dict.items():
            if not isinstance(k, str):
                raise ConfigError(
                    path=path,
                    expected="string keys",
                    value=k,
                    source=source,
                    hint="Dictionary keys must be strings.",
                )
            out[k] = _coerce_value(f"{path}.{k}", v, inner, source)
        return out

    # Union (non-Optional) - keep conservative in v1
    if origin is Union:
        # Try each option; first that works wins
        last_err: ConfigError | None = None
        for opt in args:
            try:
                return _coerce_value(path, raw, opt, source)
            except ConfigError as e:
                last_err = e
        raise last_err or ConfigError(
            path=path, expected=_type_str(target_type), value=raw, source=source
        )

    # Scalars
    return _coerce_scalar(path, raw, target_type, source)


def _coerce_scalar(path: str, raw: Any, t: Any, source: str) -> Any:
    # If already correct type (and not bool-int confusion), accept
    if t is bool:
        return _coerce_bool(path, raw, source)

    if t in (int, float, str):
        # TOML provides proper types already, env provides strings.
        if isinstance(raw, t):
            return raw
        if isinstance(raw, bool) and t is int:
            # avoid True -> 1 surprises
            raise ConfigError(
                path=path,
                expected="int",
                value=raw,
                source=source,
                hint="Boolean is not accepted where an int is expected.",
            )
        if isinstance(raw, str):
            s = raw.strip()
            try:
                if t is int:
                    return int(s, 10)
                if t is float:
                    return float(s)
                if t is str:
                    return raw
            except ValueError:
                raise ConfigError(
                    path=path,
                    expected=t.__name__,
                    value=raw,
                    source=source,
                    hint=f"Use a valid {t.__name__} value.",
                )
        # last resort: try direct cast
        try:
            return t(raw)
        except Exception:
            raise ConfigError(
                path=path,
                expected=t.__name__,
                value=raw,
                source=source,
                hint=f"Could not convert value to {t.__name__}.",
            )

    # Allow Path (common and lovable)
    if t is Path:
        if isinstance(raw, Path):
            return raw
        if isinstance(raw, str):
            return Path(raw)
        raise ConfigError(
            path=path,
            expected="path",
            value=raw,
            source=source,
            hint="Provide a filesystem path string.",
        )

    # Fallback: if target is Any or object, accept
    if t is Any or t is object:
        return raw

    # Unknown type: refuse with clarity
    raise ConfigError(
        path=path,
        expected=_type_str(t),
        value=raw,
        source=source,
        hint="Unsupported type in v1. Consider using str/int/bool/float/Optional/list/Literal/nested dataclasses.",
    )


def _coerce_bool(path: str, raw: Any, source: str) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("true", "1", "yes", "y", "on"):
            return True
        if s in ("false", "0", "no", "n", "off"):
            return False
    raise ConfigError(
        path=path,
        expected="bool",
        value=raw,
        source=source,
        hint="Use true/false, yes/no, on/off, or 1/0.",
    )


def _is_optional(t: Any) -> bool:
    origin = get_origin(t)
    if origin in (Union, UnionType):
        args = get_args(t)
        return len(args) == 2 and type(None) in args
    return False


def _optional_inner(t: Any) -> Any:
    args = get_args(t)
    return args[0] if args[1] is type(None) else args[1]


def _type_str(t: Any) -> str:
    origin = get_origin(t)
    args = get_args(t)
    if origin is Union:
        return " | ".join(_type_str(a) for a in args)
    if origin is list and args:
        return f"list[{_type_str(args[0])}]"
    if origin is dict and len(args) == 2:
        return f"dict[{_type_str(args[0])}, {_type_str(args[1])}]"
    if origin is Literal:
        return f"Literal{args!r}"
    if hasattr(t, "__name__"):
        return t.__name__
    return str(t)


def _walk_fields(config_cls: type[Any], *, prefix: str) -> list[tuple[str, Any, Any, Any]]:
    out: list[tuple[str, Any, Any, Any]] = []
    for f in fields(config_cls):
        path = f"{prefix}.{f.name}" if prefix else f.name
        ftype = f.type
        default = _field_default_repr(f)
        if is_dataclass(ftype):
            out.extend(_walk_fields(cast(type[Any], ftype), prefix=path))
        else:
            out.append((path, f, ftype, default))
    return out


def _field_default_repr(f: Any) -> str:
    if f.default is REQUIRED:
        return "REQUIRED"
    if f.default is not MISSING:
        return repr(f.default)
    if f.default_factory is not MISSING:  # type: ignore[comparison-overlap]
        return "<factory>"
    return "<none>"


def _find_missing_required(config_cls: type[Any], obj: Any, *, prefix: str) -> list[str]:
    missing: list[str] = []
    for f in fields(config_cls):
        path = f"{prefix}.{f.name}" if prefix else f.name
        val = getattr(obj, f.name)
        if is_dataclass(f.type):
            missing.extend(_find_missing_required(cast(type[Any], f.type), val, prefix=path))
        else:
            if val is REQUIRED:
                missing.append(path)
    return missing


def _path_to_env(env_prefix: str, path: str) -> str:
    # db.host -> APP_DB__HOST
    parts = path.split(".")
    return env_prefix.upper() + "_" + "__".join(p.upper() for p in parts)
