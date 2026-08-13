import pytest
from sqlalchemy import create_engine, inspect

from backend.app.core.database import Base
from backend.app.models import SiteCredential


def test_site_credential_table_and_unique_index():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    idx = {i["name"] for i in inspect(eng).get_indexes("site_credentials")}
    assert "uq_site_credentials_site_username" in idx
    assert "ix_site_credentials_site" in idx
    with eng.begin() as conn:
        conn.execute(SiteCredential.__table__.insert().values(
            site="51job", username="13800000000", password_enc="abc",
        ))
        with pytest.raises(Exception):
            conn.execute(SiteCredential.__table__.insert().values(
                site="51job", username="13800000000", password_enc="def",
            ))
