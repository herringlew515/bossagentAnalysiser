from unittest.mock import Mock

import pymysql
import pytest

from app.config import Settings
from app.database import salary_midpoint, salary_midpoint_sql
from app.sql_agent import SQLAgent, UnsafeSQL, validate_sql


@pytest.fixture
def settings():
    return Settings(_env_file=None, kimi_api_key="", kimi_model="", sql_max_rows=20)


@pytest.mark.parametrize("sql", [
    "DELETE FROM jobinfo", "SELECT id FROM jobinfo; DROP TABLE jobinfo",
    "SELECT * FROM jobinfo", "SELECT hrName FROM jobinfo", "SELECT hrName AS hrName FROM jobinfo",
    "SELECT hrName AS salary FROM jobinfo", "SELECT password FROM user", "SELECT id FROM mysql.user",
    "SELECT id FROM other.jobinfo", "SELECT SLEEP(10) FROM jobinfo", "SELECT LOAD_FILE('/etc/passwd') FROM jobinfo",
    "SELECT BENCHMARK(1000,1) FROM jobinfo", "SELECT id FROM jobinfo INTO OUTFILE '/tmp/out'",
    "SELECT id FROM jobinfo FOR UPDATE", "SELECT @@version FROM jobinfo",
    "SELECT @x:=id FROM jobinfo", "SELECT id FROM jobinfo UNION SELECT id FROM user",
    "SELECT id FROM jobinfo WHERE EXISTS (SELECT 1 FROM user)",
    "SELECT COUNT(*) FROM jobinfo a JOIN jobinfo b ON a.id=b.id",
    "SELECT other.COUNT(id) FROM jobinfo",
    "SELECT id FROM jobinfo /*!50000 INTO OUTFILE '/tmp/out' */",
    "WITH x AS (SELECT id FROM jobinfo) SELECT id FROM x",
])
def test_guard_rejects_unsafe_queries(sql, settings):
    with pytest.raises(UnsafeSQL):
        validate_sql(sql, settings)


def test_limit_and_aggregates(settings):
    assert validate_sql("SELECT id, title FROM jobinfo LIMIT 9999", settings).endswith("LIMIT 20")
    assert validate_sql("SELECT COUNT(*) AS n FROM jobinfo", settings).endswith("LIMIT 20")
    assert validate_sql("SELECT address, COUNT(*) AS n FROM jobinfo GROUP BY address ORDER BY n DESC LIMIT 5", settings).endswith("LIMIT 5")
    validate_sql(f"SELECT ROUND(AVG({salary_midpoint_sql()}),2) AS avg_salary FROM jobinfo", settings)


@pytest.mark.parametrize("value,expected", [('[7000,12000]',9500),('[0,0]',0),('面议',None),('[]',None),('[12000,7000]',None),('[-1,5000]',None),('[true,1000]',None)])
def test_salary_midpoint(value, expected):
    assert salary_midpoint(value) == expected


def test_execution_error_is_repaired(settings):
    settings.kimi_api_key, settings.kimi_model = "fake", "test-model"
    db, llm = Mock(), Mock()
    db.schema.return_value = [{"name":"id","type":"int"}]
    db.query.side_effect = [pymysql.err.OperationalError(1054,"Unknown column"), [{"jobs":43}]]
    llm.chat.side_effect = ["SELECT COUNT(id) AS jobs FROM jobinfo", "SELECT COUNT(*) AS jobs FROM jobinfo"]
    result = SQLAgent(settings, db, llm).run("北京岗位有多少")
    assert result["rows"] == [{"jobs":43}]
    assert [item["status"] for item in result["attempts"]] == ["error","success"]
    assert "Unknown column" in llm.chat.call_args.args[0][-1]["content"]


def test_guard_failure_never_executes_and_retry_is_bounded(settings):
    settings.kimi_api_key, settings.kimi_model = "fake", "test-model"
    db, llm = Mock(), Mock()
    db.schema.return_value = []
    llm.chat.return_value = "DELETE FROM jobinfo"
    result = SQLAgent(settings, db, llm).run("删除所有岗位")
    assert len(result["attempts"]) == settings.sql_max_attempts
    assert result["sql"] is None
    db.query.assert_not_called()


@pytest.mark.parametrize("question", ["北京和上海 Python 岗平均薪资", "北京 Python Java 岗平均薪资", "2025年北京 Python 平均薪资", "北京公司数量", "北京本科 Python 平均薪资"])
def test_demo_does_not_ignore_unsupported_filters(question,settings):
    db = Mock()
    db.table = "`jobinfo`"
    db.query.side_effect = [[{"address":"北京"},{"address":"上海"}], [{"type":"python"},{"type":"java"}]]
    result = SQLAgent(settings,db,Mock()).demo(question)
    assert result["sql"] is None
    assert db.query.call_count == 2
