import os
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from twisted.internet.defer import waitForDeferred

class LinkedInJobSpider(scrapy.Spider):
    file_name = "job_links.txt"
    custom_settings = {
        "DOWNLOAD_DELAY": 4,  # Set a fixed delay of 4 seconds
        "RANDOMIZE_DOWNLOAD_DELAY": True,  # Add randomness to avoid detection
        "AUTOTHROTTLE_ENABLED": True,  # Enable AutoThrottle for better crawling
        "AUTOTHROTTLE_START_DELAY": 4,  # Minimum delay
        "AUTOTHROTTLE_MAX_DELAY": 8,  # Maximum delay
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,  # One request at a time
    }

    name = "linkedin_jobs"
    start_url = "https://www.linkedin.com/jobs/search/?"
    f_E = ["1", "2", "3", "4"]
    f_TPR = "r604800"
    geoID = "102095887"
    keywords = [
        "Software%20Engineer",
        "Full%20Stack%20Developer",
        "Backend%20Developer",
        "Frontend%20Developer",
        "Mobile%20App%20Developer",
        "Embedded%20Systems%20Engineer",
        "DevOps%20Engineer",
        "Site%20Reliability%20Engineer",
        "Cloud%20Engineer",
        "Game%20Developer",
        "Machine%20Learning%20Engineer",
        "Data%20Scientist",
        "AI%20Researcher",
        "Deep%20Learning%20Engineer", 
        "NLP%20Engineer",
        "Computer%20Vision%20Engineer",
        "Data%20Engineer",
        "Big%20Data%20Engineer",
        "Cybersecurity%20Analyst",
        "Ethical%20Hacker",
        "Penetration%20Tester",
        "Security%20Engineer",
        "Network%20Security%20Engineer",
        "Cloud%20Security%20Engineer",
        "Incident%20Response%20Analyst",
        "Digital%20Forensics%20Analyst",
        "Cryptographer",
        "Network%20Engineer",
        "System%20Administrator",
        "Cloud%20Architect",
        "IT%20Support%20Specialist",
        "Linux%20System%20Administrator",
        "Database%20Administrator",
        "Web%20Developer",
        "UI%2FUX%20Designer",
        "Frontend%20Engineer",
        "Interaction%20Designer",
        "Web%20Security%20Engineer",
        "Hardware%20Engineer",
        "Embedded%20Systems%20Developer",
        "IoT%20Engineer",
        "FPGA%20Engineer",
        "QA%20Engineer",
        "Test%20Automation%20Engineer",
        "Software%20Development%20Engineer%20in%20Test",
        "Blockchain%20Developer",
        "Quantum%20Computing%20Researcher",
        "Robotics%20Engineer",
        "AR%2FVR%20Developer",
        "Technical%20Program%20Manager",
    ]
    origin = "JOB_SEARCH_PAGE_SEARCH_BUTTON"
    start_urls = []
    for experience in f_E:
        for keyword in keywords:
            start_urls.append(start_url + "f_E="+ experience + "&f_TPR=" + f_TPR + "&geoID=" + geoID + "&keywords=" + keyword + "&origin=" + origin + "&refresh=true")
    
    def parse(self, response):
        job_links = response.css('ul.jobs-search__results-list a.base-card__full-link::attr(href)').getall()
        with open(self.file_name, "a", encoding="utf-8") as f:
            for _, link in enumerate(job_links):
                f.write(link + "\n")

if __name__ == "__main__":
    if(os.path.exists("job_links.txt")):
        print("job_links.txt exists, deleting...")
        os.remove("job_links.txt")

    process = CrawlerProcess(get_project_settings())
    process.crawl(LinkedInJobSpider)
    process.start()
