import configparser

from backend.app.core.config import Config


def test_config_creates_file_with_random_secrets(tmp_path):
    cfg = Config(repo_root=tmp_path, config_path=tmp_path / "config.ini", db_path=tmp_path / "test.db")
    assert cfg.config_path.exists()
    parser = configparser.ConfigParser()
    parser.read(cfg.config_path, encoding="utf-8")
    assert parser["auth"]["username"] == "admin"
    assert len(parser["auth"]["password"]) >= 12
    assert len(parser["auth"]["jwt_secret"]) >= 32
    assert cfg.auth_username == "admin"
    assert cfg.database_url == f"sqlite:///{tmp_path / 'test.db'}"


def test_config_reuse_existing_file(tmp_path):
    path = tmp_path / "config.ini"
    p = configparser.ConfigParser()
    p["auth"] = {"username": "me", "password": "pw123", "jwt_secret": "s" * 40}
    p["scraper"] = {"max_pages": "30", "headful": "false"}
    with open(path, "w", encoding="utf-8") as f:
        p.write(f)
    cfg = Config(repo_root=tmp_path, config_path=path, db_path=tmp_path / "t.db")
    assert cfg.auth_username == "me"
    assert cfg.max_pages == 30
    assert cfg.headful is False
