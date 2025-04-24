from typing import Dict
import json
from hdfs.client import os
from extractor import Extractor
from requirements_parser import RequirementsParser
from constants.canonical_skill_map import canonical_skill_map
from constants.tech_capitalization import tech_capitalization_map
from storage.hdfs.hdfs import HDFSClient
from config import LLM_API_KEY, BASE_URL
from datetime import date


class Processor:
    def __init__(self, api_key: str, llm_url: str, system_prompt: str, hdfs_job_desc_dir: str, hdfs_save_dir: str) -> None:
        self.api_key = api_key
        self.llm_url = llm_url
        self.system_prompt=system_prompt
        self.hdfs_job_desc_dir = hdfs_job_desc_dir
        self.hdfs_save_dir = hdfs_save_dir
        self.llm_extractor = Extractor(api_key=api_key, base_url=llm_url, system_prompt=system_prompt)
        self.requirements_parser = RequirementsParser(canonical_skill_map=canonical_skill_map, tech_capitalization_map=tech_capitalization_map)
        self.hdfs_client = HDFSClient()
        self.job_paths = [os.path.join(hdfs_job_desc_dir, job) for job in self.hdfs_client.list_dir(hdfs_job_desc_dir)]

    def process_job_description(self, job_description: str = "") -> Dict:
        extracted_data = self.llm_extractor.extract_skills_from_job(job_description)
        cleaned_data = self.requirements_parser.clean_extracted_data(extracted_data)

        return cleaned_data


    def process_job(self, job_path: str):
        # Load the json file with job_path
        job_data = self.hdfs_client.read_json(job_path)
        job_skills = self.process_job_description(job_data["job_description"])
        
        processed_job = {
            "job_title": job_data["job_title"],
            "company": job_data["company"],
            "job_skills": job_skills["skills"]
        }

        self.hdfs_client.write(hdfs_path=os.path.join(self.hdfs_save_dir, os.path.basename(job_path)), data=json.dumps(processed_job))

        return processed_job


if __name__ == "__main__":
    with open("constants/system_prompt.txt", "r") as f:
        system_prompt = f.read()

    processor = Processor(api_key=LLM_API_KEY, llm_url=BASE_URL, system_prompt=system_prompt, hdfs_job_desc_dir="/jobs/2025-04-17", hdfs_save_dir="/skills/2025-04-17")

    print(f"Number of jobs to process: {len(processor.job_paths)}")

    for i, job in enumerate(processor.job_paths):
        processed_job = processor.process_job(job)
        print(f"Finished processing job num: {i}")
