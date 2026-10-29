# Estado de validación de Trading

**Actualizado:** 29 de octubre de 2026 · motor 0.35.0 · precios al 28-oct.
**Estado:** escenarios condicionales de investigación; capacidad predictiva y
ventaja económica sin acreditar. El [historial hasta 0.32.0](historial-validacion-hasta-0.32.md)
conserva los cambios y cifras anteriores.

## Evidencia vigente

| Medida | Resultado | Alcance |
|---|---|---|
| GJR-t aceptados | 20/260; 65 ajustes con ν en 4,0 | Cribado histórico de riesgo; no valida la cartera ni convierte los ajustes en el borde en aceptados |
| Registro diario | 3 sesiones selladas; 2 puntuadas; 520 activo-días | Referencias estadísticas; aún no evaluable (20 sesiones y 500 activo-días) |
| Pronósticos a doce meses | 4 sellados; ninguno vencido | No hay una rentabilidad prospectiva madura |
| Núcleo de precios exacto 1.0.0 | 2 sellos; 0 orígenes maduros a 1/5/21 sesiones | No se suma la evidencia de otros modelos ni se cuentan activos correlacionados como orígenes independientes |
| Eventos verificados | 0 | GARCH-X y saltos informativos siguen bloqueados |
| IC reconstruido del proxy anual | 0,037 a 252 sesiones; 36 orígenes | Intervalo por bloques [−0,082; 0,082]; no valida el IC declarado de 0,05 |
| IC de rangos con fórmula TTM actual reconstruida | 0,087 a 252 sesiones; 36 orígenes, solo tres sin solapamiento | Banda descriptiva [0,027; 0,134]; ventaja frente a BPA/precio sin resolver, vintages y catálogo históricos sin verificar |
| Candidato de oro con factores rezagados | 34 orígenes; R² fuera de muestra −0,057 frente a media histórica | Empeora el MSE un 5,7%; permanece en sombra |

## Fiabilidad del cálculo y de los pesos (0.34.0)

La auditoría conserva código y datos de 0.33.1 en
[`auditorias/fiabilidad-0.33.1.json`](auditorias/fiabilidad-0.33.1.json).
Con datos y mandato fijos, tres búsquedas base cambiaban entre el 55% y el
75% del capital. Añadir un activo de peso y riesgo cero cambiaba 2.028.000
coordenadas: la mediana de una cartera fija pasaba de 4,95% a 4,31% y el CVaR
de 9,11% a 9,72%. Es un defecto de acoplamiento de aleatoriedad, corregido
con flujos separados y orden canónico. También se corrige la dependencia de
la frecuencia del informe y se verifica que un prefijo diario coincide con
el mismo proceso completo.

La exponencial de una Student-t no admite el centrado gaussiano que usaba
el motor. El núcleo 1.0.0 usa innovaciones gaussianas condicionales de
precios. La estimación GJR con verosimilitud t permanece; la Student se
reserva para estrés de riesgo, con ν ajustado o ν=4 declarado donde hay
fallback. No publica medias económicas ni utilidad de ese estrés. Es una
corrección matemática: no una nueva ley predictivamente validada ni motivo
para agrupar evidencia de núcleos distintos.

La selección ya contrasta todas las candidatas descubiertas bajo los cinco
modelos y añade combinaciones sencillas de fondos elegibles. Se separan
cribado, selección y una única confirmación. Los riesgos incluyen cotas de
muestreo: KL para probabilidades y aproximación de influencia para CVaR.
Se informa el conjunto cuyos rankings no se resuelven, sin llamarlo
estadísticamente equivalente. Desde 0.35.0, el desempate por rotación exige una cota de pérdida económica
dentro del umbral del mandato; la incertidumbre sola no lo habilita. Se
conserva el objetivo del peor modelo, sin garantizar un óptimo global.

El [protocolo de confianza](criterios-confianza.md) distingue corrección del
software, admisibilidad condicional de una decisión y evidencia predictiva.
**La tercera sigue sin acreditar.** La auditoría detallada de esta versión
queda en [`auditoria-fiabilidad-0.34.md`](auditoria-fiabilidad-0.34.md).

### Comprobación adicional en 0.34.1

El comparador legado podía dejar inactivo el estrés Student y conservar su
ley gaussiana/Merton mientras la etiqueta decía Student. Ese contraste
separado fuerza ahora su proceso diario con Student también en ese caso;
una prueba verifica la ley ejecutada y que no pueda usarse como retorno
económico. La cartera canónica y los registros del núcleo 1.0.0 usan el modo
diario, por lo que la corrección no cambia sus cifras auditadas en 0.34.0.

## Alineación del objetivo y evidencia reconstruida (0.35.0)

La elección de SGOV 35%, IGSB 35%, SHV 25%, CASH 5% de 0.34.1 no era una
conclusión de que esas posiciones fueran óptimas. El desempate conservador
podía escoger menor riesgo dentro de rankings inciertos y omitir una mejor
utilidad del mandato. Con la misma lista de candidatas y 3.000 escenarios
nuevos, sustituir SGOV por SHY mejora el peor equivalente en USD 205,90;
las cotas pareadas por modelo rondan USD 146, por encima del umbral de
USD 100. Se corrige el criterio de selección, sin alterar anclas ni semillas
para obtener una composición deseada.

Una sensibilidad del mismo conjunto elige 35% de acciones en el modelo base,
45% al contrastar cuatro modelos y 0% al incorporar baja convicción. Ese
modelo declara prima accionaria e IC cero. La interfaz lo hace explícito;
el resultado defensivo depende de esa convención, no de evidencia de que
las acciones vayan a perder. No se elimina un modelo para forzar compras.

Con el mismo código y datos del cierre siguiente, la propuesta desde efectivo
pasó a SPY 35%, LQD 35%, TIP 25%, CASH 5%: reasignación del 70%. Al comparar
ambas cestas fijas con 3.000 escenarios comunes por modelo, la mejora en el
peor modelo es USD 16,67 con el corte anterior y USD 1,97 con el nuevo; sus
intervalos aproximados incluyen pérdidas y ganancias de más de USD 500.
No se ha demostrado que nueva información justifique ese giro. Una cuenta
hipotética ya invertida en la cesta anterior rechaza la transición con el
control de producción; ningún modelo supera el umbral con su cota inferior.
La propuesta inicial y una decisión de rebalanceo son preguntas distintas.
Los pesos siguen poco identificados. La atribución detallada y los hashes
quedan en [el contraste de cierres](auditorias/allocation-cuts-0.35.0.json).

El contraste cronológico de precios abarca orígenes desde abril de 2022
hasta septiembre de 2026, a 1/5/21 sesiones, con tres variantes de varianza,
12 instrumentos y cuatro cestas fijas. Para la cesta de la captura, a 21
sesiones quedan 38 orígenes no superpuestos y dos excepciones VaR95: 5,26%,
intervalo binomial bajo independencia [0,64%; 17,75%]. Las mejoras de CRPS
frente a EWMA plano y dinámico no se distinguen de cero con los intervalos
por bloques registrados. Solo hay dos observaciones de cola: no valida ES.

Es una prueba reconstruida del **fallback de varianza**. Desactiva GJR,
macro y anclas económicas históricas; comparte un centrado de precios
anterior a cada corte. Usa precios ajustados actuales y una cesta elegida
ex post, sin acreditar vintages, estrategia histórica, dividendos en efectivo,
costes ejecutados o CVaR a doce meses. Los resultados no promueven cambios
a la ley de precios ni acreditan la ventaja de las decisiones. Véase la
[auditoría completa](auditoria-decision-riesgo-0.35.md).

## Incertidumbre frente a todo el conjunto (29-oct-2026)

Con datos fijos del commit `72c273b`, 19 cestas y dos semillas prefijadas de
2.000 escenarios por modelo, los líderes estimados cambian el 60% del
capital. Sus cotas superiores de pérdida de oportunidad frente al conjunto
son USD 862,30 y USD 763,72 para USD 100.000. Ninguna candidata acota esa
pérdida dentro del umbral de USD 100 en ninguno de los experimentos. Son
cotas aproximadas de Monte Carlo, no pérdidas observadas ni prueba de que
una candidata sea inferior. El diagnóstico compara todas las alternativas;
la auto-comparación del líder no se presenta como precisión del conjunto.
La [auditoría](auditoria-incertidumbre-seleccion-0.35.md) conserva resultados,
límites y reproducción. No cambia pesos ni autoriza operaciones. Siguen
abiertas la cobertura de búsqueda, los parámetros y la validación prospectiva.

## Reducción de ruido ensayada (29-oct-2026)

Un estimador antitético en sombra reduce, a igual número de trayectorias,
la menor cota superior de oportunidad del conjunto: USD 845,57 → 291,62 y
USD 1.085,51 → 431,90 en los dos experimentos prefijados. El error se calcula
por pareja independiente, no por sus dos trayectorias dependientes. Ninguna
cesta alcanza todavía el umbral USD 100. Se conserva el cálculo ordinario
de selección, confirmación y riesgo. La [auditoría del estimador](auditoria-reduccion-ruido-0.35.md)
documenta resultados, paridad exacta del modo ordinario y límites. No hay
promoción predictiva ni se cambia la ley marginal de precios.

## Precisión por mandato y presupuesto (29-oct-2026)

El contraste ampliado usa una nueva pareja de semillas, cierres 27 y 28-oct,
19 cestas, tres objetivos y presupuestos de 2.000/8.000 trayectorias. A mayor
presupuesto, la menor cota de oportunidad antitética es USD 117,41/117,28 en
crecimiento y USD 9,56/17,57 en preservación. Crecimiento sigue sin resolver
el umbral USD 100. Preservación encuentra alternativas dentro de ese umbral
condicional. El objetivo de capital distingue una candidata, pero su cota
relativa cero no implica alcanzar la meta ni riesgo cero. Los cortes son
contiguos, el universo fijo es ex post y no se certifican todos los límites
de riesgo. La [auditoría por mandatos](auditoria-precision-mandatos-0.35.md)
conserva protocolo, límites y resultados. No hay promoción a producción.

## Sensibilidad económica de la propuesta (29-oct-2026)

Sobre la cesta canónica SPY 35%, LQD 35%, TIP 25%, CASH 5%, se congelan
19 alternativas, datos y semilla, y se contrastan 17 casos declarados con
1.500 parejas. Prima CAPM cero cambia el equivalente cierto de la misma
cesta en USD −669 y crecimiento del catálogo ×0,5/×1,5 en aproximadamente
USD −518/+518. Triplicar la pérdida de crédito resta USD 170. Son cambios
dentro del modelo, sin intervalos estimados de parámetros ni validación
predictiva. El IC no mueve el centro de esta cesta de índice y bonos, pero
sí qué acciones resultan elegidas: con IC 0,10 el líder puntual reasigna
65% del capital. No acredita ese IC. Tasas/spread siguen con bandas de
utilidad que abarcan cero. La [auditoría económica](auditoria-supuestos-economicos-0.35.md)
separa datos fechados y convenciones, conserva perfiles y bandas firmadas,
y prioriza validación de anclas e IC antes de promover nuevos supuestos.
Ningún líder aislado autoriza operar. La producción permanece sin cambios.

## Contraste de la señal TTM (29-oct-2026)

Se conservan 10.538 versiones de BPA de 160 respuestas companyfacts. El
extractor TTM y las funciones actuales de valoración/exposición se ejecutan
por origen con informes anteriores al día del corte y dividendos históricos.
El IC de rangos es 0,033/0,051/0,087 a 21/63/252 sesiones. Las diferencias
frente a BPA/precio no se distinguen de cero en ninguno de esos horizontes.
La asociación anual positiva es un diagnóstico reconstruido, con solo tres
orígenes anuales sin solapamiento; no certifica habilidad estable ni el
coeficiente completo de producción. La [auditoría TTM](auditoria-senal-ttm-0.35.md)
conserva protocolo, fuentes y exclusiones. Sigue pendiente evaluar señales
individuales emitidas prospectivamente, por cohorte, y calibrar el nivel de
las anclas. La cartera y los parámetros de producción permanecen sin cambios.

## Decisión de operar

Desde 0.33.0, la propuesta ordinaria debe mejorar frente a mantener en los
cinco modelos declarados, después de costes y de un margen pareado por
ruido de Monte Carlo. Se conserva el mandato completo: utilidad de
crecimiento, preservación o meta, retiros, suelo y moneda. Se comprueban
CVaR, pérdida, drawdown y liquidez en cada modelo. El candidato se fija antes
de esa verificación con escenarios nuevos; si falla, se mantiene la cuenta.

Los escenarios de margen, combinado y baja convicción incluyen pérdidas
esperadas de crédito duplicadas y beta de diferencial multiplicada por 1,5.
Baja convicción elimina la prima accionaria declarada y fija IC a cero.
El estrés llega a todos los constituyentes que anclan un ETF, aunque no se
simulen individualmente. No se alteran sus cifras contables originales.

Si falta un ancla económica o una expectativa explícita con incertidumbre
para una posición mantenida, la transición queda incompleta y se conserva
la cuenta. No se usa el retorno genérico como evidencia para liquidarla.
Si mantener también incumple límites, el informe lo indica; no certifica
que conservar sea una cartera segura ni disimula el incumplimiento.

El control es robusto frente a **estos cinco supuestos**. Sus intervalos
miden ruido de simulación, no toda la incertidumbre del modelo. La búsqueda
minimax del panel separado continúa restringida a crecimiento USD sin
flujos; no se presenta como el óptimo robusto global de todos los mandatos.

### Comprobación histórica de 0.33.0 con una cuenta de prueba

Cuenta hipotética: SPY 35%, SHY 35%, IEF 25%, CASH 5%, USD 100.000; no es una
cuenta real ni una recomendación de pesos. Con el corte conservado, la
búsqueda base proponía cambiar por una mejora equivalente de USD 1.679.
El control nuevo conserva exactamente la cuenta y calcula cero operaciones.
Sobre los escenarios pareados de verificación:

| Modelo | Mejora neta equivalente | Cota inferior ajustada |
|---|---:|---:|
| Base | USD 1.638 | USD 723 |
| Sin re-rating | USD 1.372 | USD 474 |
| Margen y crédito | USD 1.106 | USD 178 |
| Combinado | USD 194 | USD −703 |
| Baja convicción | USD −652 | USD −1.554 |

En 0.33.1, la candidata base desde efectivo sobre la captura del 28-oct
incumplía CVaR en dos modelos (20,42% y 21,17%, límite 20%) y se conservaba
el efectivo. Era un rechazo de **una candidata**, no prueba de inexistencia
de alternativas robustas. En 0.34.0 se corrige esa limitación: selección del
conjunto descubierto bajo todos los modelos y confirmación independiente.
Las cifras anteriores describen sus versiones; no son la cartera vigente.

## Registro del simulador exacto

`simulator_validation.mjs` conserva la primera distribución por corte,
versión del núcleo, hashes y fecha real de finalización. Emplea los mismos
prefijos diarios que la simulación, a 1/5/21 sesiones, con origen futuro dos
sesiones observadas después del corte; cualquier origen que no empiece
estrictamente después de la fecha de emisión se excluye. Evalúa activos y
cestas conjuntas estáticas, frente a EWMA sin retorno económico supuesto.
Puntúa CRPS aproximado, cobertura, QLIKE y residuo de ES. Se separan activos
y carteras, orígenes superpuestos y cohortes con cambios de núcleo.

Este registro empieza con la publicación de 0.34.0; conserva dos sellos y
ningún resultado maduro del núcleo nuevo. Los registros diarios anteriores
son comparadores, no evidencia de esta ley de precios. Alcanzar 20 orígenes no superpuestos y
500 observaciones habilita una revisión diagnóstica, **no** una declaración
de validez predictiva. Faltan precisión, mejora frente a referencias,
consistencia por periodos y resultados económicos netos maduros.

## VTI y oro

**VTI:** se añade la lectura de los JSON publicados por Vanguard en la
página oficial del fondo, comprobando ticker VTI, identificador 0970,
condición de ETF de renta variable, fecha de características y fecha de
comisión. Se capturó P/E 24,05722 al 30-sep y gastos 0,03% efectivos desde
28-abr, con primera observación real del 28-oct. Su ancla por rendimiento
de beneficios es 6,274% bajo las convenciones vigentes, con banda amplia.
No se rebaja el umbral de 70% ni se inventa la composición de la parte no
cubierta. El colector lo incorpora en las capturas nuevas; no se inserta
como información conocida en una captura anterior.

**Oro:** DFII10 y DTWEXBGS se añaden a FRED. El contraste usa cambios
**pasados** de tasa real y dólar para pronosticar el retorno siguiente de
GLD: 24 orígenes de entrenamiento y 34 posteriores, con objetivos maduros
antes de cada predicción. MSE 0,004747 frente a 0,004492 de una media
sencilla. Estos datos actuales no certifican vintages originales. No se
promueve ese candidato ni la identidad inflación menos gastos como media
validada; un modelo económico y su validación siguen pendientes.

## Capacidad predictiva de acciones

`anchor_information_research.py` filtra cada cifra de BPA anual por fecha
de presentación, armoniza las unidades de splits con los precios ajustados
y puntúa rangos contra retornos residuales de SPY a 21/63/252 sesiones.
Hay 47/45/36 orígenes mensuales y medias de IC 0,028/0,040/0,037. Todos los
intervalos por bloques incluyen cero. Se compara con rendimiento de
beneficios, sin seleccionar el mejor IC para cambiar el motor.

Es un **proxy anual**, no una réplica histórica del TTM y la señal exacta de
producción. Utiliza el universo actual de 160 acciones y las convenciones
actuales mantenidas constantes; no acredita supervivencia, vintages ni
supuestos conocidos entonces. Faltan TTM originales, dividendos conocidos
al origen, universo histórico y sellos prospectivos. No sustituye el IC de
0,05 ni demuestra que sea adecuado. El escenario IC cero actúa desde ahora
en la decisión de transición.

## Calendario GJR

`build_volatility.py` conserva un archivo inmutable de parámetros por mes
en `data/volatility-parameters/`. Hay un bootstrap explícito con la
calibración ya disponible; después se recalibra en el primer corte observado
de cada nuevo mes. Dentro del mes solo se actualiza la varianza con los
retornos nuevos: ω, α, γ, β, ν y la media de entrenamiento permanecen fijos.
Se registran por separado la fecha de entrenamiento y la del estado actual.
Las ejecuciones parciales por símbolos no escriben ese archivo de producción.

La cadencia cumple el procedimiento fijado, pero no acredita que la
frecuencia mensual sea predictivamente superior. GJR sigue siendo sobre
retornos totales y no sobre residuos factoriales.

## Gobierno y límites abiertos

[Convenciones del modelo](convenciones-modelo.md) distingue datos, mandato,
convenciones operativas y candidatos en sombra. Cada convención tiene
criterio de revisión y contraste previsto. Se conserva la regla de
promoción predictiva de §9.3; registrar una convención no es validarla.

Siguen abiertos: calibración de anclas y del CVaR exacto, GJR residual,
factores de tasas/crédito/USD y dependencia de cola, consenso anterior a los
eventos, oro, optimización robusta global para otros mandatos y operativa
conciliada. Se mantiene el tope combinado de 20% para alto rendimiento y
emergentes. El efectivo usa la tasa neta del mandato; no se imputa la T-bill
a una cuenta sin contrato de remuneración.

## Comandos y comprobaciones

```sh
npm test
python -m unittest discover -s tests -p 'test_*.py'
npm run check
python scripts/anchor_information_research.py
python scripts/gold_research.py
python scripts/build_volatility.py
node scripts/reliability_audit.mjs --full
```

**Verificación local:** 242 pruebas JavaScript, 141 Python y `npm run check` aprobados.

Las pruebas cubren rechazo de mejoras aparentes bajo otro modelo, costes
cero al mantener, mandato completo, anclas ausentes, constituyentes fuera de
la muestra, fechas e identidad de VTI y parámetros congelados con unidades
de porcentaje correctas. CI conserva los diagnósticos como artefactos. La
aprobación del software no acredita las hipótesis H1, H2 o H3 del documento.
