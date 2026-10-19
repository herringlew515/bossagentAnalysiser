from unittest.mock import Mock

from fastapi.testclient import TestClient

from app import main


def test_auth_and_input_validation(monkeypatch):
    monkeypatch.setattr(main.settings,"service_api_key","test-secret")
    client = TestClient(main.app)
    assert client.get("/").status_code == 200
    assert client.post("/api/chat",json={"question":"你好"}).status_code == 401
    headers={"X-API-Key":"test-secret"}
    assert client.post("/api/chat",json={"question":"  "},headers=headers).status_code == 422
    assert client.post("/api/chat",json={"question":"你好","mode":"wrong"},headers=headers).status_code == 422


def test_sql_endpoint_reports_actual_result(monkeypatch):
    monkeypatch.setattr(main.settings,"service_api_key","")
    agent = Mock()
    agent.run.return_value = {"answer":"查询完成","sql":"SELECT COUNT(*) FROM jobinfo","rows":[{"jobs":43}],"columns":["jobs"],"attempts":[{"attempt":1,"status":"success"}]}
    monkeypatch.setattr(main,"agent",agent)
    response = TestClient(main.app).post("/api/chat",json={"question":"北京 Python 平均薪资"})
    assert response.status_code == 200
    assert response.json()["route"] == "sql"
    assert response.json()["rows"] == [{"jobs":43}]
