import random
import tempfile
import unittest
from pathlib import Path
from curriculum import LESSONS, all_words, lesson_for, render_lesson
from db import ProgressDB
from quiz import questions_for


class CurriculumTest(unittest.TestCase):
    def test_seven_days(self):
        self.assertEqual(len(LESSONS), 7)
        self.assertEqual(len(all_words()), 35)
        self.assertIn("Merhaba", render_lesson(1))
        with self.assertRaises(ValueError):
            lesson_for(0)

    def test_questions_have_one_correct_option(self):
        questions = questions_for(lesson_for(1)["words"], random.Random(17))
        self.assertEqual(len(questions), 5)
        for question in questions:
            self.assertEqual(len(set(question["options"])), 4)
            self.assertEqual(question["options"][question["correct_index"]], question["turkish"])


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = ProgressDB(str(Path(self.tmp.name) / "progress.db"))
        self.user_id = 12345

    def tearDown(self):
        self.tmp.cleanup()

    def test_lesson_progress_and_no_duplicate_words(self):
        self.assertEqual(self.db.day(self.user_id), 1)
        self.db.learn_words(self.user_id, lesson_for(1)["words"])
        self.db.learn_words(self.user_id, lesson_for(1)["words"])
        self.assertEqual(self.db.stats(self.user_id)["words"], 5)
        self.assertEqual(self.db.next_day(self.user_id), 2)
        for _ in range(10):
            self.db.next_day(self.user_id)
        self.assertEqual(self.db.day(self.user_id), 7)

    def test_quiz_scores_persist(self):
        self.db.log_quiz(self.user_id, 3, 5)
        self.assertEqual(self.db.stats(self.user_id)["correct"], 3)
        self.assertEqual(ProgressDB(self.db.path).stats(self.user_id)["quizzes"], 1)


if __name__ == "__main__":
    unittest.main()
