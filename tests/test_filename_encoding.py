import unittest

from modules.shared.services.database import repair_legacy_filename


class FilenameEncodingTest(unittest.TestCase):
    def test_repairs_gb18030_bytes_decoded_as_latin1(self):
        original = "附件1：上海银行单位定期存单质押授信业务操作规程（2025年版）.docx"
        broken = original.encode("gb18030").decode("latin-1")
        self.assertEqual(repair_legacy_filename(broken), original)

    def test_repairs_utf8_bytes_decoded_as_latin1(self):
        original = "中文文档.pdf"
        broken = original.encode("utf-8").decode("latin-1")
        self.assertEqual(repair_legacy_filename(broken), original)

    def test_keeps_valid_names_unchanged(self):
        for value in ("中文文档.pdf", "annual-report-2025.pdf", None, ""):
            self.assertEqual(repair_legacy_filename(value), value)


if __name__ == "__main__":
    unittest.main()
