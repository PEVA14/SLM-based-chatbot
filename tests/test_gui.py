import sys
import time
import tkinter as tk
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autocomplete import apply, suggest  # noqa: E402
from gui import ABSTAIN_HINT, LOW_CONFIDENCE, LOW_CONFIDENCE_NOTE, NO_ANSWER_ES, App  # noqa: E402
from index import Index  # noqa: E402
from pipeline import ChatBot  # noqa: E402
from qa_model import NO_ANSWER, Answer  # noqa: E402


class FindingModel:
    """Modelo falso: devuelve el tramo `needle` del contexto, o se abstiene."""

    def __init__(self):
        self.needle = "Rare"
        self.score = 0.9
        self.calls = []

    def answer(self, question, context):
        self.calls.append(question)
        i = context.find(self.needle) if self.needle else -1
        if i < 0:
            return Answer(NO_ANSWER, 0.77, -1, -1, True)
        return Answer(self.needle, self.score, i, i + len(self.needle), False)


class AutocompleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = Index.load()

    def labels(self, text, **kw):
        return [s.label for s in suggest(self.index, text, **kw)]

    def test_card_name_completion_from_partial_words(self):
        self.assertEqual(self.labels("How much does Mr. bo")[0], "Mr. Bones")
        self.assertEqual(self.labels("What does bluep")[0], "Blueprint")

    def test_multiword_card_names(self):
        self.assertIn("The Fool", self.labels("what rarity is the fo"))

    def test_word_completion_by_corpus_frequency(self):
        words = self.labels("which joker retr")
        self.assertEqual(words[0], "retrigger")
        self.assertTrue(all(w.startswith("retr") for w in words))

    def test_keeps_capitalisation_of_the_typed_word(self):
        self.assertIn("Retrigger", self.labels("Retr"))

    def test_no_suggestions_after_space_punctuation_or_one_letter(self):
        for text in ("", "What does Blueprint ", "What does Blueprint?", "m"):
            self.assertEqual(self.labels(text), [], text)

    def test_never_suggests_what_is_already_typed(self):
        self.assertNotIn("blueprint", [s.insert.lower() for s in suggest(self.index, "blueprint")
                                       if s.kind == "word" and s.insert == "blueprint"])

    def test_limit_and_apply(self):
        self.assertLessEqual(len(suggest(self.index, "x1", k=4)), 4)
        s = suggest(self.index, "How much does Mr. bo")[0]
        self.assertEqual(apply("How much does Mr. bo", s), "How much does Mr. Bones ")


def pump(root, condition, timeout=90):
    """Corre mainloop hasta que se cumpla la condicion (sin llamar a update(), que se cuelga)."""
    result = {}
    deadline = time.time() + timeout

    def check():
        if condition() or time.time() > deadline:
            result["ok"] = bool(condition())
            root.quit()
        else:
            root.after(40, check)

    root.after(40, check)
    root.mainloop()
    return result["ok"]


def text_of(widget):
    return widget.get("1.0", "end")


_ROOT = None  # Tk de macOS no tolera crear una segunda raiz tras destruir la primera: una sola


def tearDownModule():
    if _ROOT is not None:
        _ROOT.destroy()


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _ROOT
        if _ROOT is None:
            try:
                _ROOT = tk.Tk()
            except tk.TclError as exc:
                raise unittest.SkipTest(f"Tk no disponible: {exc}")
            _ROOT.withdraw()
        cls.model = FindingModel()
        cls.bot = ChatBot(model=cls.model, cache=False)

    def setUp(self):
        self.model.needle, self.model.score = "Rare", 0.9
        self.root = _ROOT
        for widget in self.root.winfo_children():  # limpia la ventana de la prueba anterior
            widget.destroy()
        self.app = App(self.root, bot_factory=lambda: self.bot)
        self.assertTrue(pump(self.root, lambda: self.app.ready), "el bot no termino de cargar")

    def tearDown(self):
        self.app.shutdown()

    def type(self, text):
        self.app.entry.delete(0, "end")
        self.app.entry.insert(0, text)
        self.app._on_key(types.SimpleNamespace(keysym="x"))

    def ask(self, question):
        self.app.send(question)
        self.assertTrue(self.app.busy)
        self.assertTrue(pump(self.root, lambda: not self.app.busy), "no llego la respuesta")

    def test_starts_ready_with_welcome_message(self):
        self.assertTrue(self.app.send_btn.enabled)
        self.assertIn("listo", self.app.status.cget("text"))
        self.assertIn("Listo. Pregúntame", text_of(self.app.chat))

    def test_typing_shows_trie_suggestions_and_tab_accepts_first(self):
        self.type("How much does Mr. bo")
        chips = [w.cget("text") for w in self.app.chip_row.winfo_children()]
        self.assertEqual(chips[0], "Mr. Bones")
        self.assertEqual(self.app._on_tab(None), "break")
        self.assertEqual(self.app.entry.get(), "How much does Mr. Bones ")

    def test_clicking_a_suggestion_chip_inserts_it(self):
        self.type("What does bluep")
        self.app.chip_row.winfo_children()[0].command()
        self.assertEqual(self.app.entry.get(), "What does Blueprint ")

    def test_answer_appears_in_chat_and_panel_with_highlight(self):
        self.ask("What rarity is Blueprnt?")
        chat, panel = text_of(self.app.chat), text_of(self.app.panel)
        self.assertIn("What rarity is Blueprnt?", chat)
        self.assertIn("Rare", chat)
        self.assertIn("fuente: Blueprint", chat)
        self.assertIn("What rarity is Blueprint?", panel)           # pregunta limpia
        self.assertIn("corrección: Blueprnt → Blueprint", panel)
        self.assertIn("CONTEXTO", panel)
        self.assertIn("TIEMPOS", panel)
        ranges = self.app.panel.tag_ranges("hl")
        self.assertEqual(self.app.panel.get(ranges[0], ranges[1]), "Rare")  # respuesta resaltada

    def test_abstention_is_shown_in_spanish_with_unknown_terms(self):
        self.model.needle = None
        self.ask("Does the game have a joker called Pikachu?")
        chat = text_of(self.app.chat)
        self.assertIn(NO_ANSWER_ES, chat)
        self.assertIn(ABSTAIN_HINT, chat)  # sugiere que tipo de pregunta si responde
        self.assertIn("pikachu", chat)
        self.assertEqual(len(self.app.panel.tag_ranges("hl")), 0)

    def test_low_confidence_answer_is_shown_with_a_warning(self):
        self.model.score = 0.05
        self.ask("What rarity is Blueprint?")
        chat = text_of(self.app.chat)
        self.assertIn("Rare", chat)                     # la respuesta no se oculta
        self.assertIn(LOW_CONFIDENCE_NOTE, chat)
        self.assertTrue(self.app.chat.tag_ranges("warn"))

    def test_confident_answer_and_abstention_have_no_warning(self):
        self.ask("What rarity is Blueprint?")
        self.assertNotIn(LOW_CONFIDENCE_NOTE, text_of(self.app.chat))
        self.assertNotIn(ABSTAIN_HINT, text_of(self.app.chat))  # la pista es solo al abstenerse
        self.model.needle, self.model.score = None, 0.01  # se abstiene aunque el puntaje sea bajo
        self.ask("What is the capital of France?")
        self.assertNotIn(LOW_CONFIDENCE_NOTE, text_of(self.app.chat))

    def test_threshold_sits_between_known_wrong_and_lowest_correct(self):
        self.assertGreater(LOW_CONFIDENCE, 0.05)   # la respuesta equivocada de "5 legendary jokers"
        self.assertLessEqual(LOW_CONFIDENCE, 0.2)  # evita avisar en casi todas las correctas

    def test_mode_toggle_changes_search_used(self):
        self.app.toggle.select("exact")
        self.assertEqual(self.app.mode, "exact")
        self.ask("What rarity is Blueprint?")
        self.assertIn("búsqueda exacta", text_of(self.app.chat))
        self.assertIn("BÚSQUEDA EXACTA", text_of(self.app.panel))

    def test_second_question_is_ignored_while_busy(self):
        self.app.send("What rarity is Blueprint?")
        self.app.send("What rarity is Chicot?")  # ignorada: ya hay una en curso
        self.assertTrue(pump(self.root, lambda: not self.app.busy))
        self.assertEqual(text_of(self.app.chat).count("TÚ"), 1)

    def test_empty_question_is_not_sent(self):
        self.app.entry.delete(0, "end")
        self.app.send()
        self.assertFalse(self.app.busy)

    def test_suggestion_row_keeps_its_height(self):
        self.root.update_idletasks()
        before = self.app.chip_row.winfo_reqheight()
        self.type("How much does Mr. bo")
        self.root.update_idletasks()
        self.assertEqual(self.app.chip_row.winfo_reqheight(), before)
        self.assertGreater(len(self.app.chip_row.winfo_children()), 0)

    def test_shutdown_cancels_the_poll_timer_and_is_idempotent(self):
        self.app.shutdown()
        self.assertIsNone(self.app._poll_id)
        self.app.shutdown()  # tearDown la vuelve a llamar: no debe fallar


if __name__ == "__main__":
    unittest.main()
