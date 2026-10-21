"""Build multiple-choice questions without needing the AI API."""

import random
from curriculum import all_words


def questions_for(words: list[tuple[str, str]], rng=None) -> list[dict]:
    rng = rng if rng is not None else random.Random()
    pool = sorted({tr for _, tr in all_words()})
    if len(pool) < 4:
        raise ValueError("Multiple-choice tests require at least four translations")
    questions = []
    for english, turkish in words:
        others = rng.sample([translation for translation in pool if translation != turkish], 3)
        choices = [turkish, *others]
        rng.shuffle(choices)
        questions.append({"english": english, "turkish": turkish,
                          "options": choices, "correct_index": choices.index(turkish)})
    rng.shuffle(questions)
    return questions
