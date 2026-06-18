import json
import pathlib
from typing import Dict, List


class LocalStorageClient:
    """Local-disk replacement for HDFSClient. Mirrors the subset of the
    HDFSClient interface (write/read_json/list/delete) that the ingest path
    actually uses."""

    def __init__(self, base_dir: str = "/job_postings") -> None:
        self.base = pathlib.Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> pathlib.Path:
        p = pathlib.Path(path)
        return p if p.is_absolute() else self.base / p

    def write(self, filename: str, data, overwrite: bool = True) -> str:
        path = self._resolve(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise FileExistsError(path)
        if isinstance(data, (dict, list)):
            payload = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            payload = str(data)
        path.write_text(payload, encoding="utf-8")
        return str(path.resolve())

    def read_json(self, path: str) -> Dict:
        return json.loads(self._resolve(path).read_text(encoding="utf-8"))

    def list(self) -> List[str]:
        return [str(p) for p in self.base.glob("*.json")]

    def delete(self, path: str) -> None:
        self._resolve(path).unlink(missing_ok=True)
