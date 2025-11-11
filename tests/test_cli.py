from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from adoif import cli

runner = CliRunner()


def test_config_json_flag(tmp_path, monkeypatch):
    data_dir = tmp_path / "adoif-data"
    monkeypatch.setenv("ADOIF_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ADOIF_DB_FILENAME", "test.sqlite3")
    monkeypatch.setenv("ADOIF_LOG_LEVEL", "DEBUG")

    result = runner.invoke(cli.app, ["config", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert Path(payload["data_dir"]) == data_dir
    assert payload["db_filename"] == "test.sqlite3"
    assert payload["log_level"] == "DEBUG"
