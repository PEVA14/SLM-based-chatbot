# Jokie: un chatbot sobre los jokers de Balatro con algoritmos de cadenas y un modelo de lenguaje

Proyecto de Algoritmos (TEC): **recuperación de información para un asistente basado en un
modelo de lenguaje**. Dada una pregunta, el programa busca en una colección de documentos
los fragmentos más relacionados con algoritmos clásicos de cadenas (KMP, Z-function, Trie,
distancia de edición, n-gramas con Jaccard), arma un contexto con los mejores y se lo da a un
modelo preentrenado de Hugging Face, que responde o dice que no sabe.

- **Corpus:** la wiki de Balatro (jokers, tarot, planetas, vouchers, mazos, blinds…):
  364 páginas, ~210 mil palabras, 2,249 fragmentos.
- **Modelo:** [`deepset/roberta-base-squad2`](https://huggingface.co/deepset/roberta-base-squad2),
  extractivo y en inglés. No se entrena: solo elige el tramo del contexto que responde la
  pregunta, o se abstiene.
- **Interfaz:** ventana en Tkinter con chat, panel de recuperación y autocompletado con Trie.

> Las preguntas y las respuestas son en inglés, porque el corpus y el modelo lo son. La
> interfaz está en español.

## Cómo funciona

```
pregunta ─► limpieza ─► búsqueda ─► fragmentos ─► selección de contexto ─► modelo ─► respuesta
            (typos)     exacta o     ordenados     (sin redundancia,       (con "no sé")
                        aproximada   por puntaje    límite de palabras)
```

1. **Limpieza:** corrige errores de ortografía en el texto original ("Blueprnt" → "Blueprint") y
   reformula plantillas de pregunta con las etiquetas de la wiki ("What does X do?" →
   "What is the effect of X?").
2. **Búsqueda:** dos modos intercambiables, para compararlos.
   - *Exacta:* KMP y Z-function recorren el corpus buscando palabras completas.
   - *Aproximada:* Levenshtein sobre un Trie y trigramas con Jaccard encuentran variantes
     (typos, plurales); usa un índice invertido.
3. **Contexto:** se eligen hasta 4 fragmentos (máximo 320 palabras) sin repetir contenido.
4. **Modelo:** devuelve el tramo de texto que responde, con su confianza, o se abstiene.

## Instalación y uso

**En macOS usa Python 3.12 de Homebrew, que trae Tk 9.** El Python 3.9 que viene con Xcode trae
Tk 8.5.9, y en macOS 26 la ventana abre pero **no se pinta** (queda en blanco) y llamar a `update()`
la cuelga.

```bash
brew install python@3.12 python-tk@3.12
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` fija `torch==2.8.0` y `transformers==4.57.6`, las versiones probadas.
**No actualices `transformers` a la serie 5.x:** eliminó la tarea `question-answering` y el modelo
no carga. Probado con Python 3.12.15 / Tk 9.0.4 en macOS 26; no se ha probado en Linux ni en Windows.

Los datos ya están en `data/`, así que **no hace falta descargar nada de la wiki** para usar
la aplicación. Abrir la ventana:

```bash
python main.py
```

- **La primera vez** se descarga el modelo (~475 MB) a la caché de Hugging Face.
- **El arranque tarda unos segundos** (índice, trigramas y modelo); la ventana lo avisa y bloquea
  el botón *Enviar* hasta estar lista.
- **Cada respuesta tarda menos de 1 s en CPU** en Python 3.12 (mucho más con el Python 3.9 de Xcode);
  corre en un hilo aparte y la ventana no se congela.
- En la ventana: escribe una pregunta o pulsa un ejemplo; las sugerencias del Trie aparecen
  bajo el cuadro de texto (clic o **Tab** para aceptar la primera); el interruptor
  *APROXIMADA / EXACTA* cambia el buscador; el panel de la derecha muestra cómo se recuperó
  la información, con la respuesta resaltada en el fragmento que la respalda. Si el modelo
  contesta con confianza menor a 0.15, el chat añade un aviso de baja confianza (no oculta la
  respuesta: el puntaje no es una probabilidad calibrada).

Sin ventana, desde la terminal:

```bash
python src/pipeline.py "What rarity is Blueprint?"      # flujo completo, en ambos modos
python src/search_exact.py "How do I unlock Hologram?"   # solo la búsqueda exacta
python src/search_approx.py "What does Blueprnt do?"     # solo la búsqueda aproximada
```

## Algoritmos implementados

n = caracteres del texto, m = del patrón, T = del corpus, k = términos de la pregunta,
L = longitud de una palabra, V = tamaño del vocabulario.

| Etapa | Algoritmo | Archivo | Complejidad |
|---|---|---|---|
| Preprocesamiento | Normalización, tokenización, stopwords (conservando `+4`, `x1.5`, `$10`) | [preprocess.py](src/preprocess.py) | O(n) |
| Índice | **Trie** con frecuencias (vocabulario y nombres de carta) | [trie.py](src/trie.py) | insertar/buscar O(L) |
| Índice | **Tabla hash invertida** término → fragmentos | [index.py](src/index.py) | construir O(N) tokens |
| Búsqueda exacta | **KMP** (función de fallo) | [exact.py](src/exact.py) | O(n + m) |
| Búsqueda exacta | **Z-function** | [exact.py](src/exact.py) | O(n + m) |
| Búsqueda aproximada | **Levenshtein sobre el Trie** (una fila de la tabla por nodo, con poda) | [trie.py](src/trie.py) | O(nodos visitados · L), muy por debajo de O(V · L) |
| Búsqueda aproximada | **Trigramas + Jaccard** (índice hash trigrama → palabras) | [approx.py](src/approx.py) | construir O(Σ L); consulta O(Σ tamaño de cubetas) |
| Autocompletado | Recorrido del Trie por prefijo, ordenado por frecuencia | [autocomplete.py](src/autocomplete.py) | O(m + S), S = subárbol |
| Contexto | Selección voraz con filtro de redundancia (Jaccard) | [context.py](src/context.py) | O(h · c · t) |
| Puntuación | BM25 (idf + saturación de frecuencia) | [scoring.py](src/scoring.py) | O(ocurrencias) |

La explicación de las técnicas de diseño, las complejidades y las decisiones está en los
comentarios de cada módulo.

## Resultados

Medidos sobre 26 preguntas (23 con respuesta en el corpus y 3 sin ella), con el mismo selector
de contexto, el mismo modelo y el mismo prompt:

| | Búsqueda exacta | Búsqueda aproximada |
|---|---|---|
| Tiempo medio de búsqueda | 1,105 ms | 15 ms |
| El contexto contiene la respuesta | 18 de 23 | 23 de 23 |
| Respuestas correctas del modelo | 15 de 23 | 22 de 23 |
| Abstenciones correctas (sin respuesta en el corpus) | 3 de 3 | 3 de 3 |
| Respuestas inventadas | 0 | 0 |

El tiempo de la exacta crece linealmente con el tamaño del corpus; el de la aproximada, mucho
menos. **Antes de citar estas cifras, lee la sección de limitaciones.** El análisis completo
está en [docs/etapa6_analisis.md](docs/etapa6_analisis.md), las tablas en
[docs/etapa6_tablas.md](docs/etapa6_tablas.md) y las gráficas en `docs/figures/`.

## Limitaciones conocidas

- **La evaluación es optimista.** Las 26 preguntas las escribió quien desarrolló el sistema, y
  las equivalencias de dominio y la reformulación del prompt se ajustaron viendo cómo fallaba
  el sistema en ese mismo conjunto. El 22 de 23 no es una precisión esperada en preguntas
  nuevas. Con 23 preguntas, una sola equivale a 4.3 puntos porcentuales.
- **Cómo le va con preguntas que nadie ajustó** (`python src/eval_generated.py`): con 225 preguntas
  generadas mecánicamente desde las fichas (rareza, precio, efecto y desbloqueo de 60 cartas al
  azar) acierta el 90 % y se abstiene el 4 %. Con preguntas libres es mucho peor: en una prueba
  informal de 21 preguntas (listas, conteos, opiniones, comparaciones, "Tell me about X") se
  abstuvo en 10. Funciona bien para datos de una carta concreta; no para conteos, opiniones ni
  descripciones abiertas, porque el modelo es extractivo.
- **Dos componentes son heurísticas escritas a mano, no algoritmos de cadenas**
  ([lexicon.py](src/lexicon.py)): las equivalencias ("cost" → "buy price") y las plantillas
  que reformulan la pregunta. Funcionan en este corpus y no se transfieren a otro dominio.
- **La comparación de velocidad mezcla algoritmo con infraestructura:** la exacta recorre el
  corpus completo y la aproximada consulta un índice. Con el mismo índice, la exacta cuesta
  3 ms. KMP, además, está en Python puro.
- **El modelo es extractivo:** no genera texto, no hace listas ni síntesis ("Which jokers
  retrigger played cards?" se abstiene) y es sensible a cómo se redacta la pregunta.
- **Las preguntas de lista fallan:** "What are the 5 legendary jokers" necesita 5 nombres de 5
  fichas distintas y el modelo extractivo solo puede devolver un tramo; además la búsqueda llena el
  contexto con fragmentos de *The Soul*. Responde "The Soul Spectral card" con confianza 0.05.
- **La búsqueda no sabe abstenerse:** siempre devuelve fragmentos, incluso para preguntas sin
  respuesta; esa decisión la toma el modelo.
- **Tk en macOS:** con el Tk 8.5.9 del Python de Xcode la ventana no se pinta y `update()` se
  cuelga; por eso se recomienda Python 3.12 con Tk 9. Además, Tk 9 no tolera crear una segunda
  ventana raíz tras destruir la primera, y las pruebas de la ventana comparten una sola.

## Reproducir los datos y los resultados

Todo es opcional, porque `data/` ya trae el resultado de cada paso. Los comandos se corren desde
la raíz del proyecto, en este orden; las evaluaciones tardan varios minutos cada una (usan el modelo
o barren el corpus completo):

```bash
python src/scrape.py        # descarga la wiki por su API (~740 peticiones, con pausa entre ellas)
python src/chunking.py      # divide en fragmentos -> data/chunks.json
python src/build_index.py   # estadísticas y escalado del índice -> data/index_stats.json
python src/eval_stage3.py   # búsqueda exacta: KMP vs Z vs fuerza bruta
python src/eval_stage4.py   # exacta vs aproximada, aislando cada pieza
python src/eval_stage5.py   # flujo completo con el modelo, 26 preguntas
python src/eval_stage6.py   # escalado de la colección y selección de contexto (el más lento)
pip install -r requirements-report.txt
python src/figures.py       # gráficas y tablas -> docs/
```

`src/eval_questions.py` define las 26 preguntas y verifica contra el corpus que cada respuesta
esperada existe (`python src/eval_questions.py`).

## Pruebas

```bash
python -m unittest discover -s tests
```

90 pruebas (de segundos a ~1 min según el Python). Las de la ventana abren y cierran ventanas ocultas; usan un modelo falso, así
que no cargan los 475 MB. Si Tk no está disponible, esas pruebas se omiten.

## Estructura

```
main.py                    abre la ventana
src/
  scrape.py  chunking.py   descarga de la wiki y división en fragmentos
  preprocess.py            normalización y tokenización
  trie.py  index.py        Trie (con búsqueda aproximada) e índice invertido
  exact.py                 KMP, Z-function y fuerza bruta
  approx.py                Levenshtein, trigramas y Jaccard
  scoring.py               fórmula de puntuación (BM25)
  search_exact.py          recuperación exacta
  search_approx.py         recuperación aproximada
  lexicon.py               equivalencias y reformulación de preguntas (heurísticas)
  query_clean.py           corrección de typos en la pregunta
  context.py               selección del contexto
  qa_model.py  pipeline.py modelo de lenguaje y flujo completo
  autocomplete.py  gui.py  autocompletado con Trie y ventana
  eval_*.py  figures.py    evaluaciones y figuras del reporte
tests/                     pruebas unitarias
data/                      corpus, fragmentos, índice y resultados medidos (JSON)
docs/                      análisis de la etapa 6, tablas y figuras
```

## Datos y licencias

- **Corpus:** texto de la [Balatro Wiki](https://balatrowiki.org), bajo
  [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/). `data/` contiene
  texto derivado de ella, por lo que se comparte bajo la misma licencia: **uso no comercial**,
  con atribución y compartiendo igual.
- **Modelo:** `deepset/roberta-base-squad2`, licencia CC-BY-4.0. No se incluye en el
  repositorio; se descarga de Hugging Face al ejecutarlo.
- Balatro es un juego de LocalThunk. Este es un proyecto académico, sin afiliación.
