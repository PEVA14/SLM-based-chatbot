"""Interfaz grafica (Tkinter) del chatbot de jokers de Balatro.

  +--------------------------------------------------------------+
  |  JOKIE           [APROXIMADA | EXACTA]            estado      |
  +-----------------------------------+--------------------------+
  |  chat                             |  panel de recuperacion   |
  |                                   |  (pregunta limpia,       |
  |                                   |   terminos, contexto,    |
  |                                   |   respuesta, tiempos)    |
  +-----------------------------------+--------------------------+
  |  ejemplos        [ pregunta... ]  sugerencias (Trie)  [Enviar]|
  +--------------------------------------------------------------+

Decisiones:
  * La ventana nunca llama a update() (en el Tk 8.5 de macOS se cuelga); solo mainloop/after.
  * El modelo se carga y se consulta en hilos aparte para que la ventana no se congele
    (una respuesta tarda 1-5 s en CPU). Los hilos NO tocan widgets: dejan eventos en una
    cola que la ventana vacia con after().
  * tk.Button ignora los colores en macOS, asi que los botones son Labels con eventos.
"""
import queue
import threading
import tkinter as tk

from autocomplete import apply, suggest

BG, PANEL, CARD = "#14382d", "#0d2a22", "#f4f1e8"
INK, MUTED = "#10201b", "#8fb3a5"
GOLD, RED, BLUE, ORANGE = "#f2b632", "#e4584b", "#2b8cd6", "#f58b2a"
FONT_UI = ("Menlo", 11)
FONT_BOLD = ("Menlo", 11, "bold")
FONT_BODY = ("Helvetica Neue", 13)
FONT_SMALL = ("Helvetica Neue", 11)
FONT_TITLE = ("Menlo", 22, "bold")

MODE_LABELS = {"approx": "aproximada", "exact": "exacta"}
EXAMPLES = [
    "What rarity is Blueprint?",
    "How much does Mr. Bones cost?",
    "What does Blueprnt do?",
    "Which joker retriggers cards held in hand?",
    "How do I unlock Hologrm?",
    "What is the capital of France?",
]
NO_ANSWER_ES = "No lo sé: el contexto seleccionado no responde la pregunta."
ABSTAIN_HINT = ("Funciona mejor con datos de una carta concreta: su efecto, rareza, precio o cómo "
                "desbloquearla (ej. What does Mime do?). Los conteos, opiniones y listas completas no.")
# Por debajo de este puntaje la respuesta se muestra con un aviso (no se descarta). Con las 22
# respuestas correctas de la evaluacion el minimo fue 0.09 y una respuesta equivocada tuvo 0.05:
# el margen es corto, asi que solo se avisa. El puntaje no es una probabilidad calibrada.
LOW_CONFIDENCE = 0.15
LOW_CONFIDENCE_NOTE = "Ojo: confianza baja. Revisa en el panel si el fragmento resaltado respalda la respuesta."
POLL_MS = 60


class FlatButton(tk.Label):
    """Boton plano. (tk.Button no respeta bg/fg en macOS.)"""

    def __init__(self, master, text, command, bg=BLUE, fg="white", font=FONT_BOLD, padx=12, pady=5):
        super().__init__(master, text=text, bg=bg, fg=fg, font=font, padx=padx, pady=pady,
                         cursor="pointinghand")
        self.command, self.base_bg, self.enabled = command, bg, True
        self.bind("<Button-1>", lambda e: self.enabled and self.command())
        self.bind("<Enter>", lambda e: self.enabled and self.configure(bg=self._lighten(self.base_bg)))
        self.bind("<Leave>", lambda e: self.configure(bg=self.base_bg))

    @staticmethod
    def _lighten(color):
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % tuple(min(255, c + 28) for c in (r, g, b))

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(bg=self.base_bg if enabled else "#51675f",
                       cursor="pointinghand" if enabled else "arrow")

    def recolor(self, bg, fg):
        self.base_bg = bg
        self.configure(bg=bg, fg=fg)


class Toggle(tk.Frame):
    """Control segmentado: una opcion seleccionada."""

    def __init__(self, master, options, value, on_change):
        super().__init__(master, bg=PANEL, padx=2, pady=2)
        self.value, self.on_change, self.buttons = value, on_change, {}
        for v, label in options:
            btn = FlatButton(self, label, lambda v=v: self.select(v), font=FONT_UI, padx=14, pady=4)
            btn.pack(side="left", padx=1)
            self.buttons[v] = btn
        self._paint()

    def select(self, value):
        self.value = value
        self._paint()
        self.on_change(value)

    def _paint(self):
        for v, btn in self.buttons.items():
            on = v == self.value
            btn.recolor(GOLD if on else PANEL, INK if on else MUTED)


def default_bot_factory():
    from pipeline import ChatBot
    return ChatBot(k=10, cache=True)


class App:
    def __init__(self, root, bot_factory=default_bot_factory):
        self.root, self.bot, self.busy, self.ready = root, None, False, False
        self.mode = "approx"
        self.suggestions = []
        self.events = queue.Queue()
        self._poll_id, self.closed, self._redraw_ids = None, False, []
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.title("Jokie · Balatro joker assistant")
        root.configure(bg=BG)
        root.geometry("1180x760")
        root.minsize(920, 580)
        self._build()
        self._say("Cargando el índice y el modelo de lenguaje… (unos segundos)", "sys")
        threading.Thread(target=self._load_bot, args=(bot_factory,), daemon=True).start()
        self._poll_id = root.after(POLL_MS, self._poll)
        self._redraw_ids.append(root.after(350, self._force_redraw))

    def _force_redraw(self):
        """El Tk 8.5 de macOS recientes puede dejar la ventana sin pintar hasta que cambia de
        tamano: se cambia 1 px y se restaura. No hace nada si la ventana esta oculta."""
        r = self.root
        if self.closed or not r.winfo_viewable():
            return
        r.lift()
        w, h = r.winfo_width(), r.winfo_height()
        r.geometry(f"{w + 1}x{h}")
        self._redraw_ids.append(r.after(150, lambda: None if self.closed else r.geometry(f"{w}x{h}")))

    def shutdown(self):
        """Cancela los temporizadores pendientes (evita errores de `after` al salir)."""
        if self.closed:
            return
        self.closed = True
        for after_id in [self._poll_id, *self._redraw_ids]:
            if after_id is not None:
                self.root.after_cancel(after_id)
        self._poll_id, self._redraw_ids = None, []

    def close(self):
        self.shutdown()
        try:
            self.root.destroy()
        except tk.TclError:  # ya estaba destruida
            pass

    # ------------------------------------------------------------------ layout
    def _build(self):
        r = self.root
        r.grid_columnconfigure(0, weight=3, uniform="cols")
        r.grid_columnconfigure(1, weight=2, uniform="cols")
        r.grid_rowconfigure(1, weight=1)

        header = tk.Frame(r, bg=BG, padx=16, pady=10)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(header, text="JOKIE", bg=BG, fg=GOLD, font=FONT_TITLE).pack(side="left")
        tk.Label(header, text="  Balatro joker assistant", bg=BG, fg=MUTED, font=FONT_UI).pack(side="left")
        self.status = tk.Label(header, text="", bg=BG, fg=MUTED, font=FONT_UI)
        self.status.pack(side="right", padx=(12, 0))
        self.toggle = Toggle(header, [("approx", "APROXIMADA"), ("exact", "EXACTA")], "approx",
                             self._set_mode)
        self.toggle.pack(side="right")
        tk.Label(header, text="búsqueda:", bg=BG, fg=MUTED, font=FONT_UI).pack(side="right", padx=6)

        self.chat, chat_bar = self._text_area(row=1, column=0, bg=PANEL, padx=(16, 8))
        self.panel, panel_bar = self._text_area(row=1, column=1, bg=PANEL, padx=(8, 16))
        self._chat_tags()
        self._panel_tags()
        self._show_panel_placeholder()

        footer = tk.Frame(r, bg=BG, padx=16, pady=10)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        examples = tk.Frame(footer, bg=BG)
        examples.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        tk.Label(examples, text="Prueba:", bg=BG, fg=MUTED, font=FONT_UI).pack(side="left", padx=(0, 8))
        for q in EXAMPLES:
            FlatButton(examples, q, lambda q=q: self.send(q), bg="#245a49", fg=CARD,
                       font=FONT_SMALL, padx=8, pady=3).pack(side="left", padx=3)

        self.chip_row = tk.Frame(footer, bg=BG, height=30)  # altura fija: no salta al cambiar las sugerencias
        self.chip_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.chip_row.pack_propagate(False)

        self.entry = tk.Entry(footer, bg=CARD, fg=INK, insertbackground=INK, relief="flat",
                              font=("Helvetica Neue", 15), highlightthickness=2,
                              highlightbackground=PANEL, highlightcolor=GOLD)
        self.entry.grid(row=2, column=0, sticky="ew", ipady=8, padx=(0, 10))
        self.send_btn = FlatButton(footer, "ENVIAR", self.send, bg=RED, padx=20, pady=9)
        self.send_btn.grid(row=2, column=1)
        self.send_btn.set_enabled(False)
        tk.Label(footer, text="Tab acepta la primera sugerencia · Enter envía · "
                              "preguntas en inglés (el corpus es la wiki de Balatro)",
                 bg=BG, fg=MUTED, font=FONT_SMALL).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<Return>", lambda e: self.send())
        self.entry.bind("<Tab>", self._on_tab)
        self.entry.bind("<Escape>", lambda e: self._set_suggestions([]))
        self.entry.focus_set()

    def _text_area(self, row, column, bg, padx):
        frame = tk.Frame(self.root, bg=bg)
        frame.grid(row=row, column=column, sticky="nsew", padx=padx, pady=(0, 4))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        text = tk.Text(frame, bg=bg, fg=CARD, wrap="word", relief="flat", padx=14, pady=10,
                       font=FONT_BODY, state="disabled", cursor="arrow", highlightthickness=0,
                       spacing1=2, spacing3=2)
        bar = tk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=bar.set)
        text.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        return text, bar

    def _chat_tags(self):
        c = self.chat
        c.tag_configure("sys", foreground=MUTED, font=FONT_SMALL, justify="center", spacing1=8, spacing3=8)
        c.tag_configure("user_hdr", foreground=GOLD, font=FONT_UI, justify="right", spacing1=12, rmargin=4)
        c.tag_configure("user", background=GOLD, foreground=INK, justify="right",
                        lmargin1=120, lmargin2=120, rmargin=4, spacing1=3, spacing3=3)
        c.tag_configure("bot_hdr", foreground=BLUE, font=FONT_UI, spacing1=12, lmargin1=4)
        c.tag_configure("bot", background=CARD, foreground=INK, font=("Helvetica Neue", 14, "bold"),
                        lmargin1=4, lmargin2=4, rmargin=120, spacing1=3, spacing3=3)
        c.tag_configure("abstain", background="#3a4f48", foreground=CARD, font=("Helvetica Neue", 13),
                        lmargin1=4, lmargin2=4, rmargin=120, spacing1=3, spacing3=3)
        c.tag_configure("meta", foreground=MUTED, font=FONT_SMALL, lmargin1=4, lmargin2=4, spacing3=4)
        c.tag_configure("warn", foreground=ORANGE, font=FONT_SMALL, lmargin1=4, lmargin2=4, spacing3=4)

    def _panel_tags(self):
        p = self.panel
        p.tag_configure("h", foreground=GOLD, font=FONT_BOLD, spacing1=14, spacing3=3)
        p.tag_configure("k", foreground=MUTED, font=FONT_SMALL)
        p.tag_configure("v", foreground=CARD, font=FONT_SMALL, lmargin1=10, lmargin2=10)
        p.tag_configure("fix", foreground=ORANGE, font=FONT_SMALL, lmargin1=10, lmargin2=10)
        p.tag_configure("chunk", foreground=BLUE, font=FONT_BOLD, spacing1=8, lmargin1=10, lmargin2=10)
        p.tag_configure("text", foreground="#d8e3dd", font=FONT_SMALL, lmargin1=10, lmargin2=10)
        p.tag_configure("hl", background=GOLD, foreground=INK, font=("Helvetica Neue", 11, "bold"))
        p.tag_configure("time", foreground=CARD, font=FONT_UI, lmargin1=10, lmargin2=10)
        p.tag_configure("empty", foreground=MUTED, font=FONT_SMALL, justify="center", spacing1=60)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _append(widget, pieces):
        """pieces: [(texto, tag)]; el widget es de solo lectura, asi que se habilita un instante."""
        widget.configure(state="normal")
        for text, tag in pieces:
            widget.insert("end", text, tag)
        widget.configure(state="disabled")

    def _say(self, text, tag):
        self._append(self.chat, [(text + "\n", tag)])
        self.chat.see("end")

    def _show_panel_placeholder(self):
        self.panel.configure(state="normal")
        self.panel.delete("1.0", "end")
        self.panel.insert("end", "Aquí verás cómo se recuperó la información:\nla pregunta limpia, los términos,\n"
                                 "los fragmentos elegidos como contexto\ny los tiempos de cada fase.", "empty")
        self.panel.configure(state="disabled")

    def _set_status(self, text, color=MUTED):
        self.status.configure(text=text, fg=color)

    def _set_mode(self, mode):
        self.mode = mode

    # ------------------------------------------------------------------ autocomplete
    def _on_key(self, event):
        if event.keysym in ("Return", "Tab", "Escape"):
            return
        self._set_suggestions(suggest(self.bot.index, self.entry.get()) if self.ready else [])

    def _on_tab(self, event):
        if self.suggestions:
            self._accept(self.suggestions[0])
        return "break"  # Tab no debe mover el foco

    def _set_suggestions(self, suggestions):
        self.suggestions = suggestions
        for child in self.chip_row.winfo_children():
            child.destroy()
        for s in suggestions:
            bg = BLUE if s.kind == "card" else "#245a49"
            FlatButton(self.chip_row, s.label, lambda s=s: self._accept(s), bg=bg, fg="white",
                       font=FONT_SMALL, padx=9, pady=3).pack(side="left", padx=(0, 6))

    def _accept(self, suggestion):
        text = apply(self.entry.get(), suggestion)
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.icursor("end")
        self.entry.focus_set()
        self._set_suggestions(suggest(self.bot.index, text))

    # ------------------------------------------------------------------ threads
    def _load_bot(self, factory):
        try:
            self.events.put(("ready", factory()))
        except Exception as exc:  # noqa: BLE001  se muestra en la ventana
            self.events.put(("load_error", exc))

    def _ask(self, question, mode):
        try:
            self.events.put(("reply", self.bot.answer(question, mode)))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("error", exc))

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                getattr(self, f"_on_{kind}")(payload)
        except queue.Empty:
            pass
        self._poll_id = self.root.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------ events
    def _on_ready(self, bot):
        self.bot, self.ready = bot, True
        self.send_btn.set_enabled(True)
        self._set_status("● listo", "#6fcf97")
        self._say("Listo. Pregúntame sobre jokers, tarot, planetas, vouchers, mazos o blinds de Balatro "
                  "(en inglés). Puedes escribir con errores: la búsqueda aproximada los corrige.", "sys")

    def _on_load_error(self, exc):
        self._set_status("● error", RED)
        self._say(f"No se pudo cargar el modelo: {exc}", "sys")

    def _on_error(self, exc):
        self.busy = False
        self.send_btn.set_enabled(True)
        self._set_status("● error", RED)
        self._say(f"Error al responder: {exc}", "sys")

    def send(self, question=None):
        if not self.ready or self.busy:
            return
        if question is not None:
            self.entry.delete(0, "end")
            self.entry.insert(0, question)
        question = self.entry.get().strip()
        if not question:
            return
        self.entry.delete(0, "end")
        self._set_suggestions([])
        self.busy = True
        self.send_btn.set_enabled(False)
        self._set_status("● pensando…", ORANGE)
        self._append(self.chat, [("TÚ\n", "user_hdr"), (f" {question} \n", "user")])
        self.chat.see("end")
        threading.Thread(target=self._ask, args=(question, self.mode), daemon=True).start()

    def _on_reply(self, reply):
        self.busy = False
        self.send_btn.set_enabled(True)
        self._set_status("● listo", "#6fcf97")
        ans, t = reply.answer, reply.timings_ms
        pieces = [(f"JOKIE · búsqueda {MODE_LABELS[reply.mode]}\n", "bot_hdr")]
        if ans.abstained:
            note = ""
            if reply.search.unmatched_terms:
                note = f"  (no aparece en el corpus: {', '.join(reply.search.unmatched_terms)})"
            pieces += [(f" {NO_ANSWER_ES}{note} \n", "abstain"),
                       (f"confianza en «no hay respuesta»: {ans.score:.2f} · {t['total'] / 1000:.1f} s\n", "meta"),
                       (ABSTAIN_HINT + "\n", "meta")]
        else:
            source = next((c.title for c in reply.context.chunks if c.id == reply.supporting_chunk), "?")
            pieces += [(f" {ans.text} \n", "bot"),
                       (f"confianza {ans.score:.2f} · fuente: {source} · {t['total'] / 1000:.1f} s\n", "meta")]
            if ans.score < LOW_CONFIDENCE:
                pieces.append((LOW_CONFIDENCE_NOTE + "\n", "warn"))
        self._append(self.chat, pieces)
        self.chat.see("end")
        self._render_panel(reply)

    # ------------------------------------------------------------------ panel
    def _render_panel(self, reply):
        s, ctx, ans, t = reply.search, reply.context, reply.answer, reply.timings_ms
        p = self.panel
        p.configure(state="normal")
        p.delete("1.0", "end")

        def put(text, tag):
            p.insert("end", text, tag)

        put("PREGUNTA ENVIADA AL MODELO\n", "h")
        put(reply.prompt_question + "\n", "v")
        for before, after in reply.clean.corrections:
            put(f"corrección: {before} → {after}\n", "fix")
        if reply.rewritten:
            put("reformulada con las etiquetas de la ficha de la wiki\n", "k")

        put(f"\nBÚSQUEDA {MODE_LABELS[reply.mode].upper()}\n", "h")
        put(f"términos: {', '.join(s.terms) or '—'}\n", "v")
        if s.expanded:
            put(f"añadidos por equivalencias: {', '.join(s.expanded)}\n", "v")
        for term, variants in s.variants.items():
            put(f"variantes de «{term}»: " + ", ".join(f"{w} ({sim})" for w, sim, _ in variants) + "\n", "v")
        if s.names:
            put(f"cartas detectadas: {', '.join(s.names)}\n", "v")
        if s.unmatched_terms:
            put(f"sin coincidencia posible: {', '.join(s.unmatched_terms)}\n", "fix")

        put(f"\nCONTEXTO · {len(ctx.chunks)} fragmentos · {ctx.words} palabras\n", "h")
        spans = {cid: (a, b) for a, b, cid in ctx.spans}
        for rank, chunk in enumerate(ctx.chunks, 1):
            put(f"[{rank}] {chunk.title} · puntaje {chunk.score} · fragmento {chunk.id}\n", "chunk")
            a, b = spans[chunk.id]
            if not ans.abstained and a <= ans.start < b:
                rs, re_ = ans.start - a, min(ans.end, b) - a
                put(chunk.text[:rs], "text")
                put(chunk.text[rs:re_], "hl")
                put(chunk.text[re_:] + "\n", "text")
            else:
                put(chunk.text + "\n", "text")
        if not ctx.chunks:
            put("la búsqueda no devolvió fragmentos\n", "k")

        put("\nTIEMPOS\n", "h")
        put(f"limpieza {t['clean']:.0f} ms · búsqueda {t['retrieval']:.0f} ms · contexto "
            f"{t['context']:.0f} ms\nmodelo {t['model']:.0f} ms · total {t['total']:.0f} ms\n", "time")
        p.configure(state="disabled")
        p.see("1.0")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
