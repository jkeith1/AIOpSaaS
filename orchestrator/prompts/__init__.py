"""Prompt templates for the AIOps agent.

Prompts live as plain .txt files next to this module so they can be edited
(or mounted over from a ConfigMap) without touching Python.
"""

from pathlib import Path

PROMPT_DIR = Path(__file__).parent


def load(name: str) -> str:
    """Load a prompt by name, with or without the .txt suffix.

    Raises:
        FileNotFoundError: If no such prompt exists.
    """
    path = PROMPT_DIR / (name if name.endswith(".txt") else f"{name}.txt")
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in PROMPT_DIR.glob("*.txt")))
        raise FileNotFoundError(f"No prompt named '{name}'. Available: {available}")
    return path.read_text(encoding="utf-8").strip()


__all__ = ["load", "PROMPT_DIR"]
