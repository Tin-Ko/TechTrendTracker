"""Turn a co-occurring skill triple into a portfolio project via local Gemma.

Mirrors the offline extraction path (ollama.chat, JSON format, temperature 0)
so generation stays deterministic and fully local -- no cloud LLM, and nothing
for the Cloud Run request path to host.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Sequence

import ollama


# Same default tag as the ingest worker (data_pipeline/llm_processor/processor.py).
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma3:latest")

_LEVELS = {"BEGINNER", "INTERMEDIATE", "ADVANCED"}

_SYSTEM_PROMPT = """You design portfolio project ideas for people breaking into tech (students and career-switchers).

You will be given exactly THREE skills. Invent ONE small, finishable project that genuinely uses ALL THREE together -- not three features bolted on, but one coherent app where each skill has a real job.

Return STRICT JSON, no markdown, with exactly these keys:
{
  "title": "a 3-6 word project name, plain text",
  "level": "BEGINNER | INTERMEDIATE | ADVANCED",
  "blurb": "1-2 sentences: what they build and why it impresses a recruiter. Concrete, no fluff."
}

Choose the level honestly from how hard it is to combine these three skills well. Do not mention any skill that was not given."""


@dataclass(frozen=True)
class Project:
    title: str
    level: str
    blurb: str


class ProjectGenerator:
    def __init__(self, model: str = LLM_MODEL) -> None:
        self.model = model

    def generate(self, skills: Sequence[str]) -> Project:
        if len(skills) != 3:
            raise ValueError(f"expected 3 skills, got {len(skills)}: {skills!r}")

        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": "Skills: " + ", ".join(skills)},
            ],
            format="json",
            options={"temperature": 0},
        )
        data = json.loads(response["message"]["content"])

        title = str(data.get("title", "")).strip()
        blurb = str(data.get("blurb", "")).strip()
        level = str(data.get("level", "")).strip().upper()
        if level not in _LEVELS:
            level = "INTERMEDIATE"
        if not title or not blurb:
            raise ValueError(f"model returned empty title/blurb for {skills!r}: {data!r}")

        return Project(title=title, level=level, blurb=blurb)
