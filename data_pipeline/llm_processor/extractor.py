import json
from typing import Dict
import openai
from config import LLM_API_KEY


class Extractor:
    def __init__(self, api_key: str, base_url: str, system_prompt: str) -> None:
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.system_prompt = system_prompt

    def extract_skills_from_job(self, description: str) -> Dict:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": description}
        ]

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            response_format={
                "type": "json_object"
            }
        )

        extracted_data = response.choices[0].message.content

        return json.loads(extracted_data)


if __name__ == "__main__":
    with open("test_prompts.txt", "r") as f:
        test_job_description = f.read()

    with open("../../constants/system_prompt.txt", "r") as f:
        system_prompt = f.read()

    extractor = Extractor(api_key=LLM_API_KEY, base_url="https://api.deepseek.com", system_prompt=system_prompt)

    print(extractor.extract_skills_from_job(test_job_description))
