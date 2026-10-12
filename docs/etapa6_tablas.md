# Etapa 6: tablas generadas desde los datos medidos
_Generado por `src/figures.py`; no editar a mano._

## 1. Exacta vs aproximada (26 preguntas: 23 con respuesta, 3 sin ella)

| Metrica | Exacta (KMP) | Aproximada |
|---|---|---|
| Tiempo medio de busqueda (ms) | 1104.8 | 15.3 |
| Tiempo mediano de busqueda (ms) | 843.1 | 11.6 |
| Fragmentos examinados (media) | 2249 | 966 |
| Fragmento con la respuesta en el puesto 1 | 78% | 100% |
| ... entre los 3 primeros | 78% | 100% |
| MRR | 0.785 | 1.0 |
| El contexto elegido contiene la respuesta | 18/23 | 23/23 |
| Respuestas correctas del modelo | 15/23 | 22/23 |
| Respuestas erroneas con el contexto correcto presente | 2 | 0 |
| Abstenciones indebidas | 6 | 1 |
| Abstenciones correctas (sin respuesta en el corpus) | 3/3 | 3/3 |
| Respuestas inventadas | 0 | 0 |
| Tiempo medio del modelo (ms) | 1373.7 | 1452.7 |
| Tiempo medio total por pregunta (ms) | 2452.2 | 1478.8 |

## 2. Aislando cada pieza (recuperacion, etapa 4)

| Configuracion | hit@1 | hit@3 | MRR | Tiempo medio (ms) | Fragmentos examinados |
|---|---|---|---|---|---|
| exact_kmp | 0.52 | 0.56 | 0.596 | 926.7 | 2249 |
| exact_kmp_lex | 0.78 | 0.78 | 0.785 | 1104.8 | 2249 |
| exact_index | 0.78 | 0.78 | 0.785 | 3.0 | 819 |
| approx_nolex | 0.65 | 0.78 | 0.765 | 13.8 | 783 |
| approx | 1.00 | 1.00 | 1.0 | 15.3 | 966 |

## 3. Respuestas correctas del modelo por tipo de pregunta

| Tipo | n | Exacta | Aproximada |
|---|---|---|---|
| direct | 11 | 9 | 11 |
| inflection | 1 | 0 | 0 |
| no_name | 2 | 1 | 2 |
| symbol | 2 | 2 | 2 |
| synonym | 3 | 3 | 3 |
| typo | 4 | 0 | 4 |

## 4. Caso por caso (puesto del fragmento con la respuesta: exacta / aproximada)

| Caso | Tipo | Pregunta | Puesto exacta | Puesto aprox. | Resultado exacta | Resultado aprox. |
|---|---|---|---|---|---|---|
| DIFERENCIA | direct | What does The Fool tarot card do? | 1 | 1 | wrong_with_support | correct |
| DIFERENCIA | direct | What does the Overstock voucher do? | 1 | 1 | wrong_with_support | correct |
| DIFERENCIA | no_name | Which joker retriggers cards held in hand? | 18 | 1 | abstained_no_support | correct |
| DIFERENCIA | typo | What does Blueprnt do? | None | 1 | abstained_no_support | correct |
| DIFERENCIA | typo | How do I unlock Hologrm? | None | 1 | abstained_no_support | correct |
| DIFERENCIA | typo | What rarity is Brainstrom? | None | 1 | abstained_no_support | correct |
| DIFERENCIA | typo | What does Fibonaci do? | None | 1 | abstained_no_support | correct |
| similar | direct | What rarity is Blueprint? | 1 | 1 | correct | correct |
| similar | direct | How do I unlock Brainstorm? | 1 | 1 | correct | correct |
| similar | direct | What does Mime do? | 1 | 1 | correct | correct |
| similar | direct | What does Cavendish do? | 1 | 1 | correct | correct |
| similar | direct | What is the effect of Fibonacci? | 1 | 1 | correct | correct |
| similar | direct | What rarity is Chicot? | 1 | 1 | correct | correct |
| similar | direct | What does Mercury do? | 1 | 1 | correct | correct |
| similar | direct | How do I unlock Mr. Bones? | 1 | 1 | correct | correct |
| similar | direct | What does the Egg joker do? | 1 | 1 | correct | correct |
| similar | inflection | Which jokers retrigger played cards? | 1 | 1 | abstained_with_support | abstained_with_support |
| similar | no_answer | Does the game have a joker called Pikachu? | None | None | correct_abstention | correct_abstention |
| similar | no_answer | What is the capital of France? | None | None | correct_abstention | correct_abstention |
| similar | no_answer | What is the price of the Superman joker? | None | None | correct_abstention | correct_abstention |
| similar | no_name | Which joker copies the ability of the leftmost joker? | 1 | 1 | correct | correct |
| similar | symbol | Which joker gives +15 Mult but can be destroyed at end of round? | 1 | 1 | correct | correct |
| similar | symbol | Which joker gives X3 Mult and has a 1 in 1000 chance of being destroyed? | 1 | 1 | correct | correct |
| similar | synonym | How much does Hologram cost? | 1 | 1 | correct | correct |
| similar | synonym | How much does Mr. Bones cost? | 1 | 1 | correct | correct |
| similar | synonym | How much is Brainstorm worth when sold? | 1 | 1 | correct | correct |

## 5. Escalado con el tamano de la coleccion (ms por pregunta, media de 8)

| Escala | Fragmentos | Caracteres | Indice (ms) | Exacta KMP | Exacta indice | Aproximada |
|---|---|---|---|---|---|---|
| 0.25x | 562 | 313,340 | 525 | 275.39 | 1.54 | 7.73 |
| 0.5x | 1124 | 625,175 | 1562 | 596.28 | 2.14 | 9.97 |
| 1x | 2249 | 1,191,341 | 2366 | 1070.54 | 7.07 | 13.78 |
| 2x | 4498 | 2,382,683 | 4274 | 2083.06 | 7.78 | 20.8 |
| 4x | 8996 | 4,765,367 | 8088 | 4154.11 | 19.09 | 33.59 |

_Las escalas 2x y 4x repiten los fragmentos con ids nuevos: son sinteticas._

## 6. Efecto de la seleccion de contexto (recuperacion aproximada fija)

| Configuracion | Correctas | Erroneas | Se abstuvo | Contexto con la respuesta | Abst. correctas | Inventadas | Palabras de contexto | Modelo (ms) |
|---|---|---|---|---|---|---|---|---|
| top-1 fragmento | 22/23 | 1 | 0 | 23/23 | 3/3 | 0 | 91.7 | 443 |
| top-2 fragmentos | 22/23 | 0 | 1 | 23/23 | 3/3 | 0 | 184.1 | 870 |
| top-3 fragmentos | 21/23 | 1 | 1 | 23/23 | 3/3 | 0 | 270.5 | 1376 |
| top-4 (configuracion por defecto) | 22/23 | 0 | 1 | 23/23 | 3/3 | 0 | 286.2 | 1412 |
| top-6, hasta 600 palabras | 21/23 | 1 | 1 | 23/23 | 3/3 | 0 | 535.1 | 2659 |
| top-4 sin filtro de redundancia | 22/23 | 0 | 1 | 23/23 | 3/3 | 0 | 286.2 | 1377 |
| presupuesto 100 palabras | 10/23 | 3 | 10 | 10/23 | 3/3 | 0 | 80.9 | 426 |
| presupuesto 200 palabras | 22/23 | 0 | 1 | 23/23 | 3/3 | 0 | 168.4 | 654 |
| defecto + 2 fragmentos al azar | 20/23 | 1 | 2 | 23/23 | 3/3 | 0 | 478.5 | 2642 |
| defecto + 4 fragmentos al azar | 19/23 | 1 | 3 | 23/23 | 3/3 | 0 | 661.2 | 3332 |
