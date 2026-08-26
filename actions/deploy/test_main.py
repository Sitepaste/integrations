import http.client
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from main import (
    get_input,
    main,
    normalize_section,
    parse_front_matter,
    set_output,
    slugify,
    titleize,
    walk_md,
)


def _mock_api(response_data):
    return io.BytesIO(json.dumps(response_data).encode())


class TestParseFrontMatter(unittest.TestCase):
    def test_extracts_attrs_and_separates_body(self):
        attrs, body = parse_front_matter("---\ntitle: Hello\n---\nBody text")
        self.assertEqual(attrs["title"], "Hello")
        self.assertEqual(body, "Body text")

    def test_returns_raw_text_when_no_fences(self):
        raw = "Just a body"
        attrs, body = parse_front_matter(raw)
        self.assertEqual(attrs, {})
        self.assertEqual(body, raw)

    def test_parses_true_as_boolean(self):
        attrs, _ = parse_front_matter("---\ndraft: true\n---\n")
        self.assertIs(attrs["draft"], True)

    def test_parses_false_as_boolean(self):
        attrs, _ = parse_front_matter("---\ndraft: false\n---\n")
        self.assertIs(attrs["draft"], False)

    def test_parses_inline_array(self):
        attrs, _ = parse_front_matter("---\ntags: [one, two, three]\n---\n")
        self.assertEqual(attrs["tags"], ["one", "two", "three"])

    def test_parses_empty_array(self):
        attrs, _ = parse_front_matter("---\ntags: []\n---\n")
        self.assertEqual(attrs["tags"], [])

    def test_strips_quotes_from_array_items(self):
        attrs, _ = parse_front_matter("---\ntags: [\"one\", 'two']\n---\n")
        self.assertEqual(attrs["tags"], ["one", "two"])

    def test_strips_quotes_from_scalar_values(self):
        attrs, _ = parse_front_matter('---\ntitle: "My Title"\n---\n')
        self.assertEqual(attrs["title"], "My Title")

    def test_handles_windows_line_endings(self):
        attrs, body = parse_front_matter("---\r\ntitle: Hello\r\n---\r\nBody")
        self.assertEqual(attrs["title"], "Hello")
        self.assertEqual(body, "Body")

    def test_returns_raw_when_closing_fence_missing(self):
        raw = "---\ntitle: Hello\nno closing fence"
        attrs, body = parse_front_matter(raw)
        self.assertEqual(attrs, {})
        self.assertEqual(body, raw)

    def test_skips_lines_without_colon_separator(self):
        attrs, _ = parse_front_matter("---\ntitle: Hello\nmalformed\nslug: test\n---\n")
        self.assertEqual(attrs["title"], "Hello")
        self.assertEqual(attrs["slug"], "test")
        self.assertEqual(len(attrs), 2)

    def test_ignores_front_matter_beyond_30_lines(self):
        lines = ["---"] + [f"key{i}: val{i}" for i in range(30)] + ["---", "body"]
        attrs, _ = parse_front_matter("\n".join(lines))
        self.assertEqual(attrs, {})

    def test_preserves_newlines_in_body(self):
        _, body = parse_front_matter("---\ntitle: T\n---\nline1\nline2\nline3")
        self.assertEqual(body, "line1\nline2\nline3")


class TestSlugify(unittest.TestCase):
    def test_lowercases_and_strips_extension(self):
        self.assertEqual(slugify("Hello-World.md"), "hello-world")

    def test_removes_apostrophes(self):
        self.assertEqual(slugify("it's-fine.md"), "its-fine")

    def test_replaces_special_chars_with_hyphens(self):
        self.assertEqual(slugify("hello world!.md"), "hello-world")

    def test_collapses_consecutive_hyphens(self):
        self.assertEqual(slugify("a---b.md"), "a-b")

    def test_uses_filename_ignoring_directory(self):
        self.assertEqual(slugify("guides/getting-started.md"), "getting-started")

    def test_strips_leading_and_trailing_hyphens(self):
        self.assertEqual(slugify("-hello-.md"), "hello")

    def test_truncates_long_slugs(self):
        result = slugify(("a" * 150) + ".md")
        self.assertLessEqual(len(result), 100)

    def test_trims_trailing_hyphen_after_truncation(self):
        name = "a" * 99 + " b.md"
        result = slugify(name)
        self.assertLessEqual(len(result), 100)
        self.assertFalse(result.endswith("-"))


class TestNormalizeSection(unittest.TestCase):
    def test_keeps_a_single_slash_for_nesting(self):
        self.assertEqual(normalize_section("api/builds"), "api/builds")

    def test_normalizes_each_segment(self):
        self.assertEqual(normalize_section("API/Post Builds"), "api/post-builds")

    def test_drops_empty_segments(self):
        self.assertEqual(normalize_section("/api"), "api")
        self.assertEqual(normalize_section("api/"), "api")
        self.assertEqual(normalize_section("api//builds"), "api/builds")

    def test_flat_sections_are_unchanged(self):
        self.assertEqual(normalize_section("guides"), "guides")

    def test_keep_case_preserves_typed_casing(self):
        # The server lowercases this into the slug and captures the casing
        # as the section's display title.
        self.assertEqual(normalize_section("API/Builds", keep_case=True), "API/Builds")
        self.assertEqual(normalize_section("API v2", keep_case=True), "API-v2")


class TestTitleize(unittest.TestCase):
    def test_capitalizes_hyphen_separated_words(self):
        self.assertEqual(titleize("hello-world"), "Hello World")

    def test_handles_empty_string(self):
        self.assertEqual(titleize(""), "")


class TestGetInput(unittest.TestCase):
    def test_converts_hyphens_to_underscores_in_key(self):
        with patch.dict(os.environ, {"INPUT_CONTENT_DIR": "docs"}):
            self.assertEqual(get_input("content-dir"), "docs")

    def test_strips_whitespace(self):
        with patch.dict(os.environ, {"INPUT_API_TOKEN": "  secret  "}):
            self.assertEqual(get_input("api-token"), "secret")

    def test_returns_empty_for_unset_input(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("INPUT_")}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(get_input("anything"), "")


class TestSetOutput(unittest.TestCase):
    def test_appends_key_value_lines_to_github_output_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            tmp = f.name
        try:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": tmp}):
                set_output("a", 1)
                set_output("b", 2)
            self.assertEqual(Path(tmp).read_text(), "a=1\nb=2\n")
        finally:
            Path(tmp).unlink()

    def test_no_error_when_github_output_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
        with patch.dict(os.environ, env, clear=True):
            set_output("x", 1)


class TestWalkMd(unittest.TestCase):
    def test_finds_markdown_files_recursively(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.md").write_text("a")
            (Path(d) / "b.txt").write_text("b")
            (Path(d) / "sub").mkdir()
            (Path(d) / "sub" / "c.md").write_text("c")
            rels = [r for _, r in walk_md(d)]
            self.assertIn("a.md", rels)
            self.assertIn(str(Path("sub") / "c.md"), rels)
            self.assertNotIn("b.txt", rels)

    def test_skips_hidden_directories(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".hidden").mkdir()
            (Path(d) / ".hidden" / "secret.md").write_text("x")
            (Path(d) / "visible.md").write_text("y")
            rels = [r for _, r in walk_md(d)]
            self.assertEqual(rels, ["visible.md"])

    def test_returns_empty_for_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(walk_md(d), [])

    def test_raises_for_nonexistent_directory(self):
        with self.assertRaises(OSError):
            walk_md("/nonexistent/path")


class TestMain(unittest.TestCase):
    @staticmethod
    def _env(
        token="tok_test",
        content_dir="content",
        content_type="docs",
        site_id="",
        dry_run="false",
        prune="false",
    ):
        env = {
            "INPUT_API_TOKEN": token,
            "INPUT_CONTENT_DIR": content_dir,
            "INPUT_CONTENT_TYPE": content_type,
            "INPUT_SITE_ID": site_id,
            "INPUT_DRY_RUN": dry_run,
            "INPUT_PRUNE": prune,
        }
        clean = {k: v for k, v in os.environ.items() if not k.startswith("INPUT_")}
        clean.update(env)
        return clean

    @staticmethod
    def _capture_payload(captured):
        def handler(req, **kw):
            captured["payload"] = json.loads(req.data)
            return _mock_api({"build": {}})

        return handler

    def test_fails_without_api_token(self):
        with patch.dict(os.environ, self._env(token=""), clear=True):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_fails_with_invalid_content_type(self):
        with patch.dict(os.environ, self._env(content_type="invalid"), clear=True):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_defaults_content_type_to_docs(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d, content_type=""), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["contentType"], "docs")

    def test_fails_for_nonexistent_content_directory(self):
        with patch.dict(os.environ, self._env(content_dir="/nonexistent"), clear=True):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_warns_for_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            captured = io.StringIO()
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("sys.stdout", captured),
            ):
                main()
            self.assertIn("No markdown files found", captured.getvalue())

    def test_duplicate_slugs_fail_validation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.md").write_text("---\nslug: same\n---\nA")
            (Path(d) / "b.md").write_text("---\nslug: same\n---\nB")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_oversized_content_fails_validation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "big.md").write_text(f"---\ntitle: Big\n---\n{'x' * 100_001}")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_slug_exceeding_100_chars_fails_validation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.md").write_text(f"---\nslug: {'a' * 101}\n---\nbody")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_exceeding_5000_page_limit_fails(self):
        with tempfile.TemporaryDirectory() as d:
            real_file = Path(d) / "page.md"
            real_file.write_text("---\ntitle: T\n---\nbody")
            fake_files = [(real_file, f"{i}.md") for i in range(5001)]
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.walk_md", return_value=fake_files),
                self.assertRaises(SystemExit) as ctx,
            ):
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_warns_about_relative_image_references(self):
        with tempfile.TemporaryDirectory() as d:
            md = "---\ntitle: T\n---\n![photo](images/cat.jpg)\n![ok](https://x.com/dog.jpg)"
            (Path(d) / "post.md").write_text(md)
            captured_stdout = io.StringIO()
            with (
                patch.dict(os.environ, self._env(content_dir=d, dry_run="true"), clear=True),
                patch("sys.stdout", captured_stdout),
            ):
                main()
            output = captured_stdout.getvalue()
            self.assertIn("images/cat.jpg", output)
            self.assertNotIn("dog.jpg", output)

    def test_dry_run_makes_no_api_call(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: Hello\n---\nBody")
            with patch.dict(os.environ, self._env(content_dir=d, dry_run="true"), clear=True):
                main()

    def test_appends_midnight_utc_to_date_only_published_at(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\npublishedAt: 2024-06-15\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["publishedAt"], "2024-06-15T00:00:00Z")

    def test_reads_date_field_as_published_at_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ndate: 2024-06-15\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["publishedAt"], "2024-06-15T00:00:00Z")

    def test_published_at_takes_precedence_over_date(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text(
                "---\npublishedAt: 2024-07-01T12:00:00Z\ndate: 2024-06-15\n---\nbody"
            )
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["publishedAt"], "2024-07-01T12:00:00Z")

    def test_passes_full_datetime_published_at_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            ts = "2024-06-15T14:30:00Z"
            (Path(d) / "post.md").write_text(f"---\npublishedAt: {ts}\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["publishedAt"], ts)

    def test_directory_becomes_section(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "guides").mkdir()
            (Path(d) / "guides" / "setup.md").write_text("---\ntitle: Setup\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["section"], "guides")

    def test_standalone_nested_directory_becomes_nested_section(self):
        # A second directory level maps to a nested standalone section
        # ("api/builds"), the same depth docs/blog reach via their
        # content-type prefix.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "api" / "builds").mkdir(parents=True)
            (Path(d) / "api" / "builds" / "post-builds.md").write_text(
                "---\ntitle: POST /builds\n---\nbody"
            )
            captured = {}
            with (
                patch.dict(
                    os.environ,
                    self._env(content_dir=d, content_type="standalone"),
                    clear=True,
                ),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["section"], "api/builds")

    def test_docs_nested_directory_keeps_top_level_section_with_warning(self):
        # Docs and blog spend their nesting level on the content-type prefix,
        # so a second directory level is ignored, not mapped.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "guides" / "advanced").mkdir(parents=True)
            (Path(d) / "guides" / "advanced" / "setup.md").write_text(
                "---\ntitle: Setup\n---\nbody"
            )
            captured = {}
            stdout = io.StringIO()
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
                patch("sys.stdout", stdout),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["section"], "guides")
            self.assertIn("::warning", stdout.getvalue())

    def test_standalone_third_directory_level_is_ignored_with_warning(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "api" / "builds" / "deep").mkdir(parents=True)
            (Path(d) / "api" / "builds" / "deep" / "x.md").write_text("---\ntitle: X\n---\nbody")
            captured = {}
            stdout = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    self._env(content_dir=d, content_type="standalone"),
                    clear=True,
                ),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
                patch("sys.stdout", stdout),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["section"], "api/builds")
            self.assertIn("::warning", stdout.getvalue())

    def test_directory_casing_is_preserved_in_payload(self):
        # A directory named API/ should label the section "API", not the
        # titleized "Api" — the server captures typed casing from the section
        # value, so the action must not lowercase it away.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "API" / "Builds").mkdir(parents=True)
            (Path(d) / "API" / "Builds" / "post-builds.md").write_text(
                "---\ntitle: POST /builds\n---\nbody"
            )
            captured = {}
            with (
                patch.dict(
                    os.environ,
                    self._env(content_dir=d, content_type="standalone"),
                    clear=True,
                ),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["section"], "API/Builds")

    def test_front_matter_section_may_nest_for_standalone(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.md").write_text("---\ntitle: X\nsection: api/builds\n---\nbody")
            captured = {}
            with (
                patch.dict(
                    os.environ,
                    self._env(content_dir=d, content_type="standalone"),
                    clear=True,
                ),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["section"], "api/builds")

    def test_front_matter_nested_section_fails_for_docs(self):
        # Caught locally so the run fails with the file named, instead of a
        # server-side validation error.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.md").write_text("---\ntitle: X\nsection: guides/advanced\n---\nbody")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_front_matter_section_deeper_than_two_levels_fails_for_standalone(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.md").write_text("---\ntitle: X\nsection: a/b/c\n---\nbody")
            with patch.dict(
                os.environ,
                self._env(content_dir=d, content_type="standalone"),
                clear=True,
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_includes_site_id_in_payload_when_provided(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d, site_id="site_123"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["siteId"], "site_123")

    def test_wraps_scalar_tag_in_list(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntags: python\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["tags"], ["python"])

    def test_maps_frontmatter_fields_to_page_payload(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text(
                "---\ntitle: My Post\nslug: my-post\ndescription: A post\n"
                "draft: false\ntags: [python, test]\n---\nContent here"
            )
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            page = captured["payload"]["pages"][0]
            self.assertEqual(page["slug"], "my-post")
            self.assertEqual(page["title"], "My Post")
            self.assertEqual(page["content"], "Content here")
            self.assertEqual(page["contentType"], "docs")
            self.assertEqual(page["description"], "A post")
            self.assertIs(page["draft"], False)
            self.assertEqual(page["tags"], ["python", "test"])

    def test_maps_api_endpoint_to_page_payload(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text(
                "---\ntitle: List pages\napi_endpoint: GET /pages\n---\nbody"
            )
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["apiEndpoint"], "GET /pages")

    def test_rejects_api_endpoint_without_http_method(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text(
                "---\ntitle: X\napi_endpoint: FETCH /pages\n---\nbody"
            )
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_sets_outputs_on_successful_deploy(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            out_file = Path(d) / "github_output.txt"
            out_file.write_text("")
            env = self._env(content_dir=d)
            env["GITHUB_OUTPUT"] = str(out_file)

            with (
                patch.dict(os.environ, env, clear=True),
                patch(
                    "main.urllib.request.urlopen",
                    return_value=_mock_api(
                        {"build": {"deployUrl": "https://example.sitepaste.com"}}
                    ),
                ),
            ):
                main()

            output = out_file.read_text()
            self.assertIn("page-count=1", output)
            self.assertIn("deploy-url=https://example.sitepaste.com", output)

    def test_exits_with_field_errors_on_400_response(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            error_body = json.dumps({"pages": {"0": {"slug": "invalid slug"}}}).encode()
            http_error = urllib.error.HTTPError(
                url="https://sitepaste.com/api/v1/public/pages",
                code=400,
                msg="Bad Request",
                hdrs=http.client.HTTPMessage(),
                fp=io.BytesIO(error_body),
            )

            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=http_error),
                self.assertRaises(SystemExit) as ctx,
            ):
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_exits_with_error_on_500_response(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            error_body = json.dumps({"error": "internal server error"}).encode()
            http_error = urllib.error.HTTPError(
                url="https://sitepaste.com/api/v1/public/pages",
                code=500,
                msg="Internal Server Error",
                hdrs=http.client.HTTPMessage(),
                fp=io.BytesIO(error_body),
            )

            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=http_error),
                self.assertRaises(SystemExit) as ctx,
            ):
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_fails_on_request_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=TimeoutError()),
                self.assertRaises(SystemExit) as ctx,
            ):
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_invalid_slug_format_fails_validation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\nslug: Hello World\n---\nbody")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_too_many_tags_fails_validation(self):
        with tempfile.TemporaryDirectory() as d:
            tags = ", ".join(f"tag{i}" for i in range(21))
            (Path(d) / "post.md").write_text(f"---\ntags: [{tags}]\n---\nbody")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_invalid_tag_characters_fails_validation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntags: [C++]\n---\nbody")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_invalid_published_at_fails_validation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\npublishedAt: not-a-date\n---\nbody")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_tag_casing_is_preserved_in_payload(self):
        # Typed casing reaches the server, which stores the lowercase slug
        # and captures the casing as the tag's display title — writing "iOS"
        # must display as iOS, not "ios". Validation still runs on the
        # lowercase form, so invalid characters are caught either way.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntags: [iOS, python]\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertEqual(captured["payload"]["pages"][0]["tags"], ["iOS", "python"])

    def test_invalid_tag_characters_fail_regardless_of_case(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntags: [C++]\n---\nbody")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_build_warning_does_not_fail_action(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch(
                    "main.urllib.request.urlopen",
                    return_value=_mock_api(
                        {"build": {"error": "quota_exceeded", "message": "Build limit reached"}}
                    ),
                ),
            ):
                main()


class TestPrune(unittest.TestCase):
    _env = staticmethod(TestMain._env)

    @staticmethod
    def _prune_api(remote_pages, calls):
        """Mock urlopen: GET /pages returns remote_pages, POST captures its payload."""

        def handler(req, **kw):
            calls.append(req)
            if req.get_method() == "GET":
                return _mock_api({"pages": remote_pages})
            return _mock_api({"build": {}, "deleted": ["stale"]})

        return handler

    def test_prunes_remote_pages_missing_locally(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")
            remote = [
                {"slug": "keep", "contentType": "docs"},
                {"slug": "stale", "contentType": "docs"},
                {"slug": "stale-sectioned", "contentType": "docs", "section": "guides"},
            ]
            calls = []
            with (
                patch.dict(os.environ, self._env(content_dir=d, prune="true"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api(remote, calls)),
            ):
                main()
            payload = json.loads(calls[-1].data)
            self.assertEqual(
                payload["deleteSlugs"],
                [
                    {"slug": "stale", "contentType": "docs"},
                    {"slug": "stale-sectioned", "contentType": "docs", "section": "guides"},
                ],
            )

    def test_matches_by_section_and_slug(self):
        # A local page in section "guides" must not protect a sectionless
        # remote page with the same slug, and vice versa.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "guides").mkdir()
            (Path(d) / "guides" / "setup.md").write_text("---\ntitle: Setup\n---\nbody")
            remote = [
                {"slug": "setup", "contentType": "docs"},
                {"slug": "setup", "contentType": "docs", "section": "guides"},
            ]
            calls = []
            with (
                patch.dict(os.environ, self._env(content_dir=d, prune="true"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api(remote, calls)),
            ):
                main()
            payload = json.loads(calls[-1].data)
            self.assertEqual(payload["deleteSlugs"], [{"slug": "setup", "contentType": "docs"}])

    def test_matches_sections_case_insensitively(self):
        # The API returns lowercase section slugs; a cased local directory
        # (Guides/) must still protect its remote page from pruning.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Guides").mkdir()
            (Path(d) / "Guides" / "setup.md").write_text("---\ntitle: Setup\n---\nbody")
            remote = [{"slug": "setup", "contentType": "docs", "section": "guides"}]
            calls = []
            with (
                patch.dict(os.environ, self._env(content_dir=d, prune="true"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api(remote, calls)),
            ):
                main()
            payload = json.loads(calls[-1].data)
            self.assertNotIn("deleteSlugs", payload)

    def test_ignores_remote_pages_of_other_content_types(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")
            remote = [{"slug": "a-blog-post", "contentType": "blog"}]
            calls = []
            with (
                patch.dict(os.environ, self._env(content_dir=d, prune="true"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api(remote, calls)),
            ):
                main()
            payload = json.loads(calls[-1].data)
            self.assertNotIn("deleteSlugs", payload)

    def test_omits_delete_slugs_when_nothing_to_prune(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")
            remote = [{"slug": "keep", "contentType": "docs"}]
            calls = []
            with (
                patch.dict(os.environ, self._env(content_dir=d, prune="true"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api(remote, calls)),
            ):
                main()
            payload = json.loads(calls[-1].data)
            self.assertNotIn("deleteSlugs", payload)

    def test_dry_run_lists_prunes_but_only_calls_get(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")
            remote = [{"slug": "stale", "contentType": "docs"}]
            calls = []
            with (
                patch.dict(
                    os.environ,
                    self._env(content_dir=d, prune="true", dry_run="true"),
                    clear=True,
                ),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api(remote, calls)),
            ):
                main()
            self.assertEqual([req.get_method() for req in calls], ["GET"])

    def test_no_get_request_when_prune_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")
            calls = []
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api([], calls)),
            ):
                main()
            self.assertEqual([req.get_method() for req in calls], ["POST"])

    def test_get_includes_content_type_and_site_id(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")
            calls = []
            with (
                patch.dict(
                    os.environ,
                    self._env(content_dir=d, content_type="standalone", site_id="site-123", prune="true"),
                    clear=True,
                ),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api([], calls)),
            ):
                main()
            get_url = calls[0].full_url
            self.assertIn("contentType=standalone", get_url)
            self.assertIn("siteId=site-123", get_url)

    def test_dies_when_listing_remote_pages_fails(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")

            def handler(req, **kw):
                raise urllib.error.HTTPError(
                    req.full_url, 401, "Unauthorized", {}, _mock_api({"error": "invalid token"})
                )

            with (
                patch.dict(os.environ, self._env(content_dir=d, prune="true"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=handler),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
