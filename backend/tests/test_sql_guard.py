"""The AI assistant's SQL validator: what it must accept and what it must block."""

from __future__ import annotations

import pytest

from app.sql_guard import UnsafeSQLError, prepare_select

ACCEPTED = [
    "SELECT * FROM students",
    "select * from public.students;",
    "WITH t AS (SELECT * FROM students) SELECT * FROM t",
    "SELECT c.name, COUNT(a.id) AS n FROM courses c LEFT JOIN allocations a "
    "ON a.course_id = c.id GROUP BY c.name ORDER BY n DESC LIMIT 5",
    "SELECT ROUND(AVG(marks)::numeric, 2) AS avg_marks FROM students",
    "SELECT s.name FROM students s WHERE NOT EXISTS "
    "(SELECT 1 FROM allocations a WHERE a.student_id = s.id)",
    "SELECT name FROM students WHERE name ILIKE '%rao%' AND marks BETWEEN 50 AND 90",
    "SELECT cat.code, STRING_AGG(s.name, ', ') FROM categories cat "
    "JOIN students s ON s.category_id = cat.id GROUP BY cat.code",
    "SELECT name, RANK() OVER (ORDER BY marks DESC) AS r FROM students",
    "SELECT COUNT(*) FILTER (WHERE preference_rank = 1) FROM allocations",
    "SELECT EXTRACT(MONTH FROM application_date) AS m, COUNT(*) FROM students GROUP BY 1",
    "SELECT CASE WHEN marks >= 90 THEN 'A' ELSE 'B' END AS band, COUNT(*) FROM students GROUP BY 1",
    "SELECT c.name, c.total_seats - COALESCE(SUM(q.reserved_seats), 0) AS open_seats "
    "FROM courses c LEFT JOIN course_quotas q ON q.course_id = c.id GROUP BY c.id, c.name",
    "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY marks) FROM students",
    "SELECT 1 AS x UNION ALL SELECT 2",
]

REJECTED = {
    # writes & DDL
    "DELETE FROM students": "only SELECT",
    "UPDATE students SET marks = 100": "only SELECT",
    "INSERT INTO students (name) VALUES ('x')": "only SELECT",
    "DROP TABLE students": "only SELECT",
    "TRUNCATE students": "only SELECT",
    "ALTER TABLE students ADD COLUMN x int": "only SELECT",
    "WITH d AS (DELETE FROM students RETURNING *) SELECT * FROM d": "DELETE",
    "SELECT * INTO backup FROM students": "INTO",
    "SELECT * FROM students FOR UPDATE": "locking",
    "EXPLAIN ANALYZE SELECT 1": "only SELECT",
    # stacked statements
    "SELECT 1; DROP TABLE students": "one statement",
    "SELECT * FROM students; UPDATE students SET marks = 0": "one statement",
    # catalog / out-of-scope tables
    "SELECT * FROM users": "table 'users'",
    "SELECT * FROM pg_shadow": "table 'pg_shadow'",
    "SELECT * FROM pg_catalog.pg_user": "schema 'pg_catalog'",
    "SELECT table_name FROM information_schema.tables": "schema 'information_schema'",
    "SELECT * FROM (SELECT * FROM pg_user) x": "table 'pg_user'",
    "WITH pg_user AS (SELECT 1) SELECT * FROM pg_catalog.pg_user": "schema 'pg_catalog'",
    "SELECT * FROM generate_series(1, 3)": "table-valued",
    # dangerous functions (pass a keyword blocklist, blocked by the allowlist)
    "SELECT pg_read_file('/etc/passwd')": "pg_read_file",
    "SELECT pg_sleep(10)": "pg_sleep",
    "SELECT 1 WHERE EXISTS (SELECT pg_sleep(1))": "pg_sleep",
    "SELECT set_config('role', 'postgres', true)": "set_config",
    "SELECT current_setting('is_superuser')": "current_setting",
    "SELECT query_to_xml('delete from students', true, true, '')": "query_to_xml",
    "SELECT dblink('host=evil', 'select 1')": "dblink",
    "SELECT lo_import('/etc/passwd')": "lo_import",
    "SELECT version()": "not allowed",
    # junk
    "": "empty",
    "   ": "empty",
    "this is not sql": "only SELECT",
    "SELECT (((": "parse",
}


@pytest.mark.parametrize("sql", ACCEPTED)
def test_accepts_read_only_analytics(sql):
    assert prepare_select(sql)


@pytest.mark.parametrize("sql,reason", REJECTED.items())
def test_rejects_unsafe_sql(sql, reason):
    with pytest.raises(UnsafeSQLError) as excinfo:
        prepare_select(sql)
    assert reason.lower() in str(excinfo.value).lower()


def test_output_is_regenerated_from_the_ast():
    # Comments and formatting are normalised away; what runs is what was validated.
    out = prepare_select("SELECT name -- sneaky\nFROM students /* x */")
    assert "--" not in out
    assert out.startswith("SELECT name")


def test_transpiles_postgres_casts_for_sqlite():
    out = prepare_select("SELECT ROUND(AVG(marks)::numeric, 2) FROM students", target="sqlite")
    assert "::" not in out and "CAST(" in out
