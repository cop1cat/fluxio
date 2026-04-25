# Installation

fluxio requires **Python 3.12+**.

## Core package

```bash
pip install fluxio
```

## Optional extras

```bash
pip install fluxio[redis]      # RedisStore for durable checkpoints
pip install fluxio[langfuse]   # LangfuseCallback for tracing
pip install fluxio[all]        # everything
```

## Dev install from source

```bash
git clone https://github.com/example/fluxio
cd fluxio
uv sync --all-extras
uv run pytest
```

## Runtime dependencies

| Package      | Purpose                                   |
|--------------|-------------------------------------------|
| pyrsistent   | immutable HAMT backing `Context`          |
| pydantic     | optional input/output schema validation   |

Everything else (`redis`, `langfuse`) is pulled in only when you enable the corresponding extra.
