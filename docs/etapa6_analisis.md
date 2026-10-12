# Etapa 6: comparación y análisis

Borrador de análisis para el reporte. Todas las cifras salen de `data/stage4_results.json`,
`stage5_results.json` y `stage6_results.json`; las tablas completas están en
[etapa6_tablas.md](etapa6_tablas.md) y las figuras en `docs/figures/`.

**Alcance de la comparación.** Se comparan dos buscadores sobre las mismas 26 preguntas
(23 con respuesta en el corpus, 3 sin ella), con el mismo selector de contexto, el mismo
modelo y el mismo prompt:

- **Exacta:** barrido KMP/Z por palabra completa + puntuación BM25 (etapa 3), con las
  equivalencias de dominio.
- **Aproximada:** Levenshtein sobre el Trie + trigramas con Jaccard + índice invertido
  (etapa 4), con las mismas equivalencias.

## 1. Resultados por estrategia

| | Exacta | Aproximada |
|---|---|---|
| Tiempo medio de búsqueda | 1,105 ms (mediana 843) | 15 ms (mediana 12) |
| Fragmentos examinados (media) | 2,249 (todos) | 966 |
| Fragmento con la respuesta en el puesto 1 | 78 % | 100 % |
| El contexto elegido contiene la respuesta | 18 de 23 | 23 de 23 |
| Respuestas correctas del modelo | 15 de 23 | 22 de 23 |
| Abstenciones indebidas | 6 | 1 |
| Abstenciones correctas (sin respuesta en el corpus) | 3 de 3 | 3 de 3 |
| Respuestas inventadas | 0 | 0 |

## 2. Casos donde ambas son similares y donde difieren

**Similares (19 de 26 preguntas, mismo resultado y mismo puesto).** Preguntas con el
nombre exacto de la carta bien escrito ("What rarity is Blueprint?", "What does Mercury
do?"), las de sinónimo ("How much does Hologram cost?"), las de símbolos de juego ("X3 Mult
… 1 in 1000") y las tres sin respuesta en el corpus. Cuando la pregunta usa las palabras de
la wiki, la búsqueda exacta ya pone el fragmento correcto de primero y la aproximada no
aporta nada.

**Diferencia importante (7 de 26):**

- **Typos (4 de 4).** Con "Blueprnt", "Hologrm", "Brainstrom" o "Fibonaci" la exacta no
  encuentra la carta: el modelo se abstiene en las cuatro (0 aciertos), y la aproximada las
  resuelve todas (4 aciertos). La palabra mal escrita simplemente no existe en el corpus.
- **Plural sin nombre de carta.** "Which joker retriggers cards held in hand?": el
  fragmento correcto queda en el puesto 18 con la exacta (por "retriggers" frente a
  "retrigger") y en el 1 con la aproximada.
- **Contexto que confunde a pesar de tener la respuesta (2 de 26).** Para "What does The
  Fool tarot card do?" el contexto exacto incluyó la ficha de *Magic Deck*, cuyo efecto
  menciona a The Fool, y el modelo respondió con ese texto. Para "What does the Overstock
  voucher do?" el contexto exacto tenía tres fragmentos de la página de Overstock y el
  modelo respondió con el de rerolls; el aproximado tenía esos mismos tres más uno de la
  página Shop, y respondió bien. **El fragmento correcto estaba en el puesto 1 en ambos
  casos**: lo que cambió la respuesta fue la composición del resto del contexto.

## 3. ¿Qué algoritmo ofrece búsquedas más rápidas?

La aproximada: 15 ms contra 1,105 ms por pregunta. Pero **esa diferencia no es mérito de
Levenshtein ni de los trigramas**, y hay que decirlo así:

- La exacta *recorre el corpus completo* por cada término (1.19 millones de caracteres);
  la aproximada consulta la tabla hash invertida y solo toca los fragmentos candidatos.
- Con el mismo índice, la búsqueda exacta cuesta 3 ms (media de las 26 preguntas): la
  tolerancia a errores cuesta unas 5 veces más (15 ms), que es su costo real.
- KMP está implementado en Python puro. En el mismo corpus, el `str.count` del propio
  lenguaje (escrito en C) tardó 3 ms contra 300 ms de KMP para un patrón. Buena parte de
  la lentitud de KMP es el intérprete, no el algoritmo.

Entre los algoritmos de coincidencia exacta, **KMP fue unas 4 veces más rápido que Z**
(≈0.3 s contra ≈1.2 s por término): ambos son O(n+m), pero Z construye un arreglo del
tamaño de patrón más texto. La fuerza bruta quedó muy cerca de KMP (≈0.35 s) porque el
texto natural casi no produce coincidencias parciales largas, que es lo que haría
degenerar a O(n·m). Sobre el Trie, la búsqueda con distancia de edición fue de 4 a 29
veces más rápida que comparar contra todo el vocabulario, con resultados idénticos.

## 4. ¿Qué método recupera información más útil?

La aproximada, con una salvedad de evidencia (sección 8). Colocó el fragmento con la
respuesta en el puesto 1 en el 100 % de las preguntas (78 % la exacta) y el contexto que
armó contenía la respuesta en 23 de 23 casos (18 de 23). Aislando cada pieza (etapa 4):

| Configuración | hit@1 | Tiempo (ms) |
|---|---|---|
| Exacta (KMP), sin equivalencias | 0.52 | 927 |
| Exacta (KMP) + equivalencias | 0.78 | 1,105 |
| Aproximada sin equivalencias | 0.65 | 14 |
| Aproximada + equivalencias | 1.00 | 15 |

Las equivalencias de dominio ("cost" → "buy price") arreglan los sinónimos; la tolerancia a
errores arregla los typos y los plurales; las dos juntas arreglan ambos. Ninguna de las dos
habría llegado sola.

## 5. ¿Cómo afecta el tamaño de la colección al tiempo de búsqueda?

Medido de 0.25× a 4× el corpus (las escalas mayores que 1× repiten los fragmentos con ids
nuevos, así que son sintéticas y sirven para el tiempo, no para la calidad). Figura
`escalado.png`:

| Caracteres | Exacta KMP | Exacta con índice | Aproximada | Construir el índice |
|---|---|---|---|---|
| 0.31 M | 275 ms | 1.5 ms | 7.7 ms | 0.5 s |
| 1.19 M | 1,071 ms | 7.1 ms | 13.8 ms | 2.4 s |
| 4.77 M | 4,154 ms | 19.1 ms | 33.6 ms | 8.1 s |

- **El barrido KMP es lineal:** 15 veces más texto, 15 veces más tiempo (O(k·(T+m)) por
  consulta).
- **La aproximada crece mucho menos:** 15 veces más texto, 4.3 veces más tiempo. Una parte
  de su costo (recorrer el Trie para buscar variantes) no depende del tamaño de la
  colección; solo crece la parte de puntuar las listas de fragmentos.
- **El índice tiene un costo de construcción lineal** (0.5 s a 8.1 s), que se paga una vez.
  Con el corpus actual se compensa en unas 3 consultas (2.4 s de construcción frente a
  ≈1 s ahorrado por consulta).
- Con la aproximada, **el modelo domina el tiempo total**: 1,453 ms contra 15 ms de
  búsqueda (98 %). Con la exacta, la búsqueda era el 43 % del total.

## 6. ¿Cómo afecta la selección del contexto a la respuesta del modelo?

Con la recuperación aproximada fija se varió cómo se arma el contexto. Figura
`seleccion_contexto.png`:

- **El contexto tiene que contener la respuesta, y a veces no cabe.** Los fragmentos con la
  respuesta miden entre 51 y 132 palabras (13 de los 22 con página esperada pasan de 100).
  Con un presupuesto de 100 palabras esos no entran: el contexto contiene la respuesta solo
  en 10 de 23 preguntas, las respuestas correctas caen de 22 a 10 y el modelo se abstiene 10
  veces. Con 200 palabras vuelve a 22.
- **Más fragmentos no mejoraron nada en este conjunto.** Con 1, 2 o 4 fragmentos el
  resultado fue 22 de 23; con 3 o 6, 21. Esas diferencias son una pregunta y no son
  concluyentes. Lo que sí cambia es el costo: el modelo tarda 443 ms con 92 palabras de
  contexto y 2,659 ms con 535 (≈5 ms por palabra). Este resultado depende de que la
  búsqueda ponga la ficha en el puesto 1; con una recuperación peor, un solo fragmento no
  alcanzaría.
- **El ruido resta aciertos, sobre todo por abstención.** Añadir 2 fragmentos al azar de
  otras páginas baja de 22 a 20 aciertos y añadir 4, a 19; las abstenciones suben de 1 a 2
  y a 3, y aparece una respuesta errónea (0 en la configuración por defecto). El efecto
  principal del ruido es que el modelo, con su opción de "no hay respuesta", se vuelve más
  conservador.
- **El filtro de redundancia no tuvo efecto medible** (22 de 23 con y sin él): en este
  corpus los fragmentos vecinos casi no se repiten.
- **La composición importa, no solo la presencia** (los casos de The Fool y Overstock de la
  sección 2): un fragmento *relacionado pero de otra entidad* o de otro subtema de la misma
  página puede desplazar a la respuesta correcta, incluso cuando esta está en el puesto 1.
  El prompt reformulado ("What is the effect of X?") empuja al modelo hacia cualquier
  fragmento que tenga "Effect:" y mencione a X.

## 7. Ventajas y limitaciones de los algoritmos clásicos de cadenas para alimentar a un modelo

**Ventajas**

- *Explicables y verificables.* Cada fragmento llega con sus términos coincidentes y su
  puntuación; se puede decir por qué entró al contexto.
- *Sin entrenamiento, sin embeddings y sin GPU.* Todo el pipeline de recuperación corre en
  milisegundos con un índice de 11 MB.
- *Precisos con símbolos y números.* "+15 Mult", "X3" o "$7" se buscan como cadenas, algo
  en lo que la búsqueda semántica suele ser débil.
- *Los problemas de ortografía tienen solución algorítmica:* el Trie con distancia de
  edición corrige typos y plurales con garantías claras de complejidad.

**Limitaciones**

- *No entienden el significado.* Sin la lista manual de equivalencias, "cost" no encuentra
  "Buy Price". Esa lista es una heurística escrita a mano, no un algoritmo de cadenas, y no
  se transfiere a otro dominio.
- *No pueden abstenerse.* Para las tres preguntas sin respuesta devolvieron fragmentos
  igual; la decisión de decir "no sé" la tomó el modelo.
- *El ranking no distingue entidad de mención.* La ficha de *Magic Deck* mencionaba a The
  Fool y compitió con la de The Fool.
- *Un modelo extractivo no hace listas ni síntesis.* "Which jokers retrigger played cards?"
  tuvo la respuesta en el puesto 1 con ambos buscadores y el modelo se abstuvo en los dos,
  porque necesita nombrar varios jokers y solo puede señalar un tramo de texto.
- *El modelo es sensible a la formulación de la pregunta* ("What does X do?" fallaba y
  "What is the effect of X?" no), lo que obligó a reformular el prompt.

## 8. Limitaciones de este análisis (declararlas en el reporte)

1. **El conjunto de evaluación no es independiente.** Las 26 preguntas las escribió quien
   desarrolló el sistema, y las equivalencias, la reformulación del prompt y varios umbrales
   se ajustaron después de ver cómo fallaba el sistema en ese mismo conjunto. El 22 de 23
   de la aproximada es una cota optimista, no una precisión esperada en preguntas nuevas.
2. **Son pocas preguntas.** Con n = 23, una pregunta equivale a 4.3 puntos porcentuales;
   las diferencias de una sola pregunta (por ejemplo 22 contra 21) no son concluyentes.
   Solo las diferencias grandes lo son (typos: 4 contra 0; presupuesto de 100 palabras:
   10 contra 22).
3. **La comparación de velocidad mezcla algoritmo con infraestructura** (barrido contra
   índice) y con el lenguaje (KMP en Python puro). Se separaron con la configuración
   "exacta con índice" y con la comparación contra `str.count`.
4. **Las escalas 2× y 4× del corpus son sintéticas.** Los tiempos sirven para ver la
   tendencia; la calidad no se midió a esas escalas.
5. **Una sola máquina y una sola ejecución** para la búsqueda exacta (las rápidas se
   repitieron 3 o 5 veces y se tomó la mediana).
