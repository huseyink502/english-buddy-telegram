"""Build multiple-choice questions without needing the AI API."""

import random
from curriculum import all_words


def questions_for(words: list[tuple[str, str]], rng=None) -> list[dict]:
    rng = rng or random.Random()
    pool = list({tr for _, tr in all_words()})
    questions = []
    for english, turkish in words:
        others = rng.sample([translation for translation in pool if translation != turkish], 3)
        choices = [turkish, *others]
        rng.shuffle(choices)
        questions.append({"english": english, "turkish": turkish,
                          "options": choices, "correct_index": choices.index(turkish)})
    rng.shuffle(questions)
    return questions
