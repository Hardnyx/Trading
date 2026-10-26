# Optimización bajo incertidumbre de valoración

Estado: comparación experimental disponible en la página desde la versión 0.10.0. El cálculo no modifica posiciones ni ejecuta operaciones. La propuesta básica y el contraste de robustez permanecen identificados por separado.

El problema observado es que maximizar utilidad dentro de una valoración con P/E de salida alto puede concentrar una cartera en una revalorización que todavía no tiene evidencia prospectiva suficiente. Se añade una comparación que conserva el universo, los precios, la covarianza, los regímenes y los números aleatorios, y varía las hipótesis económicas.

## Modelos comparados

1. Supuestos actuales de BPA, crecimiento, múltiplos y confianza.
2. Sin expansión del múltiplo: el P/E de salida no supera el menor entre el supuesto original y precio/BPA observado.
3. Estrés de margen operativo: cuando existen al menos ocho observaciones distintas y 730 días, se multiplica el BPA por el menor entre uno y la razón entre el margen operativo mediano y el reciente.
4. Combinación de los dos anteriores.
5. Combinación con confianza asignada de 30% y prima hipotética de renta variable amplia igual a cero.

El tercer caso **no es una estimación contable de BPA normalizado**. No reconstruye intereses, impuestos, márgenes netos, cambios de perímetro ni mezcla de negocios. Es un estrés proporcional explícito para detectar dependencia de beneficios excepcionalmente altos. No eleva el BPA cuando el margen reciente es bajo. Si faltan observaciones comparables, el informe registra la ausencia; no inventa un histórico. Las revisiones del mismo período cuentan una vez y se filtran por publicación.

El marco del motor sigue anualizando valoraciones de varios años. Esta investigación no demuestra convergencia de múltiplos en doce meses ni calibra la probabilidad de cada modelo alternativo.

## Búsqueda y verificación

- Se prepara una sola muestra de activos, incluyendo los instrumentos existentes de la cuenta. Ningún modelo vuelve a ordenar el universo según sus retornos.
- Los fondos mantenidos necesitan supuestos explícitos: VTI recibe como hipótesis la tasa Treasury de tres meses más 3,5 puntos porcentuales y una banda de 15 puntos; GLD recibe retorno central cero y una banda de 15 puntos. Son entradas de sensibilidad, no pronósticos validados. IEF utiliza duración, TIR y gastos de una página oficial cuya identidad y moneda se verifican.
- Se generan asignaciones iniciales y se exploran transferencias locales de cinco puntos porcentuales entre activos. Se comprueban topes, liquidez mínima, exposición sectorial, grupos económicos y solapamientos mediante el mismo validador del motor.
- Todas las carteras se valoran sobre las mismas trayectorias de cada modelo. El filtro terminal usa las distribuciones monetarias y la retención del mandato sin sumarlas dos veces.
- La selección minimiza el mayor arrepentimiento: la diferencia de utilidad logarítmica frente a la mejor candidata admisible en cada modelo. El comparador es la muestra finita de carteras que satisface simultáneamente los límites en todos los modelos.
- La unión de finalistas robustas, ganadoras de cada modelo y referencias se verifica semanalmente con otra semilla. Se comprueban CVaR, probabilidad de pérdida, drawdown y liquidez.
- La comparación con mantener la cuenta utiliza diferencias por trayectoria y costos de transición. El umbral de mejora se contrasta con una cota conservadora de error Monte Carlo, ajustada por la cantidad de carteras y modelos examinados en verificación. La aproximación normal y la cota de unión no cubren error del modelo, falta de vintages ni calibración económica fuera de muestra.

El informe distingue la admisibilidad de construcción y la mejora económica. Por ejemplo, una referencia con VTI al 40% excede el límite global de 35%. Que otra cartera cumpla ese tope no prueba que tenga mayor utilidad. La cuenta original se conserva como comparador, incluso cuando no pertenece al conjunto admisible para nuevas propuestas.

No se afirma optimalidad global. La lista de activos, el número de candidatas, la malla de cinco puntos y los modelos alternativos son limitaciones explícitas. La repetición con otras semillas o universos debe conservarse como diagnóstico, sin seleccionar retrospectivamente solo la ejecución más favorable.

## Usar en la página

En **Componer cartera**, pulsa **Comparar robustez**. Se usan el mandato, los límites, los costos, los escenarios macro y las hipótesis editadas en la sesión. Si ingresaste cantidades de una cuenta, ese es el comparador; en su defecto se usa la composición registrada. Sin ambos, una cartera de trabajo que suma 100% se valora a precios del corte y se identifica expresamente como referencia teórica. Si no hay posiciones, se compara con el capital inicial en efectivo.

La tabla presenta la mediana al mantener, la mediana candidata, CVaR, probabilidad de pérdida y mejora equivalente con límite inferior Monte Carlo en los cinco modelos. La comparación es compatible actualmente con crecimiento en USD sin retiros, suelo ni meta de capital; otros mandatos conservan sus datos y reciben una explicación de la limitación, sin reinterpretarlos.

**Cambios frente a la referencia y efectivo** desglosa cada instrumento: mantener, abrir, aumentar, reducir o cerrar, pesos, valores, diferencia monetaria, cantidades fraccionarias y precios del corte. Son diferencias hacia la candidata, no señales independientes por activo. Si no supera el umbral de robustez, el panel identifica la transición como hipotética y conserva mantener como referencia. El mismo plan de costos del motor determina capital invertible, comisiones, spread, deslizamiento e impuesto supuesto. Se comprueba efectivo inicial + ventas − compras − costos = efectivo final antes de redondear; con base fiscal incompleta no se presenta una conciliación válida. No se modelan lotes enteros ni ejecución intradía.

El avance se muestra durante el cálculo y puede cancelarse. Cambiar capital, posiciones, cuenta, mandato o hipótesis invalida el resultado. **Usar pesos para simular** requiere una acción explícita y copia la candidata a la cartera de trabajo, junto con el capital y el costo de transición utilizados en la comparación. No registra operaciones de broker. Las cantidades de la cuenta se conservan.

Para fondos sin perfil de renta fija o retorno fundamentado, deben introducirse retorno esperado e incertidumbre en Research; el navegador no asigna automáticamente las primas de los ejemplos de investigación. La ingesta añade perfiles oficiales de Treasury para IEF, IEI, SGOV y SHV, además de SHY y TLT. Crédito e inflación no se habilitan por reutilizar ese modelo sin sus propios supuestos.

El núcleo del cálculo es compartido por el navegador y el script. La página usa un presupuesto menor para cálculo interactivo; los presupuestos y semillas quedan registrados en cada resultado. Las hipótesis de crecimiento y múltiplos editadas se conservan; la variante de menor confianza no aumenta una confianza ya más baja.

## Ejecutar con una cuenta local

```bash
python scripts/run_portfolio_robustness.py /ruta/privada/cuenta.json
```

La entrada es un JSON con `account.enabled`, `account.cash` y `account.positions` con símbolo y cantidad, compatible con la cuenta del motor; puede incluir `basis` para explicar su origen. No se deben incorporar cuentas personales al repositorio público. Los datos de entrada pueden guardarse en `.cache/`, excluida de Git. Un segundo argumento opcional permite leer los presupuestos de investigación desde otro JSON.

El comando escribe `out/portfolio-robustness.json` y el perfil de renta fija usado en `out/robustness-bond-inputs.json`. `out/` está excluida de Git. El informe conserva hash del mercado, semilla, universo, modelos, estreses, anclas, referencias, costos, límites y resultados de verificación. Las cuentas se valoran al corte guardado; no se presentan como precios ejecutables del día.

El workflow **Portfolio robustness research** usa exclusivamente una cuenta sintética de USD 100.000, conserva la evidencia como artefacto y no reemplaza por sí mismo las propuestas básicas de la aplicación. No consume cuentas ni posiciones personales.

## Interpretación de la salida

`candidate` identifica la mejor candidata dentro del conjunto verificado bajo el criterio indicado. No es una instrucción de operar.

`decision = no_robust_rebalance_evidence` significa que al menos un modelo no supera el umbral de mejora frente a mantener, una vez considerado el error de simulación. No equivale a afirmar que mantener sea óptimo, que los límites se cumplan en la cuenta existente o que no haya otros instrumentos mejores fuera de la muestra.

Una salida favorable solo demuestra que la candidata supera las pruebas condicionales implementadas. Sigue siendo necesaria evidencia económica prospectiva y calibración de las hipótesis antes de promoverla al motor público.
