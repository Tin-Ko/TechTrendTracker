from typing import List
from hdfs import InsecureClient
import os

class HDFSClient:
    def __init__(self, hdfs_url: str = "http://localhost:9870", user: str = "bartsuper") -> None:
        self.client = InsecureClient(hdfs_url, user)

    def upload(self, hdfs_path: str, local_path: str) -> None:
        try:
            self.client.makedirs(os.path.dirname(hdfs_path))
            self.client.upload(hdfs_path, local_path, overwrite=True)
            print(f"Uploaded {local_path} to HDFS at {hdfs_path}")
        except Exception as e:
            print(f"An error occurred: {str(e)}")

    def download(self, hdfs_path: str, local_path: str) -> None:
        self.client.download(hdfs_path, local_path, overwrite=True)
        print(f"Downloaded {hdfs_path} to local at {local_path}")

    def list_dir(self, hdfs_path: str) -> List:
        return self.client.list(hdfs_path)

    def delete(self, hdfs_path: str, recursive: bool = False):
        self.client.delete(hdfs_path, recursive=recursive)
        print(f"Deleted {hdfs_path} from HDFS")
