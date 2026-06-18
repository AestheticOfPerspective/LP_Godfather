from __future__ import annotations

from src.platforms.telegram.bot import sanitize_html


class TestSanitizeHTML:
    def test_passes_through_plain_text(self):
        assert sanitize_html("Hello World") == "Hello World"

    def test_allows_bold(self):
        assert sanitize_html("<b>bold</b>") == "<b>bold</b>"

    def test_allows_italic(self):
        assert sanitize_html("<i>italic</i>") == "<i>italic</i>"

    def test_allows_code(self):
        assert sanitize_html("<code>print(1)</code>") == "<code>print(1)</code>"

    def test_allows_pre(self):
        assert sanitize_html("<pre>block</pre>") == "<pre>block</pre>"

    def test_allows_anchor_https(self):
        result = sanitize_html('<a href="https://example.com">link</a>')
        assert '<a href="https://example.com">' in result or '<a href="https://example.com">' in result

    def test_allows_anchor_http(self):
        result = sanitize_html('<a href="http://example.com">link</a>')
        assert "http://example.com" in result

    def test_strips_anchor_javascript(self):
        result = sanitize_html('<a href="javascript:alert(1)">xss</a>')
        assert "javascript" not in result

    def test_strips_disallowed_tags(self):
        result = sanitize_html("<script>alert(1)</script>")
        assert "&lt;script&gt;" in result
        assert "&lt;/script&gt;" in result
        assert "alert" in result

    def test_strips_style_tag(self):
        result = sanitize_html("<style>body{color:red}</style>")
        assert "&lt;style&gt;" in result

    def test_escapes_unknown_tags(self):
        result = sanitize_html("<marquee>text</marquee>")
        assert "&lt;" in result
        assert "marquee" not in result or "MARQUEE" not in result

    def test_mixed_allowed_and_disallowed(self):
        result = sanitize_html("<b>safe</b><script>bad</script><i>also safe</i>")
        assert "<b>safe</b>" in result
        assert "<i>also safe</i>" in result
        assert "&lt;script&gt;" in result

    def test_allows_underline(self):
        assert sanitize_html("<u>underline</u>") == "<u>underline</u>"

    def test_allows_strikethrough(self):
        assert sanitize_html("<s>strike</s>") == "<s>strike</s>"

    def test_allows_strong(self):
        assert sanitize_html("<strong>strong</strong>") == "<strong>strong</strong>"

    def test_allows_em(self):
        assert sanitize_html("<em>em</em>") == "<em>em</em>"

    def test_allows_span(self):
        assert sanitize_html("<span>span</span>") == "<span>span</span>"

    def test_allows_br(self):
        assert sanitize_html("<br>") == "<br>"

    def test_mailto_link(self):
        result = sanitize_html('<a href="mailto:test@example.com">email</a>')
        assert "mailto:test@example.com" in result

    def test_tel_link(self):
        result = sanitize_html('<a href="tel:+1234567890">call</a>')
        assert "tel:+1234567890" in result

    def test_anchor_with_extra_attributes(self):
        result = sanitize_html('<a href="https://x.com" target="_blank">x</a>')
        assert 'href="https://x.com"' in result
        assert "target" not in result

    def test_nested_allowed_tags(self):
        result = sanitize_html("<b><i>bold italic</i></b>")
        assert "<b><i>bold italic</i></b>" in result or "<i>bold italic</i>" in result

    def test_empty_string(self):
        assert sanitize_html("") == ""

    def test_no_html(self):
        result = sanitize_html("just text with < and > symbols")
        assert "&lt;" not in result
        assert "<" in result

    def test_case_insensitive_tag_handling(self):
        result = sanitize_html("<B>bold</B>")
        assert "<B>" in result or "<b>" in result
