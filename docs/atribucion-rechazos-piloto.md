# Por qué el piloto histórico mantuvo efectivo

**2-nov-2026. Capacidad predictiva y ventaja económica: sin acreditar.**

Se reprodujo la etapa de selección de las 23 finalistas archivadas en cada
origen: CASH y 22 alternativas. Se conservaron entradas, código, modelos,
semilla de selección y 1.000 trayectorias por modelo. No se repitieron la
búsqueda ni la confirmación, ni se probaron nuevas candidatas. Esta es una
atribución retrospectiva de una decisión conocida, sin holdout independiente.

La reproducción verifica los hashes de los archivos originales y de todos
los módulos de producción. Revalida universo, anclas, covarianzas y solicitud;
recupera por candidata la factibilidad, selección, equivalente cierto del
peor modelo, ganancia inferior mínima, riesgo máximo y rotación archivados.
Rechaza la ejecución si divergen. El [informe completo](../data/historical/scoped-pilot-attribution-v1/report.json)
guarda cada control, estimación, cota, límite y motivo por modelo. Los
archivos del piloto original permanecen intactos.

## Resultado

Las 22 alternativas de cada fecha habían pasado filtros de composición y
operativa. Todas superan el umbral económico de USD 100 en los cinco modelos:
sus cotas inferiores mínimas de ganancia son USD 428–1.244 en diciembre y
USD 315–914 en abril. Son ganancias simuladas bajo supuestos, sin evidencia
de capacidad predictiva.

Ninguna pasa todos los controles de riesgo. La cota superior de probabilidad
de pérdida supera el máximo de 45% en las 22 alternativas bajo baja
convicción y también en el estrés Student. Algunas fallan además CVaR.
No hay rechazos por ganancia insuficiente, drawdown o liquidez en esta etapa.
Los conteos siguientes excluyen CASH; una alternativa puede fallar en varios
modelos y controles.

| Origen | Modelo | Rechazos por prob. de pérdida | Estimación puntual ya >45% | Solo por margen de muestreo | Rechazos CVaR |
|---|---|---:|---:|---:|---:|
| 31-dic-2024 | Base | 20/22 | 0 | 20 | 2 |
| 31-dic-2024 | Baja convicción | 22/22 | 6 | 16 | 4 |
| 31-dic-2024 | Student, solo riesgo | 22/22 | 3 | 19 | 3 |
| 30-abr-2025 | Base | 22/22 | 11 | 11 | 13 |
| 30-abr-2025 | Baja convicción | 22/22 | 19 | 3 | 14 |
| 30-abr-2025 | Student, solo riesgo | 22/22 | 18 | 4 | 9 |

En el modelo base, las probabilidades puntuales van de 38,8% a 43,4% en
diciembre y de 40,9% a 46,9% en abril. Sus cotas superiores alcanzan
44,69%–49,34% y 46,82%–52,85%, respectivamente. El control usa la cota,
no solo la frecuencia observada. En baja convicción las cotas mínimas son
48,34% y 47,93%; todas exceden el límite.

Sin márgenes de muestreo, **16/22 y 3/22** pasarían los controles puntuales
de riesgo de los cinco modelos y del estrés Student. Es un diagnóstico sobre
las mismas simulaciones, no una autorización alternativa ni prueba de que
esas inversiones sean adecuadas. Aumentar trayectorias reduciría error de
Monte Carlo, pero no garantiza admisión ni corrige error del modelo. No se
cambian semillas, límites, parámetros ni composición tras ver los resultados.

CASH pasa los controles de selección y queda como salida de seguridad. La
confirmación archivada compara CASH con CASH; no confirma las inversiones
rechazadas. La etiqueta de estabilidad alta se refiere a esa salida del
conjunto finito y no acredita una cartera óptima identificada.

## Alcance y continuación

Se cierra la atribución de rechazos de las finalistas de este piloto. No se
atribuye cada candidata descartada durante búsqueda o cribado. Los márgenes
son aproximaciones sobre trayectorias simuladas, no intervalos de confianza
predictiva; el CVaR emplea una aproximación asintótica. El estrés Student
conserva su papel exclusivo de riesgo, sin pronósticos económicos.

Los topes prudenciales, anclas y probabilidades siguen sin calibración fuera
de muestra. No se acredita que conservar efectivo fuera la mejor decisión.
Permanecen **0/48 cortes causales certificados**. Siguen pendientes la
realización de flujos compatible con la simulación, fundamentales y perfiles
históricos suficientes, y una cuenta continua neta de costes. Los registros
prospectivos deben madurar conservando sus sellos.

## Reproducción

```sh
node scripts/attribute_scoped_pilot.mjs
node --test tests/scoped-pilot-attribution.test.mjs
```

El workflow `scoped-pilot-attribution.yml` reproduce el informe y exige que
no cambie. Requiere los módulos exactos del piloto; un cambio futuro del
motor debe usar una copia de esos módulos o ejecutarse desde este commit.
