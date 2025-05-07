from pyspark.sql import SparkSession
from pyspark.sql.functions import count, col, explode, lit
from datetime import date
import os
import psycopg


class JobSkillAnalyzer:
    def __init__(self, job_title, job_skills_path: str, db_params: dict) -> None:
        self.job_title = job_title
        self.spark = SparkSession.builder.appName("SkillAnalysis").config("spark.hadoop.fs.defaultFS", "hdfs://localhost:9000").getOrCreate()
        self.job_skills_path = job_skills_path
        self.df = self._load_data()
        self.df = self.df.withColumn("job_title", lit("software engineer"))
        self.conn = psycopg.connect(
            dbname=db_params['dbname'],
            user=db_params['user'],
            password=db_params['password'],
            host=db_params['host'],
            port=db_params['port'],
        )

        self.cursor = self.conn.cursor()


    def _load_data(self) -> None:
        try:
            return self.spark.read.json(self.job_skills_path)
        except Exception as e:
            print(f"Error loading data from {self.job_skills_path}: {e}")
            raise e

    def get_all_skills(self) -> list:
        all_skills = self.df.select(explode("job_skills").alias("skill")).groupBy("skill").count().orderBy("count", ascending=False)
        all_skills_list = all_skills.rdd.map(lambda row: row.asDict()).collect()
        return all_skills_list
    
    def get_percentage(self, skill_count: int) -> float:
        total_jobs = self.df.count()
        percentage = (float(skill_count) / float(total_jobs)) * 100
        return percentage

    def save_to_postgres(self) -> None:
        try:
            all_skills = self.get_all_skills()
            job_count = self.df.count()

            self.cursor.execute(
                "INSERT INTO job_count (job_title, job_count) VALUES (%s, %s);", 
                (self.job_title, job_count)
            )

            insert_query = """
                    INSERT INTO job_skill_stats (job_title, skill, count, percentage)
                    VALUES (%s, %s, %s, %s);
            """
            data_to_insert = [
                (self.job_title, skill["skill"], skill["count"], self.get_percentage(skill["count"]))
                for skill in all_skills
            ]

            self.cursor.executemany(insert_query, data_to_insert)

            print(f"Saved {len(all_skills)} skills")
            
            self.conn.commit()
            self.cursor.close()
            self.conn.close()
            print("Successfully saved to postgres database")
        except Exception as e:
            print(f"Error saving to postgresql database: {e}")
            raise(e)



    def stop(self) -> None:
        self.spark.stop()


    def test_spark(self) -> None:
        try:
            df = self.spark.createDataFrame([
                ("Alice", 29),
                ("Bob", 35),
                ("Charlie", 23)
            ], ["name", "age"])

            df.show()
            print("SparkSession is working!")
        except Exception as e:
            print("SparkSession test failed:", str(e))


if __name__ == "__main__":
    db_params = {
        "dbname": "skillsDB",
        "user": "bartsuper",
        "password": "abcd1234",
        "host": "localhost",
        "port": "5432"
    }
    today_date = date.today()
    skills_path = os.path.join("hdfs:///skills", "software_engineer", "2025-05-01", "*.json")
    analyzer = JobSkillAnalyzer(job_title="software engineer", job_skills_path=skills_path, db_params=db_params)
    analyzer.save_to_postgres()
