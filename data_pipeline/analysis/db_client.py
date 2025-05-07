import psycopg


class DatabaseClient:
    def __init__(self, dbname: str, user: str, password: str, host:str, port: str) -> None:
        self.conn = psycopg.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )

        self.cursor = self.conn.cursor()

    def save_top_skills
