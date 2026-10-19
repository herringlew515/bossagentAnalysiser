import json
from contextlib import contextmanager
from typing import Optional

import pymysql

from app.config import Settings

# 招聘分析仅使用岗位和公司字段，不向模型提供 HR 姓名、账户等信息。
PUBLIC_COLUMNS = (
    "id", "title", "address", "type", "educational", "workExperience", "workTag",
    "salary", "salaryMonth", "companyTags", "pratice", "companyTitle",
    "companyNature", "companyStatus", "companyPeople", "createTime", "dist",
)


def salary_midpoint_sql() -> str:
    # 只有合法的非负双端点 JSON 区间参与统计，单位：元/月，不计额外发薪月份。
    lo = "JSON_UNQUOTE(JSON_EXTRACT(salary, '$[0]'))"
    hi = "JSON_UNQUOTE(JSON_EXTRACT(salary, '$[1]'))"
    return (
        "CASE WHEN JSON_VALID(salary) THEN CASE WHEN JSON_TYPE(salary) = 'ARRAY' "
        "AND JSON_LENGTH(salary) = 2 "
        f"AND {lo} REGEXP '^[0-9]+([.][0-9]+)?$' "
        f"AND {hi} REGEXP '^[0-9]+([.][0-9]+)?$' "
        f"AND CAST({hi} AS DECIMAL(12,2)) >= CAST({lo} AS DECIMAL(12,2)) "
        f"THEN (CAST({lo} AS DECIMAL(12,2)) + CAST({hi} AS DECIMAL(12,2))) / 2 "
        "ELSE NULL END ELSE NULL END"
    )


def salary_midpoint(value: str) -> Optional[float]:
    try:
        values = json.loads(value)
        if not isinstance(values, list) or len(values) != 2 or any(isinstance(v, bool) for v in values):
            return None
        low, high = map(float, values)
        if not (0 <= low <= high < 100000000):
            return None
        return (low + high) / 2
    except (ValueError, TypeError):
        return None


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.table = f"`{settings.mysql_table}`"

    @contextmanager
    def connection(self):
        cfg = self.settings
        conn = pymysql.connect(
            host=cfg.mysql_host, port=cfg.mysql_port, user=cfg.mysql_user,
            password=cfg.mysql_password, database=cfg.mysql_database,
            charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5, read_timeout=cfg.sql_timeout_ms // 1000 + 5,
            write_timeout=5, autocommit=False,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SET SESSION MAX_EXECUTION_TIME = {cfg.sql_timeout_ms}")
                cursor.execute("START TRANSACTION READ ONLY")
            yield conn
        finally:
            conn.rollback()
            conn.close()

    def query(self, sql: str, params=None, limit=None):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchmany(limit) if limit is not None else cursor.fetchall()

    def schema(self):
        rows = self.query(f"SHOW COLUMNS FROM {self.table}")
        return [{"name": r["Field"], "type": r["Type"]} for r in rows if r["Field"] in PUBLIC_COLUMNS]

    def jobs(self):
        names = ", ".join(f"`{c}`" for c in PUBLIC_COLUMNS)
        return self.query(f"SELECT {names} FROM {self.table} ORDER BY id")

    def overview(self):
        mid = salary_midpoint_sql()
        totals = self.query(
            f"SELECT COUNT(*) AS jobs, COUNT(DISTINCT address) AS cities, "
            f"COUNT(DISTINCT companyTitle) AS companies, ROUND(AVG({mid}),0) AS avg_salary, "
            f"COUNT({mid}) AS salary_samples, MIN(createTime) AS first_date, MAX(createTime) AS last_date FROM {self.table}"
        )[0]
        cities = self.query(f"SELECT address AS name, COUNT(*) AS count FROM {self.table} GROUP BY address ORDER BY count DESC LIMIT 6")
        categories = self.query(f"SELECT type AS name, COUNT(*) AS count FROM {self.table} GROUP BY type ORDER BY count DESC LIMIT 6")
        return {**totals, "top_cities": cities, "top_categories": categories}
