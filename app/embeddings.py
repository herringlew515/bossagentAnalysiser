import hashlib
import re
import threading
from typing import List

import httpx
import jieba
import numpy as np

from app.config import ROOT, Settings

jieba.setLogLevel(30)


def tokenize(text: str) -> List[str]:
    return [word for word in jieba.lcut(text.lower()) if re.search(r"[\w\u4e00-\u9fff]", word)]


class Embedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._model_lock = threading.Lock()

    @property
    def fingerprint(self):
        cfg = self.settings
        return {"provider": cfg.embedding_provider, "model": cfg.embedding_model,
                "dimensions": cfg.embedding_dimensions, "base_url": cfg.embedding_base_url, "version": 1}

    def encode(self, texts: List[str]) -> np.ndarray:
        cfg = self.settings
        if not texts:
            raise ValueError("Embedding 输入不能为空")
        if cfg.embedding_provider == "hash":
            vectors = np.zeros((len(texts), cfg.embedding_dimensions), dtype=np.float32)
            for row, text in enumerate(texts):
                for token in tokenize(text):
                    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                    position = int.from_bytes(digest[:4], "little") % cfg.embedding_dimensions
                    vectors[row, position] += 1 if digest[4] % 2 else -1
        elif cfg.embedding_provider == "sentence_transformers":
            with self._model_lock:
                if self._model is None:
                    try:
                        import torch
                        from sentence_transformers import SentenceTransformer
                    except ImportError as exc:
                        raise RuntimeError('语义模型依赖未安装，请运行 pip install -e ".[semantic]"。') from exc
                    torch.set_num_threads(cfg.embedding_cpu_threads)
                    model_path = ROOT / cfg.embedding_model
                    model_id = str(model_path) if model_path.is_dir() else cfg.embedding_model
                    self._model = SentenceTransformer(model_id, cache_folder=str(ROOT / "data/models/cache"))
            vectors = np.asarray(self._model.encode(texts, batch_size=cfg.embedding_batch_size,
                                                   show_progress_bar=False), dtype=np.float32)
        else:
            if not cfg.embedding_base_url or not cfg.embedding_api_key:
                raise RuntimeError("请配置独立的 EMBEDDING_BASE_URL 和 EMBEDDING_API_KEY。")
            batches = []
            try:
                with httpx.Client(timeout=90) as client:
                    for offset in range(0, len(texts), cfg.embedding_batch_size):
                        batch = texts[offset:offset + cfg.embedding_batch_size]
                        response = client.post(cfg.embedding_base_url.rstrip("/") + "/embeddings",
                            headers={"Authorization": f"Bearer {cfg.embedding_api_key}"},
                            json={"model": cfg.embedding_model, "input": batch})
                        response.raise_for_status()
                        data = sorted(response.json()["data"], key=lambda item: item["index"])
                        if [item["index"] for item in data] != list(range(len(batch))):
                            raise ValueError("Embedding 数量或顺序异常")
                        batches.extend(item["embedding"] for item in data)
                vectors = np.asarray(batches, dtype=np.float32)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise RuntimeError("Embedding 服务调用失败，请检查配置和网络。") from exc
        if vectors.ndim != 2 or vectors.shape[0] != len(texts) or not np.isfinite(vectors).all():
            raise RuntimeError("Embedding 返回了无效向量")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return np.ascontiguousarray(vectors / np.maximum(norms, 1e-12), dtype=np.float32)
