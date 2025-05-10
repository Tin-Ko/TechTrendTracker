import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from storage.hdfs.hdfs import HDFSClient
import json
import uuid
import os
from datetime import date
import pika

class LinkedInJobContentSpider(scrapy.Spider):
    name = "linkedin_job_content_spider"
    handle_httpstatus_all = False
    handle_httpstatus_list = [200]

    custom_settings = {
        "DOWNLOAD_DELAY": 4,  # Set a fixed delay of 4 seconds
        "RANDOMIZE_DOWNLOAD_DELAY": True,  # Add randomness to avoid detection
        "AUTOTHROTTLE_ENABLED": True,  # Enable AutoThrottle for better crawling
        "AUTOTHROTTLE_START_DELAY": 4,  # Minimum delay
        "AUTOTHROTTLE_MAX_DELAY": 8,  # Maximum delay
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,  # One request at a time
    }

    with open("data_pipeline/scraper/data_science_job_links.txt", "r") as f:
        start_urls = f.readlines()
        print(f"number of job links: {len(start_urls)}")


    def __init__(self) -> None:
        super().__init__()
        self.hdfs_client = HDFSClient()
        self.counter = 0
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
        self.channel = self.connection.channel()

        self.channel.queue_declare(queue="job_queue", durable=True)


    def parse(self, response):
        print(f"scraping job number: {self.counter}")
        try:
            job_title = response.xpath('//h1[contains(@class, "top-card-layout__title")]/text()').get()
            company = response.xpath('//a[contains(@class, "topcard__org-name-link")]/text()').get()
            company = company.strip(" \n")
            print(job_title)
            print(company)
            text_list = response.xpath(
                '//div[contains(@class, "show-more-less-html__markup")]/descendant-or-self::*/text()'
            ).getall()
            clean_text = ' '.join(t.strip() for t in text_list if t.strip())


            job_data = {
                "job_title": job_title,
                "company": company,
                "job_description": clean_text
            }

            job_data_json = json.dumps(job_data, ensure_ascii=False, indent=4)

            hdfs_path = os.path.join("/jobs", "data_scientist", str(date.today()), f"{uuid.uuid1()}.json")

            self.hdfs_client.write(hdfs_path, job_data_json, overwrite=True)
            
            self.channel.basic_publish(
                exchange='',
                routing_key='job_queue',
                body=hdfs_path,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                )
            )

            self.counter += 1

        except Exception as e:
            print(f"link num: {self.counter}, {response.url} doesn't exist, skipping now...")
            self.counter += 1
            return

        


if __name__ == "__main__":
    process = CrawlerProcess(get_project_settings())
    process.crawl(LinkedInJobContentSpider)
    process.start()
