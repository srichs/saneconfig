Usage
=====

Quick start
-----------

.. code-block:: python

   from dataclasses import dataclass
   from saneconfig import REQUIRED, load


   @dataclass
   class AppConfig:
       debug: bool = False
       port: int = 8080
       database_url: str = REQUIRED


   config = load(
       AppConfig,
       env_prefix="APP",
       files=["config.toml", "config.local.toml"],
   )

Configuration precedence
------------------------

1. Environment variables
2. TOML files (later files override earlier files)
3. Dataclass defaults

Environment variable mapping
----------------------------

With ``env_prefix="APP"``:

- ``APP_PORT=9000`` maps to ``port``
- ``APP_DEBUG=true`` maps to ``debug``
- nested values use ``__`` separators (for example, ``APP_DB__HOST``)

For list values provided via environment variables, use JSON array syntax.

.. code-block:: bash

   APP_ALLOWED='["a", "b"]'

Loading secrets securely
------------------------

For required secret values (for example, ``api_key = REQUIRED``), provide them via
environment variables instead of committing them to TOML files.

.. code-block:: bash

   export APP_API_KEY='your-real-secret'

.. code-block:: python

   cfg = load(App, env_prefix="APP")

For local development, you can use ``dotenv=True`` with ``saneconfig[dotenv]`` and
keep ``.env`` out of version control.
