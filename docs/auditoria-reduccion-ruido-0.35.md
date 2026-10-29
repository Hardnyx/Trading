# Reducción de ruido de selección · 29-oct-2026

Se prueba un estimador antitético en sombra, sin cambiar la política que
elige o autoriza una cartera. El núcleo de precios sigue siendo 1.0.0 y
la aplicación 0.35.0: la distribución marginal objetivo y las trayectorias
ordinarias permanecen iguales. La extensión del generador exige
`researchShadowMode: true` para activar `researchMirror`.

## Qué se prueba

Cada escenario se empareja con otro que invierte los normales primitivos
(precios, factores, divisa e incertidumbre del ancla). Las uniformes de
régimen y saltos se reflejan en la misma rejilla discreta del generador.
Cada trayectoria evoluciona su propia varianza, incluido GJR asimétrico;
no se invierten precios ya calculados ni se mantiene artificialmente fija
la varianza del espejo. La simetría de los normales y la transformación
uniforme conservan las leyes marginales objetivo.

La utilidad se evalúa completa en cada trayectoria y después se promedia
por pareja. El error se calcula sobre las 1.000 medias de parejas
independientes. Contar los 2.000 integrantes como independientes daría
precisión ficticia. No se usan estas medias para calcular probabilidades,
cuantiles, CVaR o límites de riesgo.

Referencia docente primaria: [Martin Haugh, Columbia University, Simulation
Efficiency and an Introduction to Variance Reduction Methods](https://www.columbia.edu/~mh2078/MonteCarlo/MCS_Var_Red_Basic.pdf).
La reducción de varianza no está garantizada para cualquier función; se
contrasta en el modelo y el mandato concretos, a igual número de evaluaciones.

## Experimento congelado

- Mismos datos completos y 19 cestas del análisis anterior, precios 28-oct.
- Cinco modelos económicos y horizonte anual; ninguna búsqueda nueva.
- Dos semillas principales prefijadas: 1218542633 y 1536675889.
- Para el estimador ordinario, 1.000 escenarios de la semilla principal y
  1.000 de una semilla independiente prefijada (430718295 y 770270119).
- Para el antitético, 1.000 escenarios principales y sus 1.000 espejos.
- Igual coste en evaluaciones de utilidad: 2.000 trayectorias por modelo y
  método. El estudio genera tres brazos porque ambos métodos comparten uno;
  no se atribuye independencia a la comparación entre métodos ni igualdad
  exacta de tiempo de CPU.
- Multiplicidad para cuatro experimentos (dos métodos por dos semillas).
  Son aproximaciones de Monte Carlo con conversión monetaria estimada, no
  garantías predictivas ni cobertura exacta para cualquier distribución.

## Resultado

| Semilla principal | Menor cota superior de oportunidad, ordinario | Menor cota superior, antitético | Reducción de esa cota |
|---|---:|---:|---:|
| 1218542633 | USD 845,57 | USD 291,62 | 65,5% |
| 1536675889 | USD 1.085,51 | USD 431,90 | 60,2% |

Las cuatro evaluaciones eligen SHY 35%, IGSB 35%, SHV 25%, CASH 5% como
líder puntual del conjunto. Coincidir no demuestra que esos pesos sean
óptimos ni que el método haya resuelto su identificación. Ninguna cesta
acota la oportunidad dentro de USD 100. La tabla compara mínimos de las
cotas del conjunto; en el segundo experimento ordinario ese mínimo no
corresponde exactamente al líder puntual (su cota es USD 1.096,07).

Las reducciones son de esta cota aproximada, no porcentajes de reducción
de varianza universales, de riesgo financiero ni de error de pronóstico.
La utilidad media estimada del líder con antitéticos da equivalentes ciertos
de USD 104.155,32 y USD 104.173,86. Son cifras condicionales del simulador,
no rentabilidades realizadas o recomendaciones de inversión.

## Verificación y decisión

Las pruebas cubren simetría exacta de log-precios gaussianos con varianza
constante, cancelación del ruido de utilidad logarítmica en ese caso,
conteo de parejas, rechazo de datos faltantes y bloqueo del espejo fuera
de investigación. El contraste con el código de `1ffeb47` comprueba igualdad
exacta de salidas ordinarias en cuatro combinaciones de varianza fija/GJR
y anclas fijas/inciertas. Sus hashes están en el resultado fechado.

El estimador queda en sombra. Hay evidencia de que merece continuar el
contraste, pero dos semillas y un conjunto ex post no permiten promoverlo
como prueba de una selección precisa. Faltan otros cortes y mandatos,
comparación con mayor presupuesto independiente y evaluación de coste y
memoria. La confirmación y las restricciones de riesgo de producción
continúan usando escenarios ordinarios independientes. Tampoco se acredita
la calibración de parámetros o ventaja económica fuera de muestra.

## Reproducción

```sh
node --test tests/antithetic-selection.test.mjs
node scripts/antithetic_selection_research.mjs
```

El [resultado completo](auditorias/antithetic-selection-2026-10-29.json)
conserva cotas de las 19 cestas y hashes de código, datos y exposición.
Para repetirlo en la revisión que incorpora este script se necesitan los
ficheros completos de mercado y volatilidad de `1ffeb47`; el commit solo
contiene los datos publicados entonces. Las capturas de metadatos sin
historiales no sustituyen esos ficheros. CI conserva el contraste completo
junto al diagnóstico ordinario durante 90 días y tras cada refresco exitoso.
