import json
import os
from typing import Dict
from httpx import options
import ollama
import openai
from data_pipeline.llm_processor.config import LLM_API_KEY


class Extractor:
    def __init__(self, model: str, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt

    def extract_skills_from_job(self, description: str) -> Dict:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": description}
        ]

        response = ollama.chat(
            model=self.model,
            messages=messages,
            format="json",
            options={"temperature": 0},
        )


        extracted_data = response["message"]["content"]
        print(extracted_data)

        return json.loads(extracted_data)

    def extract_skills_from_job_cloudLLM(self, description: str) -> Dict:
        client = openai.OpenAI(
            api_key=LLM_API_KEY,
            base_url="https://api.deepseek.com"
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": description}
        ]

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            response_format={
                "type": "json_object"
            }
        )

        extracted_data = response.choices[0].message.content
        print("Extracted data: ", extracted_data)

        return json.loads(extracted_data)


    def test_extractor(self, job_description: str) -> None:
        # extracted = self.extract_skills_from_job(job_description)
        deepseek_extracted = self.extract_skills_from_job_cloudLLM(job_description)
        # print(deepseek_extracted)


if __name__ == "__main__":
    with open(os.path.join("data_pipeline", "llm_processor", "test_prompts.txt"), "r") as f:
        test_job_description = f.read()

    with open("constants/system_prompt.txt", "r") as f:
        system_prompt = f.read()

    extractor = Extractor(model="llama3", system_prompt=system_prompt)
    for i in range(3):
        extractor.test_extractor(test_job_description)

