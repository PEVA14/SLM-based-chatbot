import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from exact import failure_function, kmp_search, naive_search, z_function, z_search  # noqa: E402
from index import Index  # noqa: E402
from search_exact import ExactSearcher  # noqa: E402


class AlgorithmTests(unittest.TestCase):
    def test_failure_function_classic(self):
        self.assertEqual(failure_function("ababaca"), [0, 0, 1, 2, 3, 0, 1])

    def test_z_function_classic(self):
        self.assertEqual(z_function("aabcaabxaaaz"), [0, 1, 0, 0, 3, 1, 0, 0, 2, 2, 1, 0])

    def test_overlapping_matches(self):
        for algo in (kmp_search, z_search, naive_search):
            self.assertEqual(algo("aaaa", "aa"), [0, 1, 2])
            self.assertEqual(algo("abcabc", "abc"), [0, 3])

    def test_no_match_and_empty_pattern(self):
        for algo in (kmp_search, z_search, naive_search):
            self.assertEqual(algo("abc", "d"), [])
            self.assertEqual(algo("abc", ""), [])
            self.assertEqual(algo("", "a"), [])
            self.assertEqual(algo("ab", "abc"), [])

    def test_agree_with_naive_on_random_strings(self):
        rng = random.Random(7)
        for _ in range(1500):
            text = "".join(rng.choice("abc") for _ in range(rng.randint(0, 40)))
            pat = "".join(rng.choice("abc") for _ in range(rng.randint(1, 5)))
            expected = naive_search(text, pat)
            self.assertEqual(kmp_search(text, pat), expected)
            self.assertEqual(z_search(text, pat), expected)


class SearcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = Index.load()
        cls.kmp = ExactSearcher(cls.idx, term_algo="kmp")
        cls.zed = ExactSearcher(cls.idx, term_algo="z")

    def test_whole_word_only(self):
        # "joker" no debe coincidir dentro de "jokers"
        tf = self.kmp._scan("joker", self.kmp.term_search)
        for cid in tf:
            self.assertIn(" joker ", f" {self.idx.joined[cid]} ")

    def test_scan_counts_match_token_counts(self):
        tf = self.kmp._scan("blueprint", self.kmp.term_search)
        for cid, f in tf.items():
            self.assertEqual(self.idx.joined[cid].split().count("blueprint"), f)
        self.assertEqual(len(tf), self.idx.df("blueprint"))

    def test_kmp_and_z_give_same_ranking(self):
        q = "What rarity is Blueprint?"
        a, b = self.kmp.search(q), self.zed.search(q)
        self.assertEqual([(h.id, h.score) for h in a.hits], [(h.id, h.score) for h in b.hits])

    def test_card_sheet_ranks_first(self):
        res = self.kmp.search("What rarity is Blueprint?")
        self.assertEqual(res.hits[0].title, "Blueprint")
        self.assertIn("Rarity: Rare", res.hits[0].text)

    def test_multiword_name_detected_and_longest_wins(self):
        self.assertEqual(self.kmp.detect_names("How much does Mr. Bones cost?"), ["mr bones"])

    def test_typo_has_no_exact_match(self):
        res = self.kmp.search("What does Blueprnt do?")
        self.assertEqual(res.unmatched_terms, ["blueprnt"])
        self.assertEqual(res.hits, [])

    def test_cache_returns_same_results(self):
        cached = ExactSearcher(self.idx, cache=True)
        q = "How do I unlock Hologram?"
        first, second = cached.search(q), cached.search(q)
        self.assertEqual([h.id for h in first.hits], [h.id for h in second.hits])
        self.assertLess(second.timings_ms["total"], first.timings_ms["total"])


if __name__ == "__main__":
    unittest.main()
