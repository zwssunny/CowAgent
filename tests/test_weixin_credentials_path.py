"""Per-instance isolation of the Weixin credentials (token) file.

A single Weixin channel keeps its legacy credentials path byte-for-byte; when
several instances run in one process each must get its own file so their tokens
do not overwrite one another.
"""

import os

import config
from config import get_weixin_credentials_path


def _reset_conf(monkeypatch, **overrides):
    base = {"weixin_credentials_path": ""}
    base.update(overrides)
    monkeypatch.setattr(config, "conf", lambda: base)


def test_single_instance_keeps_legacy_path(monkeypatch):
    monkeypatch.delenv("COW_DATA_DIR", raising=False)
    _reset_conf(monkeypatch)
    assert get_weixin_credentials_path() == os.path.expanduser(
        "~/.weixin_cow_credentials.json"
    )


def test_instance_id_isolates_the_file(monkeypatch):
    monkeypatch.delenv("COW_DATA_DIR", raising=False)
    _reset_conf(monkeypatch)
    path = get_weixin_credentials_path("weixin-abc123")
    assert path == os.path.expanduser(
        "~/.weixin_cow_credentials.weixin-abc123.json"
    )
    # Two instances never resolve to the same file.
    assert path != get_weixin_credentials_path("weixin-def456")


def test_explicit_configured_path_is_suffixed_per_instance(monkeypatch, tmp_path):
    configured = str(tmp_path / "creds.json")
    _reset_conf(monkeypatch, weixin_credentials_path=configured)
    assert get_weixin_credentials_path() == configured
    assert get_weixin_credentials_path("weixin-xyz") == str(
        tmp_path / "creds.weixin-xyz.json"
    )
