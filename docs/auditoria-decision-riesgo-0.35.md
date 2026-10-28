# Auditoría de decisión y riesgo · 0.35.0

28 de octubre de 2026. Precios al 27-oct. La cartera mostrada en la captura
es SGOV 35%, IGSB 35%, SHV 25% y efectivo 5%, desde USD 100.000 en efectivo.
No se operó una cuenta del usuario.

## Qué explica esa composición

Hay dos causas distintas: el criterio usado para escoger pesos y los
supuestos económicos que se consideran admisibles. La corrección del primero
no valida los segundos ni obliga a comprar acciones.

En 0.34.1, no poder demostrar superioridad en todos los modelos habilitaba
el desempate por menor rotación y luego riesgo. Esto podía sustituir el
objetivo de crecimiento por mínimo riesgo aunque hubiese una diferencia
relevante para la utilidad en el peor modelo. No rechazar una diferencia
con pocas simulaciones no demuestra que dos decisiones sean equivalentes.

Se congelan las candidatas ya encontradas, los datos y el mandato. La
atribución usa la captura del 28-oct a las 12:27 UTC y el contraste de riesgo
la de las 19:04 UTC, ambas con precios del 27-oct y hashes registrados. En
3.000 escenarios independientes, la candidata que cambia SGOV por SHY da:

| Comparación condicional | Equivalente cierto del peor modelo |
|---|---:|
| SGOV 35%, IGSB 35%, SHV 25%, CASH 5% | USD 103.976,10 |
| SHY 35%, IGSB 35%, SHV 25%, CASH 5% | USD 104.182,00 |
| Diferencia | USD 205,90 |

Las cotas inferiores pareadas por modelo rondan USD 146, por encima del
umbral de USD 100. Es una comparación monetaria **dentro del modelo**, no
una ganancia observada. Los insumos se conservan en
[la lista congelada](auditorias/policy-pool-0.34.1.json) y los resultados en
[la atribución de la política](auditorias/policy-attribution-0.34.1.json).

### Corrección del desempate

Se prioriza la mayor utilidad en el peor modelo. Reducir rotación exige que
la **cota superior** de pérdida frente a la mejor candidata quede dentro del
umbral económico del mandato. Con igual rotación se prioriza la utilidad;
el riesgo ya se controla en las restricciones y en la función de utilidad.
Los rankings inciertos se siguen mostrando, pero son un conjunto distinto
de los empates económicos cuya pérdida está acotada.

La comparación respeta la forma del objetivo:

```math
\min_\ell \mu_{\mathrm{líder},\ell}
-\min_k \mu_{\mathrm{alternativa},k}
=\max_k\min_\ell(\mu_{\mathrm{líder},\ell}-\mu_{\mathrm{alternativa},k}).
```

Se emparejan todas las parejas de modelos, con multiplicidad por posibles
líderes y alternativas. Las cotas son aproximaciones de Monte Carlo y la
conversión monetaria usa una utilidad base estimada. No contienen toda la
incertidumbre de parámetros ni son confianza predictiva. Una única elegida
llega a confirmación independiente; se conserva el control de cinco modelos,
los costes, el mandato completo y el estrés Student solo de riesgo.

### El supuesto que hace defensiva la solución

Una sensibilidad del **mismo conjunto finito** obtiene:

| Hipótesis incluidas | Peso en acciones de la mejor candidata | Peor equivalente estimado |
|---|---:|---:|
| Solo modelo base | 35% | USD 105.097 |
| Cuatro modelos, sin baja convicción | 45% | USD 104.297 |
| Los cinco modelos declarados | 0% | USD 104.182 |

Baja convicción declara prima accionaria e IC cero. Al maximizar la utilidad
bajo ese conjunto, el carry de bonos cortos puede dominar la renta variable.
El resultado expresa una convención prudente que falta calibrar. No demuestra
que las acciones vayan a caer ni que una cartera de bonos sea universalmente
mejor para crecer. La interfaz muestra el objetivo en el peor caso y el
supuesto de prima e IC cero. No se retira un modelo después de ver la captura
para obtener una asignación preferida.

## Contraste histórico inmediato del riesgo

Se reconstruyen 54 orígenes mensuales desde abril de 2022 hasta septiembre
de 2026, usando solo precios anteriores a cada corte para estimar parámetros.
Se puntúan horizontes de 1/5/21 sesiones, con el mismo adelanto de dos sesiones
del registro prospectivo. Hay 12 instrumentos, cuatro cestas fijas y tres
leyes de varianza: fallback actual con reversión, EWMA dinámico sencillo y
EWMA plano. Se utilizan 2.000 escenarios por modelo y origen.

El código de precios es el del motor. GJR queda desactivado: no se trasladan
los ajustes actuales a fechas anteriores. Tampoco se inventan anclas de BPA,
TIR o macro con vintages históricos. Todos los modelos comparten una media
histórica calculada antes del corte como centrado auxiliar. Se contrasta el
componente de varianza, no la predicción económica completa.

### Cesta de la captura a 21 sesiones

| Modelo de varianza | Orígenes no solapados | Excepciones VaR95 | CRPS medio, menor es mejor |
|---|---:|---:|---:|
| Fallback actual con reversión | 38 | 2 | 0,0021284 |
| EWMA dinámico sencillo | 38 | 2 | 0,0021298 |
| EWMA plano | 38 | 2 | 0,0021397 |

La frecuencia de excepciones es 5,26%, con intervalo binomial bajo
independencia [0,64%; 17,75%]. La muestra no permite concluir que la tasa
esté cerca del 5% con precisión útil. Solo hay dos observaciones de cola;
Expected Shortfall sigue débilmente identificado.

Las mejoras de CRPS del fallback son 0,00001123 frente a EWMA plano y
0,00000137 frente a EWMA dinámico. Los dos intervalos por bloques de origen
incluyen cero. Son las dos comparaciones principales fijadas en el protocolo,
con intervalos al 97,5% para corregir su multiplicidad. No hay superioridad
resuelta sobre las referencias sencillas.

Las pruebas binomiales de cobertura se presentan con sus hipótesis; se
ajustan por Holm para las 144 celdas. No rechazar con pocos datos no valida
la distribución. Se conservan años separados, cobertura, QLIKE, residuo de
ES y comparaciones pareadas en
[el resumen numérico](auditorias/price-risk-reconstruction-2026-10-28.json).

### Límites de la evidencia

- Los precios ajustados y el universo se conocen hoy; no se certifican
  vintages originales ni supervivencia histórica.
- La cesta actual se escogió después de esos años. Es un estrés de exposición
  fija, no un backtest de una estrategia que hubiera seleccionado esos pesos.
- No se prueba aquí el GJR aceptado, macro, la media de las anclas, fiscalidad,
  dividendos en efectivo ni ejecución del broker.
- Un contraste a 21 sesiones no valida el CVaR publicado a doce meses.
- Los resultados no cambian automáticamente la ley de precios ni promueven
  parámetros. El registro prospectivo conserva sus sellos originales.

El CRPS compara distribuciones según una puntuación propia; aquí se aproxima
con una malla de cuantiles, sin convertirlo en una prueba de rentabilidad.
Referencia primaria:
[Gneiting y Raftery (2007)](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf).
La necesidad de contrastar ES directamente, en lugar de inferirlo solo de
la cobertura de VaR, se discute en
[Acerbi y Székely (2014)](https://www.msci.com/resources/research/articles/2014/Research_Insight_Backtesting_Expected_Shortfall_December_2014.pdf).
El residuo mostrado aquí es diagnóstico y no se presenta como su test formal.

## Reproducción y comprobaciones

```sh
node scripts/price_risk_replay.mjs
python scripts/summarize_price_risk.py
node --test tests/price-risk-replay.test.mjs tests/reliable-selection.test.mjs
python -m unittest tests.test_price_risk_summary
git show 06fece6494ade19bd6c541abf45150968eed4516:dist/data/volatility.json > out/policy-volatility.json
node scripts/selection_policy_audit.mjs --market data/snapshots/2026-10/2026-10-28T122753076354Z.json --volatility out/policy-volatility.json --pool docs/auditorias/policy-pool-0.34.1.json
```

La CLI usa `dist/data/market.json`. Para repetir el contraste fechado,
`runPriceRiskReplay(snapshot)` admite la captura versionada
`data/snapshots/2026-10/2026-10-28T190445339804Z.json`; el JSON registra
su hash y el del código ejecutado. Una captura posterior es otro experimento.

CI conserva una ejecución acotada (`--quick`, 24 orígenes y 1.000 escenarios)
como diagnóstico en sombra. El JSON fechado de esta auditoría conserva el
contraste completo; el acotado no lo sustituye.

Las pruebas verifican ausencia de información futura, desenlaces en las
fechas originales, pares completos, exclusión de solapamiento y separación
entre incertidumbre del ranking y pérdida económica acotada. La validación
local completa comprende 242 pruebas JavaScript y 141 Python. Aprobarlas
no acredita capacidad predictiva ni ventaja económica fuera de muestra.
