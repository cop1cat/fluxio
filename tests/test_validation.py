from pydantic import BaseModel
import pytest

from fluxio import Pipeline, stage


class UserInput(BaseModel):
    user_id: int


class UserOutput(BaseModel):
    user: dict


async def test_input_schema_passes_with_extras():
    @stage(input_schema=UserInput)
    async def loader(ctx):
        return ctx.set("user", {"id": ctx["user_id"]})

    async with Pipeline([loader], auto_parallel=False) as pipe:
        result = await pipe.invoke({"user_id": 7, "unrelated": "junk"})
    assert result.get("user") == {"id": 7}


async def test_input_schema_fails_on_wrong_type():
    @stage(input_schema=UserInput)
    async def loader(ctx):
        return ctx

    async with Pipeline([loader], auto_parallel=False) as pipe:
        with pytest.raises(RuntimeError, match="Input validation failed"):
            await pipe.invoke({"user_id": "not-an-int"})


async def test_output_schema_fails_on_missing_write():
    @stage(output_schema=UserOutput)
    async def broken(ctx):
        return ctx

    async with Pipeline([broken], auto_parallel=False) as pipe:
        with pytest.raises(RuntimeError, match="Output validation failed"):
            await pipe.invoke({})
