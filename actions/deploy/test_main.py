import http.client
import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from main import (
    LIST_PAGE_SIZE,
    api_error_message,
    error_detail,
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


def _api_http_error(status, body):
    """The HTTPError urlopen raises for an API error response.

    `body` is written as the API's own envelope — {"error": <sentence>,
    "code": <stable id>} — so a test that reads it the wrong way round fails
    here rather than in a run log.
    """
    return urllib.error.HTTPError(
        url="https://sitepaste.com/api/v1/public/sites/default/pages",
        code=status,
        msg="",
        hdrs=http.client.HTTPMessage(),
        fp=io.BytesIO(json.dumps(body).encode()),
    )


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
        fail_on_build_error="",
    ):
        env = {
            "INPUT_API_TOKEN": token,
            "INPUT_CONTENT_DIR": content_dir,
            "INPUT_CONTENT_TYPE": content_type,
            "INPUT_SITE_ID": site_id,
            "INPUT_DRY_RUN": dry_run,
            "INPUT_PRUNE": prune,
            "INPUT_FAIL_ON_BUILD_ERROR": fail_on_build_error,
        }
        clean = {k: v for k, v in os.environ.items() if not k.startswith("INPUT_")}
        clean.update(env)
        return clean

    @staticmethod
    def _capture_payload(captured):
        def handler(req, **kw):
            captured["payload"] = json.loads(req.data)
            captured["url"] = req.full_url
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

    def test_posts_to_the_named_sites_pages_collection(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d, site_id="site_123"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertIn("/sites/site_123/pages", captured["url"])

    def test_posts_to_the_default_site_when_none_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            self.assertIn("/sites/default/pages", captured["url"])

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
            (Path(d) / "post.md").write_text("---\ntitle: X\napi_endpoint: FETCH /pages\n---\nbody")
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

    def test_names_the_offending_file_when_a_page_entry_fails_validation(self):
        # A batch keys its entry problems by index in "pages", and the whole
        # point of parsing them is the per-file annotation: without it a run
        # log says only that something was invalid, not which file.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            http_error = _api_http_error(
                422,
                {
                    "error": "validation failed",
                    "code": "validation_failed",
                    "pages": {"0": {"slug": "slug must not be empty"}},
                },
            )

            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=http_error),
                patch("sys.stdout", new_callable=io.StringIO) as out,
                self.assertRaises(SystemExit) as ctx,
            ):
                main()
            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("::error file=post.md::", out.getvalue())
            self.assertIn("slug must not be empty", out.getvalue())

    def test_reports_entry_and_envelope_problems_from_the_same_response(self):
        # They are reported independently, so a body carrying both does not
        # have half of it dropped.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            http_error = _api_http_error(
                422,
                {
                    "error": "validation failed",
                    "code": "validation_failed",
                    "pages": {"0": {"slug": "slug must not be empty"}},
                    "fields": {"deleteSlugs": "deleteSlugs array exceeds 5000 entries"},
                },
            )
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=http_error),
                patch("sys.stdout", new_callable=io.StringIO) as out,
                self.assertRaises(SystemExit),
            ):
                main()
            self.assertIn("slug must not be empty", out.getvalue())
            self.assertIn("deleteSlugs array exceeds 5000 entries", out.getvalue())

    def test_names_the_offending_envelope_field_when_the_batch_itself_fails(self):
        # A problem with the envelope's own fields has one place to point at,
        # so it comes back in "fields" rather than keyed by entry index.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            http_error = _api_http_error(
                422,
                {
                    "error": "validation failed",
                    "code": "validation_failed",
                    "fields": {"pages": "pages array exceeds 5000 entries"},
                },
            )

            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=http_error),
                patch("sys.stdout", new_callable=io.StringIO) as out,
                self.assertRaises(SystemExit) as ctx,
            ):
                main()
            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("pages array exceeds 5000 entries", out.getvalue())

    def test_exits_with_error_on_500_response(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            http_error = _api_http_error(
                500, {"error": "failed to save pages", "code": "internal_error"}
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


class TestPrune(unittest.TestCase):
    _env = staticmethod(TestMain._env)

    @staticmethod
    def _prune_api(remote_pages, calls):
        """Mock urlopen: GET /pages serves one window, POST captures its payload.

        The GET honours the `limit` and `offset` it is sent and reports the
        collection's `total`, exactly as the real list does. Serving the
        whole collection regardless would hide a client that reads only the
        first window — which is the bug this shape exists to catch.
        """

        def handler(req, **kw):
            calls.append(req)
            if req.get_method() == "GET":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(req.full_url).query)
                limit = int(query.get("limit", [str(LIST_PAGE_SIZE)])[0])
                offset = int(query.get("offset", ["0"])[0])
                return _mock_api(
                    {
                        "pages": remote_pages[offset : offset + limit],
                        "total": len(remote_pages),
                        "limit": limit,
                        "offset": offset,
                    }
                )
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

    def test_prunes_stale_pages_past_the_first_window(self):
        # The list serves at most one window per call, so a site with more
        # pages than that would keep every stale page past the first window
        # while the run still reported success.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")
            remote = [{"slug": "keep", "contentType": "docs"}]
            remote += [{"slug": f"stale-{i}", "contentType": "docs"} for i in range(LIST_PAGE_SIZE)]
            calls = []
            with (
                patch.dict(os.environ, self._env(content_dir=d, prune="true"), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api(remote, calls)),
            ):
                main()
            payload = json.loads(calls[-1].data)
            pruned = {entry["slug"] for entry in payload["deleteSlugs"]}
            self.assertIn(f"stale-{LIST_PAGE_SIZE - 1}", pruned)

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

    def test_get_names_the_site_in_the_path_and_filters_by_content_type(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.md").write_text("---\ntitle: Keep\n---\nbody")
            calls = []
            with (
                patch.dict(
                    os.environ,
                    self._env(
                        content_dir=d, content_type="standalone", site_id="site-123", prune="true"
                    ),
                    clear=True,
                ),
                patch("main.urllib.request.urlopen", side_effect=self._prune_api([], calls)),
            ):
                main()
            get_url = calls[0].full_url
            self.assertIn("contentType=standalone", get_url)
            self.assertIn("/sites/site-123/pages", get_url)

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


class TestPassthroughFields(unittest.TestCase):
    _env = staticmethod(TestMain._env)
    _capture_payload = staticmethod(TestMain._capture_payload)

    def _publish_one(self, front_matter):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text(f"---\ntitle: T\n{front_matter}\n---\nbody")
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            return captured["payload"]["pages"][0]

    def _fails_validation(self, front_matter):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text(f"---\ntitle: T\n{front_matter}\n---\nbody")
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_author_id_passes_through_as_author_id(self):
        page = self._publish_one("author: a7XkQw3mZlPwR9tGhY3nB")
        self.assertEqual(page["authorId"], "a7XkQw3mZlPwR9tGhY3nB")

    def test_author_name_fails_validation(self):
        self._fails_validation("author: Ada Lovelace")

    def test_empty_author_clears(self):
        page = self._publish_one('author: ""')
        self.assertEqual(page["authorId"], "")

    def test_password_front_matter_fails_the_run(self):
        self._fails_validation("password: supersecret123")

    def test_og_image_url_passes_through(self):
        page = self._publish_one("og_image_url: https://example.com/og.png")
        self.assertEqual(page["ogImageUrl"], "https://example.com/og.png")

    def test_og_image_url_rejects_other_schemes(self):
        self._fails_validation("og_image_url: ftp://example.com/og.png")

    def test_language_passes_through(self):
        page = self._publish_one("language: pt-BR")
        self.assertEqual(page["language"], "pt-BR")

    def test_invalid_language_fails_validation(self):
        self._fails_validation("language: not a language")

    def test_language_singleton_subtags_pass_through(self):
        # 1-char singleton/private-use subtags are valid BCP-47 and the API
        # accepts them.
        page = self._publish_one("language: de-DE-u-co-phonebk")
        self.assertEqual(page["language"], "de-DE-u-co-phonebk")

    def test_overlong_language_fails_validation(self):
        # Well-formed subtags, but past the 35-character cap.
        self._fails_validation("language: en-abcdefgh-abcdefgh-abcdefgh-abcdefgh")

    def test_theme_override_fields_pass_through(self):
        page = self._publish_one(
            "theme: minimal\nprimary_color: '#336699'\nfont_size: compact\n"
            "code_theme_light: github\ncode_theme_dark: dracula"
        )
        self.assertEqual(page["theme"], "minimal")
        self.assertEqual(page["primaryColor"], "#336699")
        self.assertEqual(page["fontSize"], "compact")
        self.assertEqual(page["codeThemeLight"], "github")
        self.assertEqual(page["codeThemeDark"], "dracula")

    def test_invalid_font_size_fails_validation(self):
        self._fails_validation("font_size: enormous")

    def test_tristate_booleans_become_tristate_strings(self):
        page = self._publish_one("show_toc: false\nshow_comments: true\nshow_tags: inherit")
        self.assertEqual(page["showToc"], "false")
        self.assertEqual(page["showComments"], "true")
        self.assertEqual(page["showTags"], "inherit")

    def test_invalid_tristate_fails_validation(self):
        self._fails_validation("show_toc: sometimes")

    def test_absent_fields_stay_absent_from_payload(self):
        page = self._publish_one("draft: true")
        for field in ("authorId", "ogImageUrl", "language", "theme", "showToc"):
            self.assertNotIn(field, page)


class TestContentTypeFrontMatter(unittest.TestCase):
    _env = staticmethod(TestMain._env)
    _capture_payload = staticmethod(TestMain._capture_payload)

    def _publish_files(self, files):
        with tempfile.TemporaryDirectory() as d:
            for rel, content in files.items():
                path = Path(d) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            captured = {}
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", side_effect=self._capture_payload(captured)),
            ):
                main()
            return captured["payload"]["pages"]

    def _fails_validation(self, files):
        with tempfile.TemporaryDirectory() as d:
            for rel, content in files.items():
                path = Path(d) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            with patch.dict(os.environ, self._env(content_dir=d), clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_show_listings_reaches_the_homepage_payload(self):
        pages = self._publish_files(
            {
                "index.md": "---\ntitle: Home\ncontentType: homepage\nshow_listings: true\n---\nx",
            }
        )
        self.assertIs(pages[0]["showListings"], True)

    def test_show_listings_false_is_sent_rather_than_dropped(self):
        # An explicit off has to reach the API: dropping it would leave the
        # homepage on whatever it was last set to.
        pages = self._publish_files(
            {
                "index.md": "---\ntitle: Home\ncontentType: homepage\nshow_listings: false\n---\nx",
            }
        )
        self.assertIs(pages[0]["showListings"], False)

    def test_show_listings_on_a_non_homepage_is_not_sent(self):
        # It only means anything on a homepage, so sending it elsewhere would
        # write a setting the page cannot use.
        pages = self._publish_files(
            {
                "guide.md": "---\ntitle: Guide\nshow_listings: true\n---\nx",
            }
        )
        self.assertNotIn("showListings", pages[0])

    def test_a_non_boolean_show_listings_fails_the_run(self):
        self._fails_validation(
            {
                "index.md": "---\ntitle: Home\ncontentType: homepage\nshow_listings: maybe\n---\nx",
            }
        )

    def test_homepage_front_matter_publishes_the_site_homepage(self):
        pages = self._publish_files(
            {
                "index.md": "---\ntitle: Docs\ncontentType: homepage\n---\nWelcome",
                "guide.md": "---\ntitle: Guide\n---\nbody",
            }
        )
        by_type = {p["contentType"]: p for p in pages}
        self.assertEqual(by_type["homepage"]["slug"], "index")
        self.assertEqual(by_type["homepage"]["title"], "Docs")
        # The rest of the directory keeps the run's content type.
        self.assertIn("docs", by_type)

    def test_homepage_in_a_subdirectory_fails(self):
        self._fails_validation(
            {
                "guides/home.md": "---\ntitle: Docs\ncontentType: homepage\n---\nWelcome",
            }
        )

    def test_two_homepages_fail(self):
        self._fails_validation(
            {
                "a.md": "---\ntitle: A\ncontentType: homepage\n---\nx",
                "b.md": "---\ntitle: B\ncontentType: homepage\n---\ny",
            }
        )

    def test_per_file_content_type_is_honored(self):
        pages = self._publish_files(
            {
                "post.md": "---\ntitle: P\ncontentType: blog\n---\nx",
                "guide.md": "---\ntitle: G\n---\ny",
            }
        )
        by_slug = {p["slug"]: p for p in pages}
        self.assertEqual(by_slug["post"]["contentType"], "blog")
        self.assertEqual(by_slug["guide"]["contentType"], "docs")

    def test_unknown_content_type_fails(self):
        self._fails_validation(
            {
                "post.md": "---\ntitle: P\ncontentType: article\n---\nx",
            }
        )


class TestErrorDetail(unittest.TestCase):
    """The API's envelope is {"error": <sentence>, "code": <stable id>}.

    `error` is the sentence to show and `code` is the identifier to branch
    on. Reading them the other way round matches nothing and silently drops
    every tailored message, so each case here sends the shape the API sends.
    """

    def test_names_the_missing_scope_and_the_remedy(self):
        detail = error_detail(
            {
                "error": 'this token does not carry the "deploy" scope',
                "code": "token_scope_required",
                "scope": "deploy",
            }
        )
        self.assertIn('"deploy" scope', detail)
        self.assertIn("Account > Tokens", detail)

    def test_does_not_guess_a_scope_the_body_did_not_name(self):
        detail = error_detail({"error": "scope missing", "code": "token_scope_required"})
        self.assertIn("Account > Tokens", detail)
        self.assertNotIn('"content"', detail)

    def test_shows_the_sentence_and_keeps_the_code_for_the_reader(self):
        detail = error_detail(
            {
                "error": "The monthly build limit for your plan has been reached.",
                "code": "quota_exceeded",
            }
        )
        self.assertIn("The monthly build limit for your plan has been reached.", detail)
        self.assertIn("quota_exceeded", detail)

    def test_shows_the_sentence_alone_when_no_code_travels_with_it(self):
        self.assertEqual(error_detail({"error": "something went wrong"}), "something went wrong")

    def test_reports_unknown_error_for_an_empty_body(self):
        self.assertEqual(error_detail({}), "unknown error")


class TestApiErrorMessage(unittest.TestCase):
    def test_prefixes_the_detail_with_the_http_status(self):
        self.assertEqual(
            api_error_message(500, {"error": "failed to save pages", "code": "internal_error"}),
            "api returned 500: failed to save pages (internal_error)",
        )


class TestBuildErrorHandling(unittest.TestCase):
    """A refused deploy leaves the pages saved and the site on its old build."""

    _env = staticmethod(TestMain._env)

    @staticmethod
    def _refused_build():
        return _mock_api(
            {
                "build": {
                    "error": "The hourly limit of 300 deploys was reached."
                    " The content was saved; trigger the deploy once the limit resets.",
                    "code": "rate_limited",
                }
            }
        )

    def test_fails_the_run_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", return_value=self._refused_build()),
                self.assertRaises(SystemExit) as ctx,
            ):
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_warns_instead_when_fail_on_build_error_is_false(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            env = self._env(content_dir=d, fail_on_build_error="false")
            with (
                patch.dict(os.environ, env, clear=True),
                patch("main.urllib.request.urlopen", return_value=self._refused_build()),
            ):
                main()  # no SystemExit

    def test_page_count_is_still_reported_when_the_deploy_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            out_file = Path(d) / "github_output.txt"
            out_file.write_text("")
            env = self._env(content_dir=d)
            env["GITHUB_OUTPUT"] = str(out_file)

            with (
                patch.dict(os.environ, env, clear=True),
                patch("main.urllib.request.urlopen", return_value=self._refused_build()),
                self.assertRaises(SystemExit),
            ):
                main()

            output = out_file.read_text()
            self.assertIn("page-count=1", output)
            self.assertNotIn("deploy-url=", output)

    def test_a_quota_refusal_also_fails_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            refused = _mock_api(
                {
                    "build": {
                        "error": "The monthly build limit for your plan has been reached.",
                        "code": "quota_exceeded",
                    }
                }
            )
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", return_value=refused),
                self.assertRaises(SystemExit) as ctx,
            ):
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_a_null_build_field_is_not_a_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", return_value=_mock_api({"build": None})),
            ):
                main()  # no SystemExit

    def test_a_token_without_the_deploy_scope_is_told_which_scope_is_missing(self):
        # The commonest way a run reaches this branch is a token minted with
        # `content` alone. The scope travels in a field of its own, so a run
        # log that does not name it leaves the reader with no remedy.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "post.md").write_text("---\ntitle: T\n---\nbody")
            refused = _mock_api(
                {
                    "build": {
                        "error": 'This token does not carry the "deploy" scope.',
                        "code": "token_scope_required",
                        "scope": "deploy",
                    }
                }
            )
            with (
                patch.dict(os.environ, self._env(content_dir=d), clear=True),
                patch("main.urllib.request.urlopen", return_value=refused),
                patch("sys.stdout", new_callable=io.StringIO) as out,
                self.assertRaises(SystemExit),
            ):
                main()
            self.assertIn('"deploy" scope', out.getvalue())


if __name__ == "__main__":
    unittest.main()
