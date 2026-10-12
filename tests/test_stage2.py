import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from index import Index  # noqa: E402
from preprocess import joined, normalize, terms, tokens  # noqa: E402
from trie import Trie  # noqa: E402


class PreprocessTests(unittest.TestCase):
    def test_keeps_game_symbols(self):
        self.assertEqual(tokens("Gives X1.5 Mult and +4 Mult for $10"),
                         ["gives", "x1.5", "mult", "and", "+4", "mult", "for", "$10"])

    def test_multiplication_sign_and_percent(self):
        self.assertEqual(tokens("×2 chips, 50% chance"), ["x2", "chips", "50%", "chance"])

    def test_accents_apostrophes_hyphens(self):
        self.assertEqual(tokens("Blueprint's café"), ["blueprint", "cafe"])
        self.assertEqual(tokens("Mail-In Rebate"), ["mail", "in", "rebate"])

    def test_suit_symbols_become_words(self):
        self.assertEqual(tokens("♠ ♥ ♦ ♣"), ["spades", "hearts", "diamonds", "clubs"])

    def test_sentence_period_not_part_of_number(self):
        self.assertEqual(tokens("It costs $5."), ["it", "costs", "$5"])

    def test_stopwords_removed_only_in_terms(self):
        self.assertEqual(terms("What is the rarity of Blueprint?"), ["rarity", "blueprint"])
        self.assertIn("what", tokens("What is the rarity"))

    def test_joined_supports_phrase_search(self):
        self.assertIn("mr bones", joined("Mr. Bones: prevents death"))
        self.assertEqual(normalize("ÁÉÍ"), "aei")


class TrieTests(unittest.TestCase):
    def setUp(self):
        self.t = Trie()
        for word, n in [("joker", 5), ("jokers", 3), ("jolly", 2), ("mult", 7)]:
            self.t.insert(word, n)

    def test_get_and_contains(self):
        self.assertEqual(self.t.get("joker"), 5)
        self.assertIn("mult", self.t)
        self.assertNotIn("jok", self.t)  # prefijo, no palabra
        self.assertEqual(len(self.t), 4)

    def test_insert_accumulates_frequency_once(self):
        self.t.insert("joker")
        self.assertEqual(self.t.get("joker"), 6)
        self.assertEqual(len(self.t), 4)

    def test_complete_orders_by_frequency(self):
        self.assertEqual([w for w, _ in self.t.complete("jo")], ["joker", "jokers", "jolly"])
        self.assertEqual(self.t.complete("jo", k=1), [("joker", 5)])
        self.assertEqual(self.t.complete("zzz"), [])

    def test_items_alphabetical(self):
        self.assertEqual([w for w, _ in self.t.items()], ["joker", "jokers", "jolly", "mult"])

    def test_shared_prefix_shares_nodes(self):
        self.assertEqual(self.t.nodes, 1 + len("joker") + 1 + len("lly") + len("mult"))


class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = Index.load()

    def test_known_terms_indexed(self):
        for word in ["blueprint", "mult", "x1.5", "+4", "$10"]:
            self.assertIn(word, self.idx.vocab)

    def test_stopwords_not_indexed(self):
        self.assertNotIn("the", self.idx.vocab)

    def test_postings_consistent_with_chunks(self):
        for term in ["blueprint", "x1.5"]:
            for cid, tf in self.idx.postings[term].items():
                self.assertEqual(terms(self.idx.chunks[cid]["text"]).count(term), tf)

    def test_card_names_trie(self):
        self.assertIn("mr bones", self.idx.names)
        self.assertIn("blueprint", self.idx.names)

    def test_autocomplete(self):
        self.assertIn("blueprint", self.idx.autocomplete("bluep"))


if __name__ == "__main__":
    unittest.main()
