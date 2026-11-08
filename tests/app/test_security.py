"""Path confinement for model-proposed file operations."""

import pytest

from sigmahelix.app.security import confine_to_root, read_text_file


def test_relative_path_resolves_inside_the_root(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    assert confine_to_root(root, "repo/README.md") == root / "repo" / "README.md"


def test_absolute_path_inside_the_root_is_allowed(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    target = root / "repo" / "notes.txt"
    assert confine_to_root(root, str(target)) == target


@pytest.mark.parametrize(
    "escape",
    ["../outside.txt", "/etc/passwd", "repo/../../outside.txt", ""],
)
def test_paths_that_escape_the_root_are_refused(tmp_path, escape):
    root = tmp_path / "projects"
    root.mkdir()
    with pytest.raises(ValueError):
        confine_to_root(root, escape)


def test_symlink_out_of_the_root_is_refused(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("do not read me", encoding="utf-8")
    (root / "link").symlink_to(outside)

    with pytest.raises(ValueError):
        confine_to_root(root, "link")


def test_read_text_file_refuses_oversized_and_binary_files(tmp_path):
    big = tmp_path / "big.txt"
    big.write_text("x" * 2048, encoding="utf-8")
    with pytest.raises(ValueError, match="larger than"):
        read_text_file(big, limit=1024)

    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\x00\x01\x02")
    with pytest.raises(ValueError, match="not text"):
        read_text_file(binary)

    plain = tmp_path / "ok.txt"
    plain.write_text("hello", encoding="utf-8")
    assert read_text_file(plain) == "hello"
