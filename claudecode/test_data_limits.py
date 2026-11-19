"""Prove automatiche per la correzione 6 (meno dati verso Anthropic). Solo dati finti."""

import os

import pytest

from claudecode.data_limits import (
    is_default_excluded,
    is_sensitive_path,
    limit_diff,
    read_repo_file,
    send_summary,
)


# ---- esclusioni predefinite -------------------------------------------------

@pytest.mark.parametrize("path", [
    "node_modules/x/index.js", "web/node_modules/y.js", "dist/app.js", "build/o.js",
    ".git/config", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    ".env", ".env.production", "src/.env.local", "keys/server.pem", "a/b/id.key",
    "cert.p12", "static/app.min.js", "static/app.js.map", "img/logo.png", "doc/a.pdf",
])
def test_default_excluded(path):
    assert is_default_excluded(path)


@pytest.mark.parametrize("path", [
    "src/api/orders.ts", "medusa-config.js", "src/modules/build_report.ts",
    "docs/environment.md", "src/distance.ts",
])
def test_normal_files_not_excluded(path):
    assert not is_default_excluded(path)


def test_sensitive_paths():
    assert is_sensitive_path(".env")
    assert is_sensitive_path("sub/.env.local")
    assert is_sensitive_path(".git/config")
    assert is_sensitive_path("x/server.pem")
    assert not is_sensitive_path("src/app.ts")
    assert not is_sensitive_path("package-lock.json")  # escluso dal diff, non segreto


# ---- tetto al diff ------------------------------------------------------------

def _section(name, size):
    return f"diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n" + ("+x\n" * size)


def test_diff_under_limit_is_unchanged():
    d = _section("a.ts", 3) + _section("b.ts", 3)
    text, kept, omitted = limit_diff(d, 10_000)
    assert text == d and kept == ["a.ts", "b.ts"] and omitted == []


def test_diff_over_limit_cuts_on_file_boundary_never_midfile():
    a, b, c = _section("a.ts", 10), _section("b.ts", 1000), _section("c.ts", 10)
    limit = len(a) + len(c) + 50
    text, kept, omitted = limit_diff(a + b + c, limit)
    assert len(text) <= limit
    assert "b.ts" in omitted and "a.ts" in kept
    assert text.count("diff --git") == len(kept)
    for name in kept:
        assert text.count(f"diff --git a/{name} b/{name}") == 1
    # ogni sezione tenuta è intera
    assert text.startswith(a)


def test_diff_limit_zero_or_invalid_means_default_not_unlimited():
    text, _, _ = limit_diff(_section("a.ts", 3), 0)
    assert "diff --git" in text


# ---- lettura dei file da parte del filtro ---------------------------------------

def test_read_inside_repo_ok(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("hello")
    ok, content, err, size = read_repo_file(str(tmp_path), "src/a.ts", 1000)
    assert ok and content == "hello" and size == 5 and err == ""


@pytest.mark.parametrize("bad", ["../secret.txt", "/etc/passwd", "/proc/self/environ",
                                 "src/../../secret.txt", "", "~/x"])
def test_read_outside_repo_refused(tmp_path, bad):
    (tmp_path.parent / "secret.txt").write_text("TOP SECRET")
    (tmp_path / "src").mkdir()
    ok, content, err, size = read_repo_file(str(tmp_path), bad, 1000)
    assert not ok and content == "" and size == 0 and err


def test_symlink_escaping_repo_refused(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("TOP SECRET")
    repo = tmp_path / "repo"
    repo.mkdir()
    os.symlink(outside, repo / "link.txt")
    ok, content, err, _ = read_repo_file(str(repo), "link.txt", 1000)
    assert not ok and "TOP SECRET" not in content


def test_symlink_inside_repo_ok(tmp_path):
    (tmp_path / "real.ts").write_text("ok")
    os.symlink(tmp_path / "real.ts", tmp_path / "alias.ts")
    ok, content, _, _ = read_repo_file(str(tmp_path), "alias.ts", 1000)
    assert ok and content == "ok"


def test_sensitive_files_not_read(tmp_path):
    (tmp_path / ".env").write_text("KEY=abc")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("token")
    for p in (".env", ".git/config"):
        ok, content, err, _ = read_repo_file(str(tmp_path), p, 1000)
        assert not ok and content == ""


def test_big_file_is_truncated_with_notice(tmp_path):
    (tmp_path / "big.ts").write_text("a" * 5000)
    ok, content, _, size = read_repo_file(str(tmp_path), "big.ts", 100)
    assert ok and size == 100
    assert content.startswith("a" * 100) and "troncato" in content and len(content) < 300


def test_not_a_file_and_missing(tmp_path):
    (tmp_path / "d").mkdir()
    assert not read_repo_file(str(tmp_path), "d", 100)[0]
    assert not read_repo_file(str(tmp_path), "nope.ts", 100)[0]


# ---- riepilogo -----------------------------------------------------------------

def test_send_summary_lists_names_and_sizes_not_content():
    s = send_summary(prompt_bytes=1234, diff_files=["a.ts", "b.ts"], omitted_files=["c.ts"],
                     filter_reads=[("a.ts", 10)])
    assert "a.ts" in s and "c.ts" in s and "1234" in s
    assert "SECRET" not in s
