# Materialidad económica de las siete pruebas confirmatorias

**Hito:** H0.3. **Corte de evidencia:** 9-nov-2026 UTC. **Estado:** requisitos verificables definidos; umbrales materiales y potencia real pendientes.

El protocolo v1 define tres indicadores medidos en unidades diferentes. Un valor p pequeño no equivale a una ventaja económicamente útil. El protocolo v2 conserva siete contrastes y deja en \`null\` sus tres campos de umbral por familia. Este documento y el auditor asociado respetan ambas decisiones.

## Correspondencia de efectos y criterios pendientes

| Contrastes | Unidad del efecto positivo | Qué justificación independiente falta |
|---|---|---|
| \`return_mse:21/63/252\` | Reducción absoluta de error cuadrático del **retorno total aritmético** por instrumento, agregada con pesos iguales de instrumentos y orígenes | Una relación documentada entre la reducción de error y una mejora material en decisiones de cartera netas de costes y riesgo |
| \`ranking_ic:21/63/252\` | Puntos de diferencia del coeficiente de correlación por rangos de **Spearman** con respecto a BPA/precio, en la misma intersección de instrumentos | Demostrar qué mejora de ordenamiento aporta valor ejecutable después del coste de rotación y exposiciones |
| \`net_economic_value:21\` | Diferencia **anualizada del logaritmo del rendimiento mensual** de la cuenta integral neta frente al SPY más efectivo ajustado por beta | Una prima neta relevante para un inversor dadas la volatilidad, drawdowns, duración, crédito, capital requerido y costes de ejecución |

No convertir una reducción de error al cuadrado o una mejora de IC en puntos básicos de retorno mediante una regla inventada. La monetización requeriría un análisis estructural de cómo dichas señales cambian las órdenes de una política causal comparable. El signo positivo respecto del benchmark ya determina la hipótesis estadística, pero **no fija cuánto debe mejorar para merecer inversión real**.

## Restricciones de costes y sensibilidad

El desarrollo v1 congela, como parámetros de investigación, spread de 5 pb y deslizamiento de 2 pb por unidad de notional al que se apliquen esos componentes; la sensibilidad triplica ambos. La **suma puramente ilustrativa de parámetros** sería 7 pb en el caso base y 21 pb en estrés, una diferencia de 14 pb por unidad de notional negociado.

| Rotación hipotética en un mes sobre NAV inicial | Presupuesto base ilustrativo | Diferencia incremental de estrés |
|---|---:|---:|
| 0 % | 0 pb NAV | 0 pb NAV |
| 25 % | 1,75 pb NAV | 3,50 pb NAV |
| 50 % | 3,50 pb NAV | 7,00 pb NAV |
| 100 % | 7,00 pb NAV | 14,00 pb NAV |

Estos resultados **no son costes realizados, ni spreads observados, ni umbrales de alfa anualizada**. Falta validar en el motor si se aplica spread completo o medio, la definición de rotación negociada, los costes de rebalanceo de la referencia, las ejecuciones al siguiente cierre y la transformación consistente a riqueza logarítmica. Los resultados deben proceder de cuentas auditables; no se pueden derivar de supuestos de costes aislados.

## Criterio de aceptación pendiente

Para registrar materialidad en un protocolo nuevo deberán estar identificados el objetivo y horizonte, las unidades, la decisión económica afectada, la fuente independiente y fechada de cada umbral, el coste y el riesgo de las alternativas, la fórmula de agregación y un análisis de potencia compatible con la inferencia seleccionada. El origen de la justificación debe preceder a la inspección de la cohorte utilizada para confirmación.

El comando \`python scripts/confirmatory_economic_materiality.py --verify --output out/confirmatory-economic-materiality-v1.json\` carga los protocolos congelados, verifica la familia completa, las referencias y las hipótesis de costes, e informa **siete umbrales sin justificar**. Rechaza cambios a cualquier protocolo, inventar umbrales o activar v2. En CI se conserva el resultado como \`confirmatory-economic-materiality\`.

**Límites:** la implementación define las condiciones documentales y las unidades, pero no produce evidencia económica nueva, no acredita potencia y no permite inferencia confirmatoria. H0.3 sigue abierto. Cualquier protocolo v3 necesitaría una justificación económica ex ante y una cohorte futura independiente, no la reutilización del pasado examinado.
