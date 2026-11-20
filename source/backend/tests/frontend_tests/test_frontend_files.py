# the page is served as index.html plus separate css and js files
import os
import re
import shutil
import subprocess
import sys
import unittest

import support  # noqa: F401,E402  (puts backend/ on sys.path)

from support.sqlite_db import DbTestCase  # noqa: E402

FRONTEND = os.path.join(os.path.dirname(support.BACKEND), "frontend")


def static_files(folder):
    """Every file under frontend/static/<folder>, including the feature sub-folders."""
    root = os.path.join(FRONTEND, "static", folder)
    return sorted(os.path.join(d, n) for d, _, names in os.walk(root) for n in names)


class FrontendFilesTests(DbTestCase):

    def page(self):
        return self.client.get("/").get_data(as_text=True)

    def test_page_links_every_file_and_each_one_is_served(self):
        html = self.page()
        urls = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
        self.assertGreaterEqual(len(urls), 7)
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            r.close()

    def test_every_static_script_is_linked_by_the_page(self):
        html = self.page()
        for folder, ext in (("js", ".js"), ("css", ".css")):
            for name in os.listdir(os.path.join(FRONTEND, "static", folder)):
                if name.endswith(ext):
                    self.assertIn(f"/static/{folder}/{name}", html, name)

    def test_content_types(self):
        css = self.client.get("/static/css/styles.css")
        js = self.client.get("/static/js/core/core.js")
        self.assertIn("text/css", css.content_type)
        self.assertIn("javascript", js.content_type)
        css.close()
        js.close()

    def test_google_client_id_is_still_filled_in_by_the_server(self):
        from config import Config
        self.assertIn(f"window.GOOGLE_CLIENT_ID = '{Config.GOOGLE_CLIENT_ID}'", self.page())

    def test_page_has_no_inline_style_block_or_big_script(self):
        html = self.page()
        self.assertNotIn("<style>", html)
        inline = re.findall(r"<script>(.*?)</script>", html, flags=re.S)
        self.assertTrue(all(len(s) < 300 for s in inline))

    def test_static_files_are_not_templates(self):
        for path in static_files("css") + static_files("js"):
            with open(path, encoding="utf-8") as f:
                self.assertNotIn("{{", f.read(), path)

    def test_files_outside_static_are_not_reachable(self):
        for url in ("/static/../app.py", "/static/%2e%2e/app.py", "/static/js/missing.js"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 404, url)
            r.close()

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_scripts_have_valid_syntax(self):
        for path in static_files("js"):
            done = subprocess.run(["node", "--check", path], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{path}: {done.stderr}")
