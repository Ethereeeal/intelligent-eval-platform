import unittest

from modules.m05_dataset_lifecycle.services.lifecycle import DatasetLifecycleService
from modules.m05_dataset_lifecycle.services.public_set import import_public_set
from modules.m05_dataset_lifecycle.services.uploaded_set import import_uploaded_set


class _LifecycleDatabase:
    def __init__(self, status="frozen"):
        self.status = status
        self.updated = False
        self.jobs = []

    def get_eval_case(self, case_id):
        return {"case_id": case_id, "version_id": 1}

    def get_dataset_version(self, version_id):
        return {"version_id": version_id, "status": self.status}

    def update_eval_case(self, *args, **kwargs):
        self.updated = True

    def retire_eval_case(self, case_id):
        self.updated = True

    def update_job(self, *args, **kwargs):
        self.jobs.append((args, kwargs))


class _UploadedSetDatabase:
    def create_uploaded_set_with_cases(self, **kwargs):
        self.payload = kwargs
        return {"set_id": 1, "quality": kwargs["quality_snapshot"], "total_cases": len(kwargs["cases"])}


class _PublicSetDatabase:
    def save_public_set(self, **kwargs):
        self.set_kwargs = kwargs
        return 1

    def save_public_cases(self, **kwargs):
        self.cases = kwargs["cases"]

    def update_public_set(self, *args, **kwargs):
        self.quality = kwargs["quality_snapshot"]


class _TreeDatabase:
    def list_generated_cases(self):
        return [{"case_id": 1, "eiu_id": 10, "review_status": "quality_verified"}]

    def list_eius(self, include_blocked=False):
        return [
            {"eiu_id": 10, "section_path": "第一章", "document_name": "a.pdf", "is_questionable": True},
            {"eiu_id": 11, "section_path": "第一章", "document_name": "a.pdf", "is_questionable": True},
        ]

    def get_eiu(self, eiu_id):
        return next(item for item in self.list_eius() if item["eiu_id"] == eiu_id)


class M05DemoHardeningTests(unittest.TestCase):
    def test_frozen_versions_are_read_only(self):
        service = DatasetLifecycleService(_LifecycleDatabase("frozen"))
        with self.assertRaises(ValueError):
            service.edit_case(1, question="changed")
        with self.assertRaises(ValueError):
            service.delete_case(1)

    def test_draft_versions_remain_editable(self):
        database = _LifecycleDatabase("draft")
        service = DatasetLifecycleService(database)
        service.edit_case(1, question="changed")
        self.assertTrue(database.updated)

    def test_reupload_does_not_rebuild_frozen_snapshot(self):
        database = _LifecycleDatabase()
        service = DatasetLifecycleService(database)
        service.rebuild_on_reupload(document_id=3, job_id=5)
        self.assertIn("已有冻结版本保持不变", database.jobs[-1][1]["message"])

    def test_multi_turn_upload_uses_final_turn_for_storage_and_quality(self):
        database = _UploadedSetDatabase()
        result = import_uploaded_set(
            db=database,
            name="multi",
            template_type="multi",
            dimension=None,
            cases=[
                {
                    "session_id": "s1",
                    "turns": [{"q": "first", "a": "one"}, {"q": "final", "a": "two"}],
                }
            ],
        )
        self.assertEqual(database.payload["cases"][0]["q"], "final")
        self.assertEqual(database.payload["cases"][0]["a"], "two")
        self.assertEqual(result["quality"]["data_completeness_rate"], 1.0)

    def test_public_sets_start_as_quality_checked(self):
        database = _PublicSetDatabase()
        import_public_set(
            db=database,
            name="public",
            version="v1.0.0",
            dimensions=None,
            cases=[{"q": "question", "a": "answer", "review_status": "governance_passed"}],
        )
        self.assertEqual(database.set_kwargs["review_status"], "quality_checked")

    def test_tree_uses_actual_covered_eius(self):
        result = DatasetLifecycleService(_TreeDatabase()).tree()
        node = result["tree"][0]
        self.assertEqual(node["coverage_pct"], 50.0)
        self.assertEqual(node["gap"], 1)


if __name__ == "__main__":
    unittest.main()
