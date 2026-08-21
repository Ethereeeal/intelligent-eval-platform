from __future__ import annotations

import unittest

from modules.m02_eiu_coverage.schemas import EiuUpdate
from modules.m02_eiu_coverage.services.llm_client import LLMClient


class M02HardeningTests(unittest.TestCase):
    def test_llm_json_accepts_object_wrappers(self) -> None:
        self.assertEqual(
            LLMClient._repair_json('{"items": [{"statement": "x"}]}'),
            [{"statement": "x"}],
        )
        self.assertEqual(
            LLMClient._repair_json('[{"statement": "x"}]'),
            [{"statement": "x"}],
        )

    def test_constraints_size_is_limited(self) -> None:
        with self.assertRaises(ValueError):
            EiuUpdate(constraints={"value": "x" * (16 * 1024)})
