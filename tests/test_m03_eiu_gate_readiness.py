import unittest

from modules.m03_generation.services.pipeline import _is_generation_ready


class M03EiuGateReadinessTests(unittest.TestCase):
    def test_batch_generation_consumes_only_green_eiu(self) -> None:
        self.assertTrue(_is_generation_ready({"auto_disposition": "green", "is_questionable": True}))
        self.assertFalse(_is_generation_ready({"auto_disposition": "yellow", "is_questionable": True}))
        self.assertFalse(_is_generation_ready({"auto_disposition": "red", "is_questionable": False}))

    def test_manual_override_requires_explicit_single_case_path(self) -> None:
        yellow = {"auto_disposition": "yellow", "is_questionable": True, "manual_include": True}
        self.assertFalse(_is_generation_ready(yellow))
        self.assertTrue(_is_generation_ready(yellow, allow_manual_override=True))
