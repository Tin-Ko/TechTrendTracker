import unittest
from data_pipeline.llm_processor.extractor import Extractor
from unittest.mock import patch, MagicMock

class TestExtractor(unittest.TestCase):

    def setUp(self) -> None:
        self.api_key = "fake-key"
        self.base_url = "https://fake-url.com"
        self.system_prompt = "Extract skills",
        self.job_description = "We are looking for an engineer with experience in Python and SQL"
        self.llm_extractor = Extractor(api_key=self.api_key, base_url=self.base_url, system_prompt=self.system_prompt)

    @patch("extractor.openai.OpenAI")
    def test_extract_skills_from_job(self, mock_openai_class) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"skills": ["Python", "SQL"]}'
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        result = self.llm_extractor.extract_skills_from_job(description=self.job_description)
        expected = {
            "skills": ["Python", "SQL"]
        }

        self.assertEqual(result, expected)

    @patch("extractor.openai.OpenAI")
    def test_invalid_json_response(self, mock_openai_class) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"skills": ["Python", "SQL"]'
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        result = self.llm_extractor.extract_skills_from_job(description=self.job_description)
        
        with self.assertRaises(Exception):
            self.llm_extractor.extract_skills_from_job(description=self.job_description)


if __name__ == "__main__":
    unittest.main()
