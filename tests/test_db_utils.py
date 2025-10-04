from utils import db


def test_get_db_path_defaults_to_data_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = db.get_db_path()
    expected = tmp_path / "data" / "medilacra.duckdb"
    assert path == str(expected)
    assert expected.parent.exists()


def test_get_db_path_honors_env_override(tmp_path, monkeypatch):
    override = tmp_path / "custom" / "file.duckdb"
    monkeypatch.setenv("MEDILACRA_DB_PATH", str(override))
    path = db.get_db_path()
    assert path == str(override.resolve())
    assert override.parent.exists()


def test_writer_and_reader_round_trip(tmp_path):
    db_path = tmp_path / "medilacra.duckdb"
    with db.writer(str(db_path)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS demo (id INTEGER)")
        con.execute("INSERT INTO demo VALUES (42)")

    with db.reader(db_path=str(db_path)) as con:
        result = con.execute("SELECT id FROM demo").fetchall()

    assert result == [(42,)]