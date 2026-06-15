# Tech Trend Tracker
Tech Trend Tracker (TTT) is a skill tracking platform that gathers data directly from job posting websites such as LinkedIn, Indeed and Glassdoor.
It helps job seekers, mainly students and entry-level applicant to identify most in-demend tech skills in the current job market.

## How to use TTT
- Typed in the job position you are looking for in the search bar and hit enter or click on the arrow button on the right.
- After submitting job position, TTT will display a bar chart that demonstrates the most in-demand skill regarding the job position.

## Deployment instructions
Since the file were too large to being put onto github, please follow the following instruction to make sure you can follow the data pipeline
### Dependencies
- Python: 3.12
    - pyspark: 3.5.5
    - scrapy: 2.12.0
    - ollama: 0.4.8
- Hadoop: 3.4.1
- Java 11
- Docker 27.5.1
    - PostgreSQL: 16 (install using Docker)
    - rabbitmq
- Go: 1.24.2

### Scrape data
#### Start a HDFS for row job description
```
start-dfs.sh
```

#### Startup Docker (rabbitMQ and postgres)
```
sudo docker compose up -d
```

#### Scrape the links for desired job position
```
python3 -m data_pipeline.scraper.linkedin
```

#### Start LLM processor and job description scraper at the same time (make sure to start llm processor first)
```
python3 -m data_pipeline.llm_processor.processor
python3 -m data_pipeline.data_pipeline.linkedin_scraper
```

#### Stop rabbitMQ (Optional)
```
sudo docker compose down rabbitmq
```

#### Start Go backend
```
cd backend
go run .
```

#### Go to website
The website should be at localhost:8080
