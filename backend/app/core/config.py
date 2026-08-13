import configparser
import logging
import secrets
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
logger = logging.getLogger("job_hunter")


class Config:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        config_path: Path | None = None,
        db_path: Path | None = None,
    ):
        self.repo_root = repo_root
        self.config_path = config_path or repo_root / "data" / "config.ini"
        self.db_path = db_path or repo_root / "data" / "job_hunter.db"
        self._ensure()

    def _ensure(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            p = configparser.ConfigParser()
            p["auth"] = {
                "username": "admin",
                "password": secrets.token_urlsafe(12),
                "jwt_secret": secrets.token_urlsafe(32),
            }
            p["scraper"] = {"max_pages": "50", "headful": "false", "use_system_chrome": "false"}
            p["site"] = {"secret": secrets.token_hex(32)}
            with open(self.config_path, "w", encoding="utf-8") as f:
                p.write(f)
            logger.warning(
                "已生成 %s，初始密码：%s（可修改文件后重启生效）",
                self.config_path, p["auth"]["password"],
            )
        self._parser = configparser.ConfigParser()
        self._parser.read(self.config_path, encoding="utf-8")
        # 旧配置文件缺少 [site] 段时补写，幂等
        if "site" not in self._parser:
            self._parser["site"] = {"secret": secrets.token_hex(32)}
            with open(self.config_path, "w", encoding="utf-8") as f:
                self._parser.write(f)
        # 旧配置文件 [scraper] 缺少 use_system_chrome 键时补写，幂等
        if "scraper" in self._parser and "use_system_chrome" not in self._parser["scraper"]:
            self._parser["scraper"]["use_system_chrome"] = "false"
            with open(self.config_path, "w", encoding="utf-8") as f:
                self._parser.write(f)

    @property
    def auth_username(self) -> str:
        return self._parser["auth"]["username"]

    @property
    def auth_password(self) -> str:
        return self._parser["auth"]["password"]

    @property
    def jwt_secret(self) -> str:
        return self._parser["auth"]["jwt_secret"]

    @property
    def max_pages(self) -> int:
        return int(self._parser["scraper"]["max_pages"])

    @property
    def headful(self) -> bool:
        return self._parser.getboolean("scraper", "headful")

    @property
    def use_system_chrome(self) -> bool:
        """是否用本机已安装的 Chrome（channel=chrome）替代内置 Chromium 启动浏览器。"""
        try:
            return self._parser.getboolean("scraper", "use_system_chrome", fallback=False)
        except Exception:
            return False

    @property
    def site_secret_key(self) -> bytes:
        return bytes.fromhex(self._parser["site"]["secret"])

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def log_dir(self) -> Path:
        return self.repo_root / "logs"
