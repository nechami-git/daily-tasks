"""A fake Anthropic client: returns scripted responses and records every request.

Only the surface the harness uses is faked: client.messages.create(**kw) returning
an object with .content (blocks with .type and .to_dict()), .stop_reason and .usage.
"""
import copy
from types import SimpleNamespace


class Block(SimpleNamespace):
    def to_dict(self, exclude_none: bool = True) -> dict:
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def text(t: str) -> Block:
    return Block(type="text", text=t)


def thinking(sig: str = "sig-1") -> Block:
    return Block(type="thinking", thinking="", signature=sig)


def tool_use(name: str, args: dict, id_: str) -> Block:
    return Block(type="tool_use", id=id_, name=name, input=args)


def usage(inp=100, out=20, cache_read=0, cache_write=0):
    return SimpleNamespace(input_tokens=inp, output_tokens=out,
                           cache_read_input_tokens=cache_read,
                           cache_creation_input_tokens=cache_write)


def response(*blocks, stop="end_turn", use=None):
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=use or usage())


class MockClient:
    def __init__(self, script: list):
        self.script = list(script)
        self.requests: list[dict] = []  # deep copies of every create(**kwargs)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        if not self.script:
            raise AssertionError("mock client: no scripted response left")
        return self.script.pop(0)
