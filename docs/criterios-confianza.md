# Qué significa poder confiar en Trading

La confianza se evalúa por afirmación. Calcular correctamente, sostener una
decisión bajo varios supuestos y predecir resultados observados son pruebas
distintas. Una cartera estable puede estar mal; una corrección demostrable
puede justificar cambiar una cartera anterior.

## 1. Corrección del cálculo

- Permutar el catálogo o añadir una posición de peso y riesgo cero no puede
  cambiar las trayectorias de una cartera fija.
- Cambiar la frecuencia del informe no cambia el proceso diario de precios
  y divisa. Los prefijos usados para validar son los del mismo simulador.
- La ley de precios debe admitir la media económica declarada. Una
  corrección gaussiana no centra una exponencial de Student-t.
- Costes, dividendos, impuestos supuestos, pesos y capital deben conciliar;
  pantalla y motor deben evaluar los mismos escenarios y la misma candidata.

Estas condiciones son comprobables ahora. No demuestran acierto predictivo.

## 2. Respaldo de una decisión concreta

El descubrimiento de candidatas, su selección y su confirmación usan tres
experimentos distintos. Todas las candidatas descubiertas se contrastan en
los cinco modelos económicos; también se comprueban referencias sencillas.
Una candidata elegida se confirma una sola vez, en escenarios que no se
usaron para seleccionarla. Rechazarla no permite probar la siguiente sobre
esa misma confirmación.

La transición debe superar mantener la cuenta, neta de costes y del umbral
del mandato, en cada modelo. Los límites incorporan margen de simulación:
cota binomial para probabilidades y una aproximación para CVaR. El estrés
Student controla riesgo sin interpretar su precio medio como rentabilidad.
Estas cotas no contienen toda la incertidumbre de parámetros o del mercado.

Se maximiza la utilidad del mandato en el peor modelo declarado. La
incertidumbre del ranking no permite cambiar ese objetivo por mínimo riesgo.
Desde 0.35.0, favorecer menor rotación exige que la **cota superior** de la
pérdida de oportunidad frente a la mejor candidata quede dentro del umbral
económico del mandato (USD 100 en la configuración base). Si dos alternativas
tienen la misma rotación, se conserva la mayor utilidad en el peor modelo.

Se contrastan todas las parejas de modelos porque `min(a) − min(b)` no es
la mejora en cada modelo por separado. Las cotas pareadas de Monte Carlo
incluyen la multiplicidad de candidatas y modelos y convierten utilidad a
un equivalente monetario aproximado. No representan incertidumbre total de
parámetros ni confianza predictiva. Se siguen mostrando alternativas cuyo
ranking no queda resuelto, aunque no sean empates económicos demostrados.
No se fija la cartera anterior y una mejora respaldada puede justificar
un cambio importante.

## 3. Evidencia predictiva

Desde el núcleo 1.0.0 se sellan distribuciones del simulador real a 1, 5 y
21 sesiones, tanto por activo como para la cesta de referencia y una cesta
de riesgo predefinida. Se comparan con EWMA sin retorno supuesto. El origen
del retorno se sitúa dos sesiones observadas después del corte de precios;
se excluye cualquier origen que empiece en o antes de la fecha de emisión.
Así no se atribuyen al pronóstico movimientos que ya habían empezado.

Los sellos y las primeras puntuaciones maduras son inmutables. Se conserva
la versión del núcleo, código, datos, fecha de publicación y resultados
faltantes. Se puntúan CRPS aproximado, cobertura, QLIKE y residuo de Expected
Shortfall. La incertidumbre se agrupa por origen; las ventanas superpuestas
y los activos correlacionados no se cuentan como observaciones independientes.

Veinte orígenes no superpuestos y 500 observaciones de activos habilitan
una revisión diagnóstica. **No declaran validado el modelo.** Antes de una
conclusión favorable hacen falta precisión suficiente de cobertura y ES,
mejora de puntuación frente a referencias con incertidumbre por bloques,
estabilidad por subperiodos y revisión de cualquier rechazo. Se revisará en
fechas mensuales predeterminadas; no se cambiarán criterios después de ver
el resultado favorable. El registro nunca promueve modelos automáticamente.

La utilidad de invertir requiere además retornos de cartera maduros fuera
de muestra, netos de costes y rotación, comparados con mantener y referencias
pasivas bajo el mismo mandato. Los horizontes cortos de riesgo no sustituyen
esa evidencia ni acreditan el IC, el re-rating o una prima de renta variable.

## Cómo interpretar la salida actual

- **Admisible bajo los contrastes:** pasa controles condicionales; la
  predicción y la ventaja económica pueden seguir sin acreditar.
- **Pesos poco identificados:** varias composiciones quedan sin una
  superioridad resuelta. No se presenta su diferencia como nueva información.
- **Mantener:** no se acreditó una transición suficiente. No demuestra que
  la cuenta actual sea óptima ni que el efectivo sea la mejor inversión.
- **Comparación incompleta:** faltan anclas o datos necesarios. No se usa
  un retorno genérico para justificar liquidar una posición.

Un cambio grande debe quedar explicado por datos nuevos, una corrección
matemática, un cambio explícito del mandato o una mejora robusta medible.
La versión, los datos y el protocolo permiten revisar cuál fue la causa.
