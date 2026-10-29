import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_data import validate_records


class DataContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Hash validation fixtures, not video decode fixtures.
        (self.root / "a.mp4").write_bytes(b"distinct recording a")
        (self.root / "b.mp4").write_bytes(b"distinct recording b")
        self.rows = [dict(id=name, media=f"{name}.mp4", group=name, split=split,
                          usage="train", reviewed=True, question="What is visible?",
                          answer="Green liquid is visible.") for name, split in (("a", "train"), ("b", "val"))]

    def test_native_conversation_output(self):
        result = validate_records(self.rows, self.root)
        self.assertEqual(result["train"][0]["video"], "a.mp4")
        self.assertEqual(result["val"][0]["conversations"][1]["from"], "gpt")

    def test_same_session_rejected(self):
        self.rows[1]["group"] = "a"
        with self.assertRaisesRegex(ValueError, "Session leakage"):
            validate_records(self.rows, self.root)

    def test_renamed_duplicate_rejected(self):
        (self.root / "b.mp4").write_bytes((self.root / "a.mp4").read_bytes())
        with self.assertRaisesRegex(ValueError, "Identical media"):
            validate_records(self.rows, self.root)

    def test_unreviewed_and_empty_answers_rejected(self):
        for field, value in (("reviewed", False), ("answer", " ")):
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            with self.assertRaises(ValueError):
                validate_records(rows, self.root)

    def test_changed_media_rejected(self):
        self.rows[0]["sha256"] = "incorrect"
        with self.assertRaisesRegex(ValueError, "media changed"):
            validate_records(self.rows, self.root)

    def test_traversal_rejected(self):
        self.rows[0]["media"] = "../outside.mp4"
        with self.assertRaisesRegex(ValueError, "outside dataset"):
            validate_records(self.rows, self.root)

    def test_independent_validation_required(self):
        with self.assertRaisesRegex(ValueError, "BOTH"):
            validate_records(self.rows[:1], self.root)


if __name__ == "__main__":
    unittest.main()
