import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from storage.hdfs.hdfs import HDFSClient
import json
import uuid
import os
from datetime import date

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

    with open("data_pipeline/scraper/job_links.txt", "r") as f:
        start_urls = f.readlines()[997:]
        print(f"number of job links: {len(start_urls)}")

    # start_urls = ["https://www.linkedin.com/jobs/view/web-software-engineering-intern-at-soundcloud-4195991198?position=1&pageNum=0&refId=1ZSrvc1a0T41JH2uUEbQ%2Bg%3D%3D&trackingId=9JG9xBtQruN8CxIigU4t6A%3D%3D"]

    def __init__(self) -> None:
        super().__init__()
        self.hdfs_client = HDFSClient()
        self.counter = 998

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

            hdfs_path = os.path.join("/jobs", str(date.today()), f"{uuid.uuid1()}.json")

            self.hdfs_client.write(hdfs_path, job_data_json, overwrite=True)
            self.counter += 1
        except Exception as e:
            print(f"link num: {self.counter}, {response.url} doesn't exist, skipping now...")
            self.counter += 1
            return

        


if __name__ == "__main__":
    process = CrawlerProcess(get_project_settings())
    process.crawl(LinkedInJobContentSpider)
    process.start()
