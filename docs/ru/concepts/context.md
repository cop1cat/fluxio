# Контекст

`Context` — неизменяемое, copy-on-write состояние, проходящее через каждый стейдж.

## Чтение

```python
ctx.get("user_id")           # permissive — None если ключа нет
ctx.get("tier", "standard")  # с дефолтом
ctx["user_id"]               # строго — KeyError если ключа нет
"user_id" in ctx             # проверка наличия
```

`ctx[key]` — когда ключ обязан быть (отсутствие — это баг). `ctx.get(key)` — когда "нет ключа" допустимо.

## Запись

Каждая запись возвращает **новый** контекст; оригинал неизменен.

```python
new_ctx = ctx.set("user", {"id": 1})
ctx.get("user")       # None — оригинал не изменён
new_ctx.get("user")   # {"id": 1}
```

Несколько записей разом через `update`:

```python
ctx = ctx.update({"priority": "high", "retries": 0})
```

## Structural sharing

`Context` — это обёртка над `pyrsistent.PMap` (HAMT). `set()` делит неизменённые поддеревья со старым контекстом — копии O(log₃₂ N) по времени и памяти.

Fork — O(1): просто новая обёртка над тем же деревом с другим именем ветки.

## Форк и мердж

Используется внутри `Parallel` и роутинга:

```python
base = Context.create({"user_id": 1})
branch_a = base.fork("a").set("profile", {...})
branch_b = base.fork("b").set("orders", [...])

merged = Context.merge(base, [branch_a, branch_b])
# В merged есть и "profile", и "orders"
```

Если две ветки пишут в один ключ — `MergeConflictError` с указанием конфликтующих ключей и имён веток.

## Снепшоты

Для чекпоинтов и дебага:

```python
data = ctx.snapshot()          # plain dict[str, Any]
ctx_ = Context.from_snapshot(data, name="restored")
```

Именно снепшоты сохраняет `CheckpointStore`.
