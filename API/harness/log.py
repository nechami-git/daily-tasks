"""Tiny helper so every runtime action is printed with the file that did it."""


def say(file: str, msg: str) -> None:
    print(f"[{file}] {msg}", flush=True)
