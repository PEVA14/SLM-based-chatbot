import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from context import select_context  # noqa: E402
from pipeline import ChatBot  # noqa: E402
from qa_model import NO_ANSWER, Answer  # noqa: E402
from query_clean import clean_question  # noqa: E402
from search_exact import Hit  # noqa: E402


def hit(cid, text, score=1.0, title="T"):
    return Hit(cid, title, score, {}, text)


class ContextTests(unittest.TestCase):
    def test_keeps_score_order_and_builds_spans(self):
        ctx = select_context([hit(1, "alpha beta gamma"), hit(2, "delta epsilon zeta")])
        self.assertEqual([c.id for c in ctx.chunks], [1, 2])
        self.assertEqual(ctx.text, "alpha beta gamma\n\ndelta epsilon zeta")
        self.assertEqual(ctx.chunk_at(0), 1)
        self.assertEqual(ctx.chunk_at(len(ctx.text) - 1), 2)
        self.assertIsNone(ctx.chunk_at(len("alpha beta gamma") + 1))  # separador

    def test_word_limit_skips_long_chunk_and_tries_next(self):
        long_ = hit(1, " ".join(f"w{i}" for i in range(50)))
        short = hit(2, "tiny chunk here")
        ctx = select_context([hit(0, "first chunk text"), long_, short], max_words=10)
        self.assertEqual([c.id for c in ctx.chunks], [0, 2])
        self.assertEqual(ctx.skipped, [(1, "excede el limite de palabras")])

    def test_redundant_chunk_is_dropped(self):
        a = hit(1, "blueprint copies the joker to the right side")
        dup = hit(2, "blueprint copies the joker to the right side too")
        other = hit(3, "mime retriggers held cards")
        ctx = select_context([a, dup, other])
        self.assertEqual([c.id for c in ctx.chunks], [1, 3])
        self.assertEqual(ctx.skipped, [(2, "redundante")])

    def test_max_chunks(self):
        hits = [hit(i, f"unique{i} words{i} here{i}") for i in range(10)]
        self.assertEqual(len(select_context(hits, max_chunks=3).chunks), 3)

    def test_empty_hits(self):
        ctx = select_context([])
        self.assertEqual((ctx.text, ctx.chunks), ("", []))


class StubModel:
    def __init__(self, answer):
        self._answer, self.calls = answer, []

    def answer(self, question, context):
        self.calls.append((question, context))
        return self._answer


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub = StubModel(Answer("Rare", 0.9, 0, 4, False))
        cls.bot = ChatBot(model=cls.stub, cache=False)

    def test_clean_question_fixes_typos_and_keeps_the_rest(self):
        s = self.bot.approx
        self.assertEqual(clean_question("What does Blueprnt do?", s).text, "What does Blueprint do?")
        self.assertEqual(clean_question("How much does Mr. Bone cost?", s).text,
                         "How much does Mr. Bones cost?")
        ok = clean_question("What rarity is Blueprint?", s)
        self.assertEqual((ok.text, ok.corrections), ("What rarity is Blueprint?", []))

    def test_short_unknown_words_are_not_autocorrected(self):
        s = self.bot.approx
        self.assertEqual(clean_question("hello", s).text, "hello")       # no "hell"
        self.assertEqual(clean_question("hello", s).corrections, [])
        # los typos de 7+ letras se siguen corrigiendo
        self.assertEqual(clean_question("How do I unlock Hologrm?", s).text, "How do I unlock Hologram?")
        self.assertEqual(clean_question("What does Fibonaci do?", s).text, "What does Fibonacci do?")

    def test_tidy_answer_removes_the_repeated_title_prefix(self):
        from qa_model import tidy_answer
        self.assertEqual(tidy_answer("Mime: Mime"), "Mime")
        self.assertEqual(tidy_answer("Mr. Bones: Mr. Bones (Joker)"), "Mr. Bones (Joker)")
        for untouched in ("Rare", "$7", "Cavendish: it gains", "Lose 5 runs"):
            self.assertEqual(tidy_answer(untouched), untouched)

    def test_approx_mode_sends_cleaned_question_to_model(self):
        r = self.bot.answer("What rarity is Blueprnt?", "approx")
        self.assertEqual(r.prompt_question, "What rarity is Blueprint?")
        self.assertFalse(r.rewritten)
        self.assertEqual(self.stub.calls[-1][0], "What rarity is Blueprint?")
        self.assertEqual(r.context.chunks[0].title, "Blueprint")

    def test_both_modes_send_the_same_prompt(self):
        a = self.bot.answer("What does Blueprnt do?", "approx")
        e = self.bot.answer("What does Blueprnt do?", "exact")
        self.assertEqual(a.prompt_question, "What is the effect of Blueprint?")
        self.assertEqual(e.prompt_question, a.prompt_question)
        self.assertTrue(a.rewritten and e.rewritten)

    def test_exact_mode_cannot_recover_from_a_typo(self):
        # El typo no coincide con nada; solo "rarity" aporta fragmentos, ninguno de Blueprint.
        e = self.bot.answer("What rarity is Blueprnt?", "exact")
        self.assertTrue(all(c.title != "Blueprint" for c in e.context.chunks))

    def test_rewrite_rules(self):
        from lexicon import rewrite_question
        cases = {
            "What does Mime do?": "What is the effect of Mime?",
            "What does the Egg joker do?": "What is the effect of the Egg joker?",
            "how does Blueprint work?": "What is the effect of Blueprint?",
            "How much does Hologram cost?": "What is the buy price of Hologram?",
            "How much is Brainstorm worth when sold?": "What is the sell price of Brainstorm?",
        }
        for src, expected in cases.items():
            self.assertEqual(rewrite_question(src), (expected, True), src)
        for untouched in ("What rarity is Blueprint?", "How do I unlock Brainstorm?",
                          "Which joker gives X3 Mult?"):
            self.assertEqual(rewrite_question(untouched), (untouched, False))

    def test_request_forms_become_questions(self):
        from lexicon import rewrite_question
        card = lambda text: text.lower() in ("blueprint", "mr. bones")
        cases = {
            "Tell me a rare joker": "What is a rare joker?",
            "Give me a legendary joker": "What is a legendary joker?",
            "Tell me about Blueprint": "What is the effect of Blueprint?",
            "Tell me about the game": "What is the game?",  # no es una carta
            "Blueprint": "What is the effect of Blueprint?",  # nombre suelto
        }
        for src, expected in cases.items():
            self.assertEqual(rewrite_question(src, card), (expected, True), src)
        self.assertEqual(rewrite_question("hello", card), ("hello", False))
        # sin is_card el nombre suelto no se toca (compatibilidad)
        self.assertEqual(rewrite_question("Blueprint"), ("Blueprint", False))

    def test_pipeline_recognises_card_names_for_rewrites(self):
        self.assertTrue(self.bot._is_card("Blueprint"))
        self.assertTrue(self.bot._is_card("mr bones"))
        self.assertFalse(self.bot._is_card("hello"))
        r = self.bot.answer("Tell me about Blueprint", "approx")
        self.assertEqual(r.prompt_question, "What is the effect of Blueprint?")
        self.assertTrue(r.rewritten)
        self.assertEqual(r.context.chunks[0].title, "Blueprint")

    def test_request_words_do_not_pollute_the_search(self):
        for searcher in (self.bot.approx, self.bot.exact):
            terms = searcher.search("Tell me a rare joker").terms
            self.assertNotIn("tell", terms)
            self.assertIn("rare", terms)

    def test_supporting_chunk_is_the_one_containing_the_answer(self):
        r = self.bot.answer("What rarity is Blueprint?", "approx")
        self.assertEqual(r.supporting_chunk, r.context.chunks[0].id)

    def test_abstention_has_no_supporting_chunk(self):
        bot = ChatBot(model=StubModel(Answer(NO_ANSWER, 0.1, -1, -1, True)), cache=False)
        r = bot.answer("What rarity is Blueprint?", "approx")
        self.assertTrue(r.answer.abstained)
        self.assertIsNone(r.supporting_chunk)

    def test_timings_are_reported(self):
        r = self.bot.answer("What rarity is Blueprint?", "approx")
        for key in ("clean", "retrieval", "context", "model", "total"):
            self.assertIn(key, r.timings_ms)

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            self.bot.answer("x", "fuzzy")


if __name__ == "__main__":
    unittest.main()
