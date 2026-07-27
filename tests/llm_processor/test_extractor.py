"""Unit tests for Extractor's live Ollama path.

Rewritten: the previous version tested a removed API (an OpenAI-based
`Extractor(api_key=..., base_url=...)`) and could not even construct the current
class. This patches `ollama.chat`, so it needs no running daemon — but it does
need the `ollama` client library importable, so the whole module is skipped when
that's absent (the model-free CI job). Extractor is a thin adapter; the real
extraction logic is covered by the requirements_parser and pipeline suites."""

import json
import unittest
from unittest.mock import patch

import pytest

pytest.importorskip("ollama")  # skip if the client lib isn't installed

from data_pipeline.llm_processor.extractor import Extractor  # noqa: E402


class TestExtractor(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = Extractor(model="gemma4:latest", system_prompt="Extract skills")
        self.job_description = "Looking for an engineer with Python and SQL"

    @patch("data_pipeline.llm_processor.extractor.ollama.chat")
    def test_parses_json_skill_list(self, mock_chat) -> None:
        mock_chat.return_value = {"message": {"content": '{"skills": ["Python", "SQL"]}'}}
        result = self.extractor.extract_skills_from_job(self.job_description)
        self.assertEqual(result, {"skills": ["Python", "SQL"]})

    @patch("data_pipeline.llm_processor.extractor.ollama.chat")
    def test_passes_model_and_system_prompt(self, mock_chat) -> None:
        mock_chat.return_value = {"message": {"content": '{"skills": []}'}}
        self.extractor.extract_skills_from_job(self.job_description)
        _, kwargs = mock_chat.call_args
        self.assertEqual(kwargs["model"], "gemma4:latest")
        self.assertEqual(kwargs["messages"][0], {"role": "system", "content": "Extract skills"})

    @patch("data_pipeline.llm_processor.extractor.ollama.chat")
    def test_invalid_json_raises(self, mock_chat) -> None:
        mock_chat.return_value = {"message": {"content": '{"skills": ["Python"'}}  # truncated
        with self.assertRaises(json.JSONDecodeError):
            self.extractor.extract_skills_from_job(self.job_description)


if __name__ == "__main__":
    unittest.main()
