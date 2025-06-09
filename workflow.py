from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Dict, Optional
from chat import Chat

import yaml
import openai

# ---------------------------------------------------------------------------
# 1. Prompt‑library loader (YAML)
# ---------------------------------------------------------------------------
class PromptLibrary:
    def __init__(self, path: str | Path = "prompts.yml") -> None:
        self.path = Path(path)
        try:
            with self.path.open("r", encoding="utf‑8") as fh:
                data = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            raise SystemExit(f"Prompt file '{self.path}' not found.")

        self.prompts: Dict[str, str] = data.get("prompts", {})

    def get(self, key: str) -> str:
        try:
            return self.prompts[key]
        except KeyError as err:
            raise KeyError(f"Prompt key '{key}' missing in {self.path}") from err


# ---------------------------------------------------------------------------
# 2. Basic I/O class
# ---------------------------------------------------------------------------

class IOHandler:
    def ask(self, prompt: str) -> str:
        return input(prompt)

    def say(self, text: str, *, end: str = "\n") -> None:
        print(text, end=end)

    def flush(self) -> None:
        return


# ---------------------------------------------------------------------------
# 3. FSM primitives
# ---------------------------------------------------------------------------
class Context(dict):
    """Shared scratchpad between states (can be subclassed for type hints)."""


class BaseState:
    name: str  # each concrete state sets its symbolic name

    def __init__(self, chat: Chat, io: IOHandler, prompts: PromptLibrary):
        self.chat = chat
        self.io = io
        self.prompts = prompts

    def on_enter(self, ctx: Context) -> None:
        raise NotImplementedError

    def next_state(self, ctx: Context) -> Optional[str]:
        raise NotImplementedError
