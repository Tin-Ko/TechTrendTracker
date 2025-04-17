from pyspark.sql import SparkSession
from pyspark.sql.functions import count, col, explode


class JobSkillAnalyzer:
    def __init__(self, job_skills_path: str) -> None:
        self.spark = SparkSession.builder.appName("SkillAnalysis").config("spark.hadoop.fs.defaultFS", "hdfs://localhost:9000").getOrCreate()
        self.job_skills_path = job_skills_path
        self.df = self._load_data()


    def _load_data(self) -> None:
        return self.spark.read.json(self.job_skills_path)


    def get_top_skills(self, top_n: int = 5) -> list:
        top_n_skills = self.df.select(explode(col("job_skills")).alias("skill")).groupBy("skill").count().orderBy("count", ascending=False).limit(top_n)
        # top_n_skills = self.df.groupBy("job_skills").agg(count("job_skills").alias("job_skills_count")).orderBy(col("job_skills_count").desc()).limit(top_n)
        # top_n_skills = skills_df.groupBy("job_skills").count().orderBy("count", ascending=False).limit(top_n)

        return top_n_skills


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
    analyzer = JobSkillAnalyzer("hdfs:///skills/2025-04-17/*.json")
    top_skills_df = analyzer.get_top_skills(30)
    top_skills_df.show()
    # analyzer.df.show(5)
