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
pérdida de oportunidad frente al líder estimado en la selección quede dentro
del umbral económico del mandato (USD 100 en la configuración base). Si dos alternativas
tienen la misma rotación, se conserva la mayor utilidad en el peor modelo.

Se contrastan todas las parejas de modelos porque `min(a) − min(b)` no es
la mejora en cada modelo por separado. Las cotas pareadas de Monte Carlo
incluyen la multiplicidad de candidatas y modelos y convierten utilidad a
un equivalente monetario aproximado. No representan incertidumbre total de
parámetros ni confianza predictiva. Se siguen mostrando alternativas cuyo
ranking no queda resuelto, aunque no sean empates económicos demostrados.
La pérdida por ese desempate no es una cota de distancia al mejor candidato
verdadero ni al óptimo global; elegir el propio líder da cero por identidad.
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

El [registro de señales completas](validacion-prospectiva-senales.md) conserva
la primera emisión mensual, score, confianza, anclas y datos originales por
cohorte. Evalúa el valor incremental frente a BPA/precio y al mismo modelo
con IC cero, además del error del ancla SPY. Verifica la primera publicación
Git antes del inicio del retorno y congela el primer resultado maduro.
Permite empezar a contrastar esas afirmaciones, sin declararlas validadas.

El [seguimiento operativo](revision-operativa-validacion.md) conserva la
primera revisión mensual del núcleo y distingue acumulación, falta de
trazabilidad y rechazo. Los diagnósticos de cobertura no agrupan activos
correlacionados como observaciones independientes. Un rechazo suspende
nuevas promociones y requiere una decisión documentada; no activa un cambio
automático de pesos o parámetros ni acredita por sí mismo el fallback EWMA.

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

Una propuesta para una cuenta nueva en efectivo no es una instrucción para
rotar una cuenta ya invertida. Ambas deben compararse con el mismo mandato
y datos. En el contraste 27–28-oct de 0.35.0 cambió el 70% de los pesos sin
una mejora resuelta entre las cestas fijas; el control rechazó esa transición
para la cuenta hipotética anterior. Es evidencia de indeterminación de
pesos, no prueba de que conservar tenga capacidad predictiva acreditada.
