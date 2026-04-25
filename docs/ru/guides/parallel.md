# Параллельное выполнение

Два способа запускать стейджи одновременно: явный `Parallel([...])` и автопараллелизация на этапе компиляции.

## Явный `Parallel`

```python
from fluxio import Parallel

Pipeline([
    fetch_user,
    Parallel([enrich_profile, fetch_orders]),
    format_response,
])
```

Ветки исполняются через `asyncio.gather`. Каждая начинает с форка контекста, записи всех веток мержатся после завершения.

## Авто-параллелизм

С объявленными reads/writes fluxio сам находит независимые стейджи и вставляет `Parallel`:

```python
@stage(reads=frozenset({"user_id"}), writes=frozenset({"user"}))
async def fetch_user(ctx): ...

@stage(reads=frozenset({"user_id"}), writes=frozenset({"orders"}))
async def fetch_orders(ctx): ...

Pipeline([fetch_user, fetch_orders])  # скомпилируется как Parallel([fetch_user, fetch_orders])
```

В лог пишется warning — так это заметно. Отключить можно через `auto_parallel=False`.

## Конфликты мерджа

Две ветки пишут в один ключ — `MergeConflictError` на мердже. Если writes объявлены, компилятор поймает конфликт ещё на компиляции.

## Fire-and-forget

```python
Parallel([audit_log, metrics_push], mode=ForkMode.FIRE_FORGET)
```

Ветки запускаются параллельно, но ошибки только логируются — не пробрасываются. Мерджа нет, выполнение продолжается с контекста до форка.

## Советы

- Объявляйте reads/writes. Это делает намерение явным, включает авто-параллелизм и ловит конфликты рано.
- Parallel внутри dict-блока роутинга (`{"premium": [Parallel([...])]}`) работает как ожидается.
- Scheduler использует asyncio + thread pool; CPU-bound `SYNC`-стейджи внутри `Parallel` действительно бегут на разных потоках.
