"""CLI smoke tests via Typer's CliRunner."""

from __future__ import annotations

from typer.testing import CliRunner

from vouch.cli import app

runner = CliRunner()


def test_version():
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "vouch" in r.stdout
    assert "0.2.0" in r.stdout


def test_no_args_shows_help():
    r = runner.invoke(app, [])
    # Typer exits 0 when help is shown via no_args_is_help / our callback
    assert "search" in r.stdout.lower() or "Usage" in r.stdout


def test_profiles_list():
    r = runner.invoke(app, ["profiles", "list"])
    assert r.exit_code == 0
    assert "arxiv.org" in r.stdout


def test_profiles_show():
    r = runner.invoke(app, ["profiles", "show", "arxiv.org"])
    assert r.exit_code == 0
    assert "arxiv" in r.stdout.lower()


def test_profiles_show_unknown():
    r = runner.invoke(app, ["profiles", "show", "nonexistent.test"])
    assert r.exit_code == 1


def test_catalog_list_empty(tmp_path):
    db = tmp_path / "cat.db"
    r = runner.invoke(app, ["catalog", "list", "--db", str(db)])
    assert r.exit_code == 0
    assert "0 site(s)" in r.stdout


def test_catalog_add_then_list(tmp_path):
    db = tmp_path / "cat.db"
    r = runner.invoke(
        app,
        [
            "catalog",
            "add",
            "example.com",
            "--category",
            "test",
            "--tags",
            "a,b",
            "--db",
            str(db),
        ],
    )
    assert r.exit_code == 0
    r = runner.invoke(app, ["catalog", "list", "--db", str(db)])
    assert "example.com" in r.stdout


def test_profiles_import_to_catalog(tmp_path):
    db = tmp_path / "cat.db"
    r = runner.invoke(
        app,
        [
            "profiles",
            "import",
            "arxiv.org,github.com",
            "--db",
            str(db),
        ],
    )
    assert r.exit_code == 0
    assert "imported" in r.stdout
