# saneconfig: 80% Understanding Briefing (Sharpened)

## What it is / Who it's for
**saneconfig** is a lightweight library (Python 3.11+) for loading typed configuration into dataclasses, with **zero runtime dependencies** (unless you opt-in to `.env` support). It is tailored for Python application developers who want robust, human-friendly, provenance-rich configuration from TOML files, environment variables, `.env` files, and CLI args, with type safety and clear error handling.

- **Audience:** Application developers (CLI, service, apps with complex/nested settings)
- **Not for:** Projects needing runtime extensibility, direct YAML, JSON, or non-dataclass config

## Key Features (Backed by Code)
- **Typed config loader:** Use Python dataclasses to define your config schema (`load()` expects a dataclass type only).
- **Strong precedence order:** Precedence: CLI args (if enabled) > env vars > .env (if enabled) > TOML (last-wins) > dataclass defaults ([Supported directly by `_core.py`](#architecture)).
- **Provenance tracking:** Clear reporting on where each config value came from, per dotted-path, via the `LoadReport` class with `.source_of(path)`/`.value_of(path)` ([see `_report.py`](#reporting)).
- **Rich error reporting:** Typed exceptions (`ConfigError`, `MissingRequiredError`) include value, expected type, source, hints ([see `_errors.py`](#errors)).
- **Schema docs:** Autogenerate a Markdown config table with `dump_schema()` (renders env var, type, default, help doc for each field).
- **Zero deps (unless `.env`):** Dependency-free unless `.env` support is enabled (uses `python-dotenv` if `dotenv` extra is installed).
- **Supports nested dataclasses & complex types:** Handles nesting, lists/dicts (from JSON env values), `Literal`, `Optional`, `Path`, etc. (`_core.py` shows recursion and coercion for these).

## Architecture (Modules/How It Works)
- **`src/saneconfig/__init__.py`:** Library API; exports `load`, `dump_schema`, `REQUIRED`, `ConfigError`.  
- **`_core.py` (core logic):**
    - `load()`: Entrypoint; does merging of all config layers with per-path provenance.
    - `dump_schema()`: Markdown doc generator.
    - Internal helpers for TOML/env/argv parsing and type coercion.
    - All IO is file/env/argv; no network or database IO.
- **`_errors.py`:** Custom exceptions for type errors and missing values, with rich detail.
- **`_report.py`:** `LoadReport` dataclass—tracks sources (`sources_by_path`) and values (`values_by_path`), lets you introspect/report provenance for each field.
- **No CLI or background runtime:** Intended as a pure importable library—no CLI wrapper or service included.
- **Test & doc structure:** Tests (pytest) present; Sphinx for documentation.

## Execution Model / Entrypoints
- **You import it:** `from saneconfig import load`
- **You define a config dataclass:** Schema is a Python dataclass.
- **You call `load(ConfigClass, ...)`:** Handles TOML, env, CLI, .env. Returns instance of your dataclass (optionally also returns a `LoadReport`).

## Provenance & Reporting
- Each config value tracks its origin (default, file, env, CLI, dotenv), visible via `LoadReport.sources_by_path[path]`.
- Main helper for debugging configs: `load(..., return_report=True)` gives both config object and provenance report (see `_core.py`, `_report.py`).

## Supported Types / Type Coercion
- **Primitives:** int, float, str, bool
- **Complex:** lists, dicts (from JSON in env/CLI), Literals (choices), Optionals, nested dataclasses       
- **Edge cases:** Fails fast (with rich errors) on type mismatches, unsupported types, or missing required fields
- **Environment variable mapping:**
    - Prefix optional (e.g., `APP_FOO`) and uses double-underscore for nesting (`APP_DB__HOST`)
    - Lists/dicts require JSON-encoded env/CLI values

## Not Found in Code
- **No config for saneconfig itself:** Everything is about loading *your app's* settings—saneconfig does not have its own runtime settings.
- **No CLI tool or external service included**

## How to Run & Develop
- **Install:** `pip install saneconfig` (use `[dotenv]` extra for `.env`)
- **Test:** pytest
- **Docs:** Sphinx

## Open Questions / Clarifications
- **Provenance reporting:** Fully explicit via `LoadReport` per-dotted-path.
- **Non-standard types:** Enums not mentioned, but lists, dicts, Literals and nested dataclasses are supported as per code.
- **Differences from pydantic-settings, dynaconf:** Not a drop-in; derived purely from dataclasses; no validation beyond Python type system; no plugin system.

---

### Suggested 3 Files to Learn System
1. **`src/saneconfig/_core.py`:** Main merging, loading, and type handling logic.
2. **`src/saneconfig/_errors.py`:** Error structure, rich detail on errors.
3. **`src/saneconfig/_report.py`:** Provenance reporting structure (`LoadReport`).

---

## Next Deep Dives / Unknowns
- `src/saneconfig/_core.py` implementation is quite detailed but if you need edge behavior on specific types (enums, advanced `typing` types), look for additional helpers (_the code supports the basics but isn’t explicit about all edge-cases_).

## 80% Confidence: What is Supported (Direct from Files)
- All the above features (typed loading, precedence, provenance, type coercion/validation, error/detail, zero deps except dotenv) are **directly implemented in the code**.
- No plugin/hook system found, and no settings for saneconfig itself.


# Reading plan

## Ordered steps to get productive fast

1. **README.md**
   Why: Overview, quickstart, and usage patterns for the library.
   - Look for install instructions
   - Basic usage examples and major features
   - Any caveats or known issues
   Time: 7 min

2. **src/saneconfig/__init__.py**
   Why: Understand the public API surface and what main symbols are exposed.
   - Which functions/classes are imported/exported
   - Any top-level docstrings or documentation
   Time: 5 min

3. **src/saneconfig/_core.py**
   Why: Main configuration loading, merging, and type coercion logic.
   - Signature and flow of `load()` and `dump_schema()`
   - How config sources are merged and precedence handled
   - Any helpers for TOML/env/CLI parsing
   Time: 20 min

4. **src/saneconfig/_errors.py**
   Why: See all custom error types and the details provided for config failures.
   - List of exception classes (`ConfigError`, etc.)
   - What information is included in exceptions
   Time: 7 min

5. **src/saneconfig/_report.py**
   Why: Learn how provenance (config source tracking) is implemented and reported.
   - Structure of `LoadReport` class
   - How you can access sources and values for each config path
   Time: 7 min

6. **tests/test_core.py**
   Why: See real-world examples of config schemas and edge case handling.
   - How tests call `load()` and expect results
   - Coverage of precedence, errors, and type coercion
   Time: 10 min

7. **tests/test_regressions.py**
   Why: Reveals tricky or previously-broken edge cases.
   - What regressions or bugfixes were needed
   - Any special config features tested
   Time: 7 min

8. **docs/usage.rst**
   Why: Extended usage docs, may include scenarios beyond README.
   - API explanations and examples
   - Best practice notes
   Time: 5 min

9. **pyproject.toml**
   Why: Declares dependencies, extra requirements (e.g., for `.env` support), and project metadata.
   - Look for `[project.optional-dependencies]`
   - Packaging metadata and entry points
   Time: 3 min

10. **docs/api.rst**
    Why: API reference, shows all public functions and classes.
    - Brief on each function, class, and usage
    Time: 5 min

---

### If you only have 30 minutes
1. **README.md** – 7 min: Get the gist and core usage patterns.
2. **src/saneconfig/__init__.py** – 5 min: Find the public API.
3. **src/saneconfig/_core.py** – 15 min: Skim `load()` and `dump_schema()` to understand how the loader works end-to-end.

---

### If you need to make a change safely
- **How to run tests/build:** From the root directory, run `pytest` (tests are in the `tests/` directory).  
- **Where to add a small change and validate quickly:** Edit a function (e.g., a logic bug or enhancement in `src/saneconfig/_core.py`), then run the relevant test(s) in `tests/test_core.py` for fast feedback.  