from typing import Dict, List
from hdfs import InsecureClient
import os
import json

class HDFSClient:
    def __init__(self, hdfs_url: str = "http://localhost:9870", user: str = "bartsuper") -> None:
        self.client = InsecureClient(hdfs_url, user)


    def read_json(self, hdfs_path: str) -> Dict:
        with self.client.read(hdfs_path, encoding="utf-8") as reader:
            return json.load(reader)


    def write(self, hdfs_path: str, data: str, overwrite: bool = False) -> None:
        try:
            with self.client.write(hdfs_path, overwrite=overwrite) as writer:
                writer.write(data.encode("utf-8"))
            print(f"Successfully wrote data to {hdfs_path}")
        except Exception as e:
            print(f"An error occured while writing to HDFS: {str(e)}")


    def upload(self, hdfs_path: str, local_path: str) -> None:
        try:
            self.client.makedirs(os.path.dirname(hdfs_path))
            self.client.upload(hdfs_path, local_path, overwrite=True)
            print(f"Uploaded {local_path} to HDFS at {hdfs_path}")
        except Exception as e:
            print(f"An error occurred when trying to upload {local_path} to {hdfs_path}: {str(e)}")


    def download(self, hdfs_path: str, local_path: str) -> None:
        try:
            self.client.download(hdfs_path, local_path, overwrite=True)
            print(f"Downloaded {hdfs_path} to local at {local_path}")
        except Exception as e:
            print(f"An error occured when trying to download {hdfs_path} to {local_path}: {str(e)}")


    def list_dir(self, hdfs_path: str) -> List:
        try:
            return self.client.list(hdfs_path)
        except Exception as e:
            print(f"An error occured when listing {hdfs_path}: {str(e)}")
            return []


    def delete(self, hdfs_path: str, recursive: bool = False):
        try:
            self.client.delete(hdfs_path, recursive=recursive)
            print(f"Deleted {hdfs_path} from HDFS")
        except Exception as e:
            print(f"An error occured when deleting {hdfs_path}: {str(e)}")
