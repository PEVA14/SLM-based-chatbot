import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from approx import NgramIndex, jaccard, levenshtein, similarity, trigrams  # noqa: E402
from eval_questions import QUESTIONS, validate  # noqa: E402
from index import Index  # noqa: E402
from lexicon import EQUIVALENCES, expansions  # noqa: E402
from search_approx import ApproxSearcher, is_inflection, max_dist  # noqa: E402
from trie import Trie  # noqa: E402


class SimilarityTests(unittest.TestCase):
    def test_levenshtein_known_values(self):
        self.assertEqual(levenshtein("kitten", "sitting"), 3)
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertEqual(levenshtein("abc", "abc"), 0)
        self.assertEqual(levenshtein("blueprnt", "blueprint"), 1)
        self.assertEqual(levenshtein("flaw", "lawn"), levenshtein("lawn", "flaw"))

    def test_similarity_range(self):
        self.assertEqual(similarity("mult", "mult"), 1.0)
        self.assertAlmostEqual(similarity("joker", "jokers"), 1 - 1 / 6)
        self.assertEqual(similarity("", ""), 1.0)

    def test_trigrams_and_jaccard(self):
        self.assertEqual(trigrams("mult"), {"_mu", "mul", "ult", "lt_"})
        self.assertEqual(jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
        self.assertEqual(jaccard({"a"}, {"a"}), 1.0)

    def test_ngram_index_finds_close_words(self):
        idx = NgramIndex(["multiplicative", "multiplier", "chips", "mult"])
        words = [w for w, _ in idx.similar("multiplicativ", threshold=0.5)]
        self.assertEqual(words[0], "multiplicative")
        self.assertNotIn("chips", words)


class TrieFuzzyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = Index.load()
        cls.words = [w for w, _ in cls.idx.vocabulary()]

    def brute(self, word, d, prefix):
        return sorted((w, levenshtein(word, w)) for w in self.words
                      if w[:prefix] == word[:prefix] and levenshtein(word, w) <= d)

    def test_matches_brute_force_levenshtein(self):
        rng = random.Random(3)
        for _ in range(40):
            word = rng.choice(self.words)
            chars = list(word)
            if len(chars) > 3:  # perturba una letra para simular un typo
                chars[rng.randrange(len(chars))] = rng.choice("aeioutnrs")
            query = "".join(chars)
            for d in (1, 2):
                for prefix in (0, 1):
                    got = sorted((w, dist) for w, dist, _ in self.idx.vocab.fuzzy(query, d, prefix))
                    self.assertEqual(got, self.brute(query, d, prefix), (query, d, prefix))

    def test_small_trie_exact_behaviour(self):
        t = Trie()
        for w in ["joker", "jokers", "joke", "poker"]:
            t.insert(w)
        got = {w: d for w, d, _ in t.fuzzy("joker", 1)}
        self.assertEqual(got, {"joker": 0, "jokers": 1, "joke": 1, "poker": 1})
        got = {w: d for w, d, _ in t.fuzzy("joker", 1, fixed_prefix=1)}
        self.assertNotIn("poker", got)

    def test_returns_nothing_beyond_distance(self):
        self.assertEqual(self.idx.vocab.fuzzy("zzzzzzzz", 1), [])


class LexiconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = Index.load()

    def test_every_target_exists_in_corpus_vocabulary(self):
        targets = {t for ts in EQUIVALENCES.values() for t in ts} | {"effect"}
        for t in targets:
            self.assertIn(t, self.idx.vocab, t)

    def test_cost_expands_to_buy_price(self):
        self.assertEqual(expansions("How much does Mr. Bones cost?", ["cost"]), ["buy", "price"])

    def test_what_does_x_do_expands_to_effect(self):
        self.assertEqual(expansions("What does Mime do?", ["mime"]), ["effect"])

    def test_no_duplicates_of_existing_terms(self):
        self.assertEqual(expansions("buy price cost", ["buy", "price", "cost"]), [])


class QuestionSetTests(unittest.TestCase):
    def test_every_label_is_reachable(self):
        self.assertEqual(validate(Index.load().chunks), [])

    def test_has_variety(self):
        self.assertGreaterEqual(len(QUESTIONS), 20)
        self.assertGreaterEqual(len({q.kind for q in QUESTIONS}), 6)


class ApproxSearcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = Index.load()
        cls.fuzzy = ApproxSearcher(cls.idx)
        cls.plain = ApproxSearcher(cls.idx, fuzzy=False)

    def test_is_inflection(self):
        self.assertTrue(is_inflection("joker", "jokers"))
        self.assertTrue(is_inflection("copy", "copies"))
        self.assertFalse(is_inflection("joker", "jokes"))
        self.assertFalse(is_inflection("played", "player"))
        self.assertEqual([max_dist(n) for n in (3, 4, 7, 8)], [0, 1, 1, 2])

    def test_typo_resolved_to_vocabulary_word(self):
        words = [v.word for v in self.fuzzy.resolve("blueprnt")]
        self.assertEqual(words[0], "blueprint")

    def test_known_term_gets_only_inflections(self):
        words = [v.word for v in self.fuzzy.resolve("jokers")]
        self.assertEqual(words[0], "jokers")
        self.assertIn("joker", words)
        self.assertNotIn("jokes", words)

    def test_numeric_terms_are_exact_only(self):
        self.assertEqual([v.word for v in self.fuzzy.resolve("x1.5")], ["x1.5"])

    def test_misspelled_card_name_detected(self):
        names = [n for n, _ in self.fuzzy.detect_names("How much does Mr. Bone cost?")]
        self.assertEqual(names, ["mr bones"])

    def test_typo_question_finds_the_card_sheet(self):
        res = self.fuzzy.search("What does Blueprnt do?")
        self.assertEqual(res.hits[0].title, "Blueprint")
        self.assertIn("Effect: Copies ability", res.hits[0].text)

    def test_fuzzy_off_is_strictly_exact(self):
        res = self.plain.search("What does Blueprnt do?")
        self.assertEqual(res.hits, [])
        self.assertEqual(res.variants, {})

    def test_only_expansion_evidence_gives_no_hits(self):
        res = self.fuzzy.search("What does zzzzzz do?")
        self.assertEqual(res.hits, [])

    def test_unknown_word_is_reported(self):
        res = self.fuzzy.search("Does the game have a joker called Pikachu?")
        self.assertIn("pikachu", res.unmatched_terms)


if __name__ == "__main__":
    unittest.main()
