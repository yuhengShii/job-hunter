import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 阻止 main.py 模块级 app=create_app() 在测试 import 时创建真实 data/config.ini
os.environ["JOB_HUNTER_TESTING"] = "1"

from backend.app.core.config import Config  # noqa: E402


@pytest.fixture()
def config(tmp_path):
    return Config(
        repo_root=tmp_path,
        config_path=tmp_path / "config.ini",
        db_path=tmp_path / "test.db",
    )
