import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from twisted.internet.defer import waitForDeferred
from storage.hdfs.hdfs import HDFSClient

class LinkedInJobContentSpider(scrapy.Spider):
    name = "linkedin_job_content_spider"
    custom_settings = {
        "DOWNLOAD_DELAY": 4,  # Set a fixed delay of 4 seconds
        "RANDOMIZE_DOWNLOAD_DELAY": True,  # Add randomness to avoid detection
        "AUTOTHROTTLE_ENABLED": True,  # Enable AutoThrottle for better crawling
        "AUTOTHROTTLE_START_DELAY": 4,  # Minimum delay
        "AUTOTHROTTLE_MAX_DELAY": 8,  # Maximum delay
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,  # One request at a time
    }

    start_urls = ["https://www.linkedin.com/jobs/view/web-software-engineering-intern-at-soundcloud-4195991198?position=1&pageNum=0&refId=1ZSrvc1a0T41JH2uUEbQ%2Bg%3D%3D&trackingId=9JG9xBtQruN8CxIigU4t6A%3D%3D"]

    def parse(self, response):
        job_title = response.xpath('//h1[contains(@class, "top-card-layout__title")]/text()').get()
        company = response.xpath('//a[contains(@class, "topcard__org-name-link")]/text()').get()
        company = company.strip(" \n")
        print(job_title)
        print(company)
        text_list = response.xpath(
            '//div[contains(@class, "show-more-less-html__markup")]/descendant-or-self::*/text()'
        ).getall()
        clean_text = '\n'.join(t.strip() for t in text_list if t.strip())
        # yield {"description:": clean_text}
        print(clean_text)


if __name__ == "__main__":
    process = CrawlerProcess(get_project_settings())
    process.crawl(LinkedInJobContentSpider)
    process.start()
