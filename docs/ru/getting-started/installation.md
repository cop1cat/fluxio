# Установка

fluxio требует **Python 3.12+**.

## Основной пакет

```bash
pip install fluxio
```

## Дополнительные extras

```bash
pip install fluxio[redis]      # RedisStore для durable чекпоинтов
pip install fluxio[langfuse]   # LangfuseCallback для трассировки
pip install fluxio[all]        # всё сразу
```

## Установка из исходников (для разработки)

```bash
git clone https://github.com/example/fluxio
cd fluxio
uv sync --all-extras
uv run pytest
```

## Runtime-зависимости

| Пакет        | Назначение                                         |
|--------------|----------------------------------------------------|
| pyrsistent   | immutable HAMT под `Context`                       |
| pydantic     | опциональная валидация входа / выхода стейджей     |

Всё остальное (`redis`, `langfuse`) подтягивается только при включении соответствующего extras.
