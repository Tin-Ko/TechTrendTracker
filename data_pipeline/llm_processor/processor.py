from typing import Dict
import json
from hdfs.client import os
from pika import delivery_mode
from data_pipeline.llm_processor.extractor import Extractor
from data_pipeline.llm_processor.requirements_parser import RequirementsParser
from constants.canonical_skill_map import canonical_skill_map
from constants.tech_capitalization import tech_capitalization_map
from storage.hdfs.hdfs import HDFSClient
from datetime import date
import uuid
import pika



class Processor:
    def __init__(self, model: str, system_prompt: str, hdfs_job_desc_dir: str, hdfs_save_dir: str) -> None:
        self.hdfs_job_desc_dir = hdfs_job_desc_dir
        self.hdfs_save_dir = hdfs_save_dir
        self.llm_extractor = Extractor(model=model, system_prompt=system_prompt)
        self.requirements_parser = RequirementsParser(canonical_skill_map=canonical_skill_map, tech_capitalization_map=tech_capitalization_map)
        self.hdfs_client = HDFSClient()
        self.job_paths = [os.path.join(hdfs_job_desc_dir, job) for job in self.hdfs_client.list_dir(hdfs_job_desc_dir)]
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
        self.channel = self.connection.channel()

        self.channel.queue_declare(queue="job_queue", durable=True)
        self.channel.queue_purge(queue="job_queue")


    def process_job_description(self, job_description: str = "") -> Dict:
        extracted_data = self.llm_extractor.extract_skills_from_job_cloudLLM(job_description)
        cleaned_data = self.requirements_parser.clean_extracted_data(extracted_data)

        return cleaned_data


    def process_job(self, job_path: str) -> None:
        # Load the json file with job_path
        job_data = self.hdfs_client.read_json(job_path)
        job_skills = self.process_job_description(job_data["job_description"])
        
        processed_job = {
            "job_title": job_data["job_title"],
            "company": job_data["company"],
            "job_skills": job_skills["skills"]
        }

        self.hdfs_client.write(hdfs_path=os.path.join(self.hdfs_save_dir, os.path.basename(job_path)), data=json.dumps(processed_job))
    
    def consumer_callback(self, ch, method, properties, body):
        job_path = body.decode("utf-8")
        print(f"Received hdfs path: {job_path}")
        self.process_job(job_path=job_path)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        

    def consume_messages(self) -> None:
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue="job_queue", on_message_callback=self.consumer_callback)
        self.channel.start_consuming()


if __name__ == "__main__":
    with open("constants/system_prompt.txt", "r") as f:
        system_prompt = f.read()

    today_date = date.today()
    jobs_base_path = "/jobs"
    skills_base_path = "/skills"
    job_title = "software_engineer"
    hdfs_job_desc_dir = os.path.join(jobs_base_path, job_title, str(today_date))
    hdfs_save_dir = os.path.join(skills_base_path, job_title, str(today_date))
    

    processor = Processor(model="llama3:instruct", system_prompt=system_prompt, hdfs_job_desc_dir=hdfs_job_desc_dir, hdfs_save_dir=hdfs_save_dir)


    processor.consume_messages()
