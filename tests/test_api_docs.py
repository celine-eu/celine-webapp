"""The interactive API docs and the schema are mounted only in development.

`celine.sdk.posture.docs_urls`, on the same signal as the posture guard
(`settings.posture_env`): in dev the three paths are served; anywhere else they are
not mounted unless `CELINE_PUBLIC_DOCS=true`. The guard itself is stubbed here — it
is `tests/test_posture.py`'s subject, and outside dev it would refuse the suite's
development defaults.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from celine.webapp import main as main_module
from celine.webapp.settings import settings

PATHS = ("/api/docs", "/api/redoc", "/api/openapi.json")


class _NoGuard:
    def enforce(self) -> None:
        pass


def _client(monkeypatch, env: str, public: str | None = None) -> TestClient:
    monkeypatch.setattr(settings, "celine_env", env)
    monkeypatch.setattr(settings, "environment", "")
    monkeypatch.setattr(main_module, "posture_guard", lambda _s: _NoGuard())
    if public is None:
        monkeypatch.delenv("CELINE_PUBLIC_DOCS", raising=False)
    else:
        monkeypatch.setenv("CELINE_PUBLIC_DOCS", public)
    # No `with`: the lifespan opens the database and is not under test here.
    return TestClient(main_module.create_app())


@pytest.mark.parametrize("env", ["", "staging", "prod"])
def test_outside_dev_the_docs_are_not_mounted(monkeypatch, env):
    client = _client(monkeypatch, env)

    assert [client.get(p).status_code for p in PATHS] == [404, 404, 404]


@pytest.mark.parametrize("public", ["", "false", "0"])
def test_only_a_true_opt_in_serves_them_outside_dev(monkeypatch, public):
    client = _client(monkeypatch, "staging", public)

    assert [client.get(p).status_code for p in PATHS] == [404, 404, 404]


def test_the_public_docs_opt_in_serves_them_outside_dev(monkeypatch):
    client = _client(monkeypatch, "staging", "true")

    assert [client.get(p).status_code for p in PATHS] == [200, 200, 200]


def test_dev_serves_the_docs(monkeypatch):
    client = _client(monkeypatch, "dev")

    assert [client.get(p).status_code for p in PATHS] == [200, 200, 200]
    schema = client.get("/api/openapi.json").json()
    assert schema["info"]["title"] == "CELINE Webapp API"
