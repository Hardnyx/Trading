# Auditoría de fiabilidad · motor 0.34.0

28 de octubre de 2026. Corte de precios del 27-oct, captura del 28-oct a las
12:27 UTC. Se mantienen los mismos datos al comparar código, semillas y
supuestos. La cuenta de prueba es hipotética. No se modifica una cuenta real.

## Conclusión

La rotación anterior tenía causas comprobables: aleatoriedad acoplada,
composiciones con diferencias pequeñas frente al error de simulación y una
ley de precios cuyo compensador no preservaba la media declarada. Se
corrigen esos defectos y se separa descubrimiento, selección y confirmación.
**La asignación y la capacidad predictiva siguen sin validar.** Obtener la
misma cartera con varias semillas no demuestra que sus pesos sean correctos.

Las evidencias numéricas se conservan en
[`fiabilidad-0.33.1.json`](auditorias/fiabilidad-0.33.1.json) y
[`fiabilidad-0.34.0.json`](auditorias/fiabilidad-0.34.0.json). La base anterior
corresponde al commit `f1486deafd9c0412b5678be474e4f5b5677d7649`.

## 1. Qué explicaba las rotaciones

| Experimento congelado | Resultado en 0.33.1 | Interpretación |
|---|---|---|
| Cambiar solo semilla de búsqueda | Cambia 55–75% del capital | La cartera no estaba bien identificada por esa búsqueda |
| Reevaluar las ganadoras con 3.000 escenarios comunes | Con 75% de capital distinto, diferencia equivalente USD 7,74 sobre USD 100.000; cota inferior USD −457 | No hay una superioridad resuelta dentro de ese experimento; tampoco demuestra equivalencia o acierto futuro |
| Añadir activo con peso y riesgo cero | 2.028.000 coordenadas distintas; mediana 4,95% → 4,31%; CVaR 9,11% → 9,72% en la misma cartera | Defecto de acoplamiento de flujos aleatorios, sin nueva información económica |

La segunda fila compara utilidad logarítmica dentro del motor anterior.
No valida su distribución de precios ni sus medias; los USD son equivalentes
condicionales del modelo, no rentabilidad realizada. Las otras comparaciones
pareadas tienen diferencias de USD −247 y USD 255, también sin superioridad
resuelta por sus cotas. No deben compararse los equivalentes de búsquedas
originales como si hubiesen usado las mismas trayectorias.

Se separan ahora flujos aleatorios por componente, activo y trayectoria,
con orden canónico. Permutar el catálogo o los regímenes, añadir un activo
de riesgo cero y cambiar el informe semanal por mensual dejan intacta la
cartera fija en sus puntos comunes. El proceso diario de divisa también
conserva esa identidad. Esto corrige artefactos numéricos; no impide que
nuevos activos con riesgo o covarianzas distintas cambien una evaluación.

## 2. Corrección de la ley de precios

El ancla es crecimiento simple anual. Con innovación gaussiana condicional,
el incremento diario `sqrt(h)·Z − h/2` tiene momento exponencial uno. Puede
utilizarse GJR para `h` aunque se ajuste con verosimilitud t.

Una Student-t para log-retornos no tiene el momento exponencial necesario.
Restar `h/2` no la centra en precios. Acotar la tabla de cuantiles tampoco
justifica ese compensador: el momento de la tabla cambia con ν y `h` y
puede estar dominado por eventos muy raros, ausentes en 1.000 trayectorias.
El JSON de la auditoría contiene contraejemplos bajo la ley gaussiana
latente continua pretendida. No son previsiones de precios ni momentos
exactos sobre el espacio discreto de semillas del generador.

En el núcleo de precios 1.0.0, la ley económica es gaussiana condicional.
Se mantienen el estado GJR y su ajuste t. Student pasa a estrés de riesgo
con ν ajustado donde está aceptado y ν=4 declarado en los demás activos
estocásticos. Ese estrés no publica media, retorno esperado ni utilidad y
puede vetar una transición. No resuelve por sí solo la dependencia de cola
conjunta ni valida el riesgo de impago.

Referencia primaria sobre la restricción del momento exponencial:
[Liu, Li y Ng, opción y GARCH con innovaciones t](https://doi.org/10.1016/j.najef.2014.10.007).
Para el ajuste estadístico t de GARCH, véase el
[artículo original de R Journal](https://journal.r-project.org/articles/RJ-2010-014/).

## 3. Selección y confirmación

La búsqueda base queda explícitamente en investigación. Sus candidatas se
unen a referencias sencillas de fondos elegibles. Todas las candidatas
legales se criban bajo cinco modelos; un conjunto de finalistas se evalúa
en escenarios distintos. Solo la elegida pasa a una confirmación adicional,
con una semilla fija independiente de descubrimiento y selección. No se
reutiliza un rechazo para intentar otra candidata en la misma confirmación.
El panel minimax separado también necesita esa confirmación para copiar pesos.

Se exige mejora neta frente a mantener en cada modelo y cumplimiento de
riesgo con margen de muestreo. Para probabilidades se utiliza cota binomial
KL; para CVaR, aproximación de influencia de cola. Se reparte el presupuesto
nominal de error entre mejora y riesgo y entre modelos/restricciones. No
son garantías finitas de CVaR ni intervalos de calibración predictiva. Los
flujos, objetivos, moneda y costes del mandato se conservan.

Entre rankings no resueltos se aplica menor rotación y luego menor cota de
riesgo. Esa es una política conservadora declarada. No significa que todas
las candidatas sean equivalentes, que los pesos sean estimadores precisos
ni que se haya encontrado el óptimo global. La interfaz muestra los rangos
de las composiciones en detalles, sin permitir interpretarlos como pesos
combinables libremente. Las tarjetas de riesgo muestran la peor cota MC de
los contrastes, para evitar presentar cero pérdidas simuladas como riesgo nulo.

## 4. Resultado con datos congelados

| Prueba de 0.34.0 | Resultado |
|---|---|
| Tres semillas de descubrimiento | Misma elección: SGOV 35%, IGSB 35%, SHV 25%, CASH 5% |
| Retirar solo la elegibilidad de VTI | Misma elección en este corte |
| Reducir TIR de IGSB en 300 pb | IGSB se sustituye por AGG; sensibilidad declarada, no dato nuevo observado |
| Cuenta hipotética SPY 35%, SHY 35%, IEF 25%, CASH 5% | Mantener, coste cero; no se acreditó una transición del conjunto comprobado |
| Tres confirmaciones adicionales de la elección inicial, 1.000 escenarios cada una | Pasan los contrastes declarados; menor cota de mejora entre USD 3.807 y USD 3.872; mayor cota CVaR entre 0,36% y 0,66% |

La ejecución canónica de tres búsquedas descubre 979 candidatas legales,
evalúa 23 finalistas y deja **13 alternativas con rankings no resueltos**;
el menor solapamiento es solo 5%. La identidad de la cartera elegida entre
semillas viene también de la política de desempate y del conjunto común de
referencias. **No permite concluir que los pesos estén identificados.**

Sobre esa elección, el modelo base da mediana 4,19% y media 4,11%. El
contraste económico más desfavorable conserva una cota de mejora de
USD 3.898 frente a efectivo inicial no remunerado, según el mandato. No es
una comparación con la cuenta real del usuario ni demuestra una ventaja
frente a una letra del Tesoro o una estrategia pasiva. El 5% de efectivo es
la reserva exigida; los otros pesos son la selección conservadora dentro
del conjunto contrastado, no parámetros financieros validados.

No se cambian TIR, topes, anclas o semillas para reproducir una cartera
preferida. La corrección matemática y el procedimiento nuevo justifican
que esta versión cambie de composición; la prueba de sensibilidad confirma
que tampoco queda congelada cuando cambia un supuesto económico.

## 5. Qué debe ocurrir antes de confiar en la predicción

El registro anterior de riesgo tenía dos sellos y una sesión puntuada;
los tres pronósticos anuales no habían vencido. No acreditan el núcleo nuevo.
El nuevo registro sella el mismo proceso diario que usa producción a
1/5/21 sesiones, para activos y cestas conjuntas estáticas, frente a EWMA
sin retorno supuesto. El retorno empieza después de la publicación y
conserva su primera puntuación madura. Las versiones de núcleo no se agrupan.

Se puntúan CRPS aproximado, cobertura, QLIKE y residuo de ES. Los intervalos
por bloques utilizan orígenes, no filas de activos correlacionados. Veinte
orígenes no superpuestos y 500 observaciones de activos en esos orígenes
solo habilitan revisión diagnóstica. Faltan precisión, mejora frente a
referencias, consistencia por periodos y una decisión documentada ante
rechazos. Para utilidad de inversión hacen falta resultados netos maduros
bajo el mismo mandato. No se promueve nada automáticamente por acumular filas.

Los [criterios de confianza](criterios-confianza.md) y el
[backlog](pendientes.md) conservan esos pendientes. Esta versión acredita
correcciones computacionales y contrastes condicionales, no rentabilidad
futura ni una cartera única correcta.

## Verificación

235 pruebas JavaScript y 137 Python aprobadas; `npm run check` y
`git diff --check` sin incidencias. La paridad de motor e interfaz se
verifica además con el navegador de CI antes de dar por cerrada la integración.
