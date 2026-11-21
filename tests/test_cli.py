from __future__ import annotations

import json

from metricview_lint.cli import main

SQL = """\
-- comment line
CREATE OR REPLACE VIEW main.shop.kpis
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: main.shop.orders
measures:
  - name: revenue
    expr: amount
$$;
"""


def test_sql_file_lines_map_to_the_file(tmp_path, capsys):
    f = tmp_path / "kpis.sql"
    f.write_text(SQL)
    assert main([str(f)]) == 1
    out = capsys.readouterr().out
    assert f"{f}:10: error MV302" in out


def test_directory_and_json(tmp_path, capsys):
    (tmp_path / "ok.yaml").write_text(
        "version: 1.1\nsource: t\nmeasures:\n  - {name: n, expr: COUNT(1)}\n"
    )
    (tmp_path / "ignored.txt").write_text("not yaml: [")
    assert main([str(tmp_path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_warnings_as_errors(tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text("version: 1.1\nsource: t\nmeasures:\n  - expr: COUNT(1)\n")
    assert main([str(f)]) == 0
    assert main([str(f), "--warnings-as-errors"]) == 1


def test_github_format(tmp_path, capsys):
    f = tmp_path / "e.yaml"
    f.write_text("version: 1.1\nsource: t\nmeasures:\n  - {name: n, expr: x}\n")
    main([str(f), "--format", "github"])
    assert capsys.readouterr().out.startswith(f"::error file={f},line=4,title=MV302::")


def test_list_rules(capsys):
    assert main(["--list-rules"]) == 0
    assert "MV302" in capsys.readouterr().out


def test_unrelated_yaml_is_skipped(tmp_path, capsys):
    (tmp_path / "ci.yml").write_text("on: push\njobs:\n  build: {runs-on: ubuntu-latest}\n")
    assert main([str(tmp_path)]) == 0
    assert main([str(tmp_path), "--all-yaml"]) == 1
