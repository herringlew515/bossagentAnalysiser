import argparse
import json

from app.config import get_settings
from app.database import Database
from app.embeddings import Embedder
from app.llm import KimiClient
from app.rag import RagService


def main():
    parser = argparse.ArgumentParser(description="就业分析助手管理命令")
    parser.add_argument("command", choices=["build-index", "check-db"])
    args = parser.parse_args()
    settings = get_settings()
    database = Database(settings)
    if args.command == "check-db":
        result = {"schema": database.schema(), "overview": database.overview()}
    else:
        rag = RagService(settings, Embedder(settings), KimiClient(settings))
        result = rag.build(database.jobs())
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
