from unittest.mock import Mock

import numpy as np
import pytest

from app.config import Settings
from app.embeddings import Embedder
from app.rag import RagService, clean_tags, semantic_chunks
from app.router import IntentRouter


def jobs():
    return [dict(id=i, title=title, type=kind, companyTitle=f"企业{i}", companyNature="软件",
                 address="北京", dist="海淀", educational="本科", workExperience="1-3年", workTag=tags,
                 salary="[10000,20000]", salaryMonth="0", companyTags="无", companyStatus="未融资")
            for i,title,kind,tags in [(1,"Python 后端开发","python",'["Python","Django","FastAPI"]'),
                                    (2,"Java 工程师","java",'["Java","Spring"]'),
                                    (3,"前端开发","web",'["Vue","JavaScript"]'),
                                    (4,"Python 数据分析","python",'["Python","Pandas","SQL"]'),
                                    (5,"C++ 开发","C++",'["C++","Linux"]'),
                                    (6,"PHP 开发","PHP",'["PHP","Laravel"]')]]


def test_build_reload_and_retrieve(tmp_path):
    cfg = Settings(_env_file=None, index_dir=tmp_path, embedding_provider="hash", kimi_api_key="", kimi_model="")
    rag = RagService(cfg, Embedder(cfg), Mock())
    rag.build(jobs())
    result = rag.retrieve("Python Django FastAPI")
    assert result[0]["job_id"] == 1
    assert 1 <= len(result) <= 5
    assert len({row["job_id"] for row in result}) == len(result)
    assert len(rag.retrieve("北京 岗位 公司 软件")) == 5
    loaded = RagService(cfg, Embedder(cfg), Mock())
    assert loaded.load()
    assert loaded.retrieve("Python Django FastAPI") == result
    cfg.embedding_dimensions = 512
    with pytest.raises(RuntimeError, match="配置已变更"):
        RagService(cfg, Embedder(cfg), Mock()).load()


def test_semantic_breakpoints():
    embedder = Mock()
    embedder.encode.return_value = np.array([[1,0],[1,0],[0,1],[0,1]], dtype=np.float32)
    result = semantic_chunks("甲"*30+"。"+"乙"*30+"。"+"丙"*30+"。"+"丁"*30+"。",embedder,max_chars=100)
    assert len(result) == 2
    assert all(len(chunk)<=100 for chunk in result)
    assert "乙" in result[0] and "丙" in result[1]


def test_decode_double_escaped_tags():
    assert clean_tags('["Python", "\\\\u5f00\\\\u53d1", ""]') == "Python、开发"


@pytest.mark.parametrize("question,route", [("北京 Python 岗平均薪资","sql"),("招聘岗位的城市分布","sql"),("Java 岗位有哪些学历要求？","rag"),("Python 开发需要哪些技能？","rag")])
def test_router(question,route):
    cfg = Settings(_env_file=None, kimi_api_key="", kimi_model="")
    assert IntentRouter(cfg,Mock()).route(question)[0] == route
