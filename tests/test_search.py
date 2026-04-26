import pytest

from recipes.search import sanitize_fts_query


def test_single_word():
    assert sanitize_fts_query("chicken") == '"chicken"'


def test_multi_word():
    assert sanitize_fts_query("chicken soup") == '"chicken" "soup"'


def test_strips_special_chars():
    # Double quotes are FTS5 special chars — the sanitizer strips them before re-quoting tokens
    result = sanitize_fts_query('chicken "AND" soup')
    # All three tokens should appear as quoted literals
    assert '"chicken"' in result
    assert '"AND"' in result
    assert '"soup"' in result
    # No raw (unescaped) double quotes outside of our token wrapping
    # Each token is individually quoted — no nested quotes inside tokens
    tokens = result.split()
    for token in tokens:
        assert token.startswith('"') and token.endswith('"')


def test_empty_string():
    assert sanitize_fts_query("") == '""'


def test_whitespace_only():
    assert sanitize_fts_query("   ") == '""'
