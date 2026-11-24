from io import BytesIO
import unittest
from zipfile import ZipFile
from aegis.distribution import build, verify, safe_path

COMMIT = "a"*40


class Distribution(unittest.TestCase):
    def test_reproducible_order(self):
        files = {"a.py":b"x=1\n","folder/b.txt":b"abc"}
        a = build(files,COMMIT)
        self.assertEqual(a,build(dict(reversed(list(files.items()))),COMMIT))
        self.assertEqual(verify(a,files,COMMIT),files)

    def test_mismatched_source_and_commit(self):
        files = {"a.txt":b"a"}
        archive = build(files,COMMIT)
        for expected,commit in (({"a.txt":b"b"},COMMIT),(files,"b"*40)):
            with self.assertRaises(ValueError):
                verify(archive,expected,commit)

    def test_unsafe_paths(self):
        for name in ("../a","/a","a/../b","a\\b","a//b","distribution-manifest.json",""):
            self.assertFalse(safe_path(name))
            with self.assertRaises(ValueError):
                build({name:b"x"},COMMIT)

    def test_extra_member_rejected(self):
        files = {"a.txt":b"a"}
        stream = BytesIO(build(files,COMMIT))
        with ZipFile(stream,"a") as z:
            z.writestr("unexpected.txt",b"x")
        with self.assertRaises(ValueError):
            verify(stream.getvalue(),files,COMMIT)
