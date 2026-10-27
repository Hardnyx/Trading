# Auditoría de cambios posteriores a 0.14.0 — 27 de octubre de 2026

## Alcance y resultado

Base anterior: `915ac4ede5729f8cde2664c3a6a3b1b7ffaa1396`.
Último commit de código examinado: `a9d2de2b3a6cd723d18eb301b9826c9f0572a760`.
El intervalo hasta ese commit contiene **13 commits de código/documentación y 2 actualizaciones automáticas de datos**. Se examinó también el refresco de cierre `6bb69cc`, que eleva a tres las actualizaciones de datos revisadas. La versión resultante es **0.17.0**. La atribución a Claude procede de la solicitud; los metadatos Git identifican al titular de la cuenta como autor de los cambios de código.

Se confirman **siete hallazgos funcionales: dos P1 y cinco P2**. P1 significa corrección prioritaria por afectar materialmente un resultado mostrado; P2, fallo condicionado a una configuración o inconsistencia que debe resolverse antes de interpretar su evidencia como validación del modelo.

| ID | Prioridad | Hallazgo | Cambio que lo introduce |
|---|---|---|---|
| H7 | P1 | BKNG vuelve a aceptar un BPA que mezcla bases anteriores y posteriores al split 25:1 | `8578718`, publicado desde `a802107` |
| H1 | P1 | El valor presente con BPA continuado utiliza otro múltiplo que la fórmula y el escenario base | `aba14ba` |
| H2 | P2 | El registro diario etiqueta como producción una distribución distinta de la que simula la página | `ecfefba` |
| H3 | P2 | El efectivo retirado continúa generando intereses en las trayectorias | `4934b79` |
| H4 | P2 | La evaluación posterior del efectivo remunerado registra un retorno realizado de cero | `4934b79` |
| H5 | P2 | La transformación Student-t modifica la covarianza que el motor afirma conservar | `8d6813c` |
| H6 | P2 | Un fallo transitorio de precios deja resultados del registro diario sin puntuar permanentemente | `ecfefba` |

El informe registra hallazgos y propuestas de corrección. No modifica el motor, los datos publicados ni los sellos prospectivos. El resultado de cero incidencias del refresco final no implica que los datos hayan superado todas las conciliaciones: H7 muestra una protección que deja de ejecutarse.

## H7 — Regresión crítica de la base por acción de BKNG

**Localización:** `scripts/refresh_data.py:242` (nuevo filtro de formularios), `refresh_data.py:606` (comprobación que se omite al faltar beneficio neto), `refresh_data.py:684` (activación de recuperación) y `refresh_data.py:702` (protección limitada a recuperación desde un original).

La exclusión de hechos de proxy statements es correcta, pero deja `net_income: null` en BKNG. La comprobación de escala devuelve entonces `None`, como si no hubiera detectado inconsistencia. Al existir BPA y coincidir su periodo con el informe más reciente, no se recupera el documento original. La protección de componentes de distintos informes alrededor de un split solo se ejecuta si existe `original_filing_recovery.accession`. En esta ruta no existe, y el BPA inconsistente queda habilitado.

**Evidencia de regresión entre snapshots:** en `915ac4e` y `570cee3`, BKNG tenía `eps: null`, `eps_unverified: 167.95` y la bandera `original_eps_split_vintage_unverified`. En `a802107` y `6bb69cc` tiene `eps: 167.95`, sin bandera, sin beneficio neto y sin recuperación original. El split 25:1 permanece correctamente identificado en los datos: el problema no es su clasificación como escisión.

El TTM publicado se forma como `165,57 + 3,88 − 1,50 = 167,95`. El primer término proviene del 10-K de 2025, presentado antes del split; los otros dos provienen de un 10-Q posterior, con cifras reexpresadas. El 10-K declara que no incorpora el split y los informes trimestrales posteriores indican ajuste retroactivo de cifras por acción. Una conversión mecánica del primer término a la nueva base daría `165,57 / 25 + 3,88 − 1,50 ≈ 9,0028`, sujeta a redondeo y conciliación del informe completo. No se propone aceptar ese cálculo como un nuevo dato verificado sin completar esa conciliación.

**Reproducción en la página pública, F5 → BKNG:** precio 153,14 USD; BPA utilizado 167,95 USD; P/E mostrado 0,9; valor presente 2.925,55 USD; supuesto descuento frente al precio de **+1.810,4%**. `fundamentalForecast()` devuelve `valid: true` y modo central 18,28% anual. La ausencia de protección puede contaminar la selección de instrumentos y las propuestas, aunque no se afirma que BKNG haya sido elegido en una cartera concreta.

**Corrección propuesta:** aplicar la conciliación de base por acción a cualquier TTM que atraviese un split, independientemente de la presencia de beneficio neto o de la ruta de recuperación. Mantener el BPA bloqueado cuando no se puede demostrar una base común. No restaurar los hechos de proxy statements descartados. Añadir una prueba integral con componentes de distintos informes, split vigente, beneficio neto ausente e informe trimestral actualizado.

**Fuentes primarias contrastadas:** [10-K 2025 de BKNG](https://www.sec.gov/Archives/edgar/data/1075531/000107553126000009/bkng-20251231.htm), [10-Q marzo 2026](https://www.sec.gov/Archives/edgar/data/1075531/000107553126000025/bkng-20260331.htm) y [10-Q junio 2026](https://www.sec.gov/Archives/edgar/data/1075531/000107553126000037/bkng-20260630.htm).

## H1 — Valor presente y fórmula incompatibles al seleccionar BPA continuado

**Localización:** `dist/assets/js/research-model.mjs:387` y `dist/assets/js/ui/views.mjs:1361`, con fórmula en `views.mjs:1465`.

`fundamentalForecast()` aplica ahora la reversión parcial del P/E al retorno esperado. Sin embargo, la rama de BPA continuado sigue utilizando `forecast.model` como valor presente principal. La rama de BPA reportado utiliza la valoración con el múltiplo de referencia. La fórmula y los escenarios de BPA continuado siguen mostrando ese múltiplo de referencia.

**Reproducción comprobada en la página pública:** F5 → OXY → BPA para previsión propia → operaciones continuadas. Supuestos predeterminados: BPA 3,39 USD, crecimiento 2%, múltiplo 13, descuento 10%, horizonte 3 años.

| Concepto | Resultado |
|---|---:|
| Valor presente coherente con P/E 13 y dividendos descontados | 37,72 USD |
| Valor presente mostrado | 50,20 USD |
| Múltiplo utilizado por el resultado mostrado | 17,6175 |
| Precio al horizonte del escenario base y de la fórmula declarada | 46,77 USD |
| Precio al horizonte mostrado al final de esa misma fórmula | 63,38 USD |

La diferencia del valor presente es aproximadamente **33,1%**. No constituye una discrepancia de redondeo ni una opinión sobre el valor de OXY: se están evaluando dos juegos de supuestos distintos dentro de la misma explicación.

**Corrección propuesta:** calcular el valor presente y sus escenarios con `valuation(valuationAsset, overrides, method)`; reservar la reversión parcial para el retorno esperado. Alternativamente, si se cambia esa convención, todos los rótulos, escenarios y términos de la fórmula deben utilizar los mismos supuestos. Añadir una comprobación de igualdad numérica de la fórmula, además de verificar que aparece el BPA seleccionado.

## H2 — El registro diario no reproduce completamente el modelo de la página

**Localización:** `scripts/risk_ledger.py:109` y `risk_ledger.py:122`; comparación con `dist/assets/js/risk-math.mjs:1` y `conditional-risk.mjs:50`.

El registro calcula EWMA después de restar la media de las 500 sesiones; la página actualiza EWMA con productos de retornos logarítmicos sin esa resta. Las inicializaciones también difieren. El registro utiliza directamente la varianza GJR publicada, mientras que la página aplica sus comprobaciones de aceptación y limita su escalador inicial. Además, los centros del retorno sellado y de las trayectorias no se definen igual.

**Reproducción con exactamente el mismo snapshot**, generado en `2026-10-27T11:02:10.674501+00:00`, corte de precios `2026-10-26`. Se comparó `instrument_forecast()` con la varianza inicial de `preparePaths()` sobre los 260 instrumentos y las mismas fuentes.

| Instrumento | Varianza diaria del registro, pp² | Varianza diaria de la página, pp² | Página frente al registro |
|---|---:|---:|---:|
| SGOV | 0,0001765454643 | 0,0004002306629 | +126,70% |
| BIL | 0,0001940463559 | 0,0004099726752 | +111,28% |
| SHV | 0,0001943336607 | 0,0004008453159 | +106,27% |
| GOOGL | 2,5973340957 | 2,4583841578 | −5,35% |

Los 19 GJR aceptados coinciden en su varianza inicial en este corte: no se observó una discrepancia efectiva por el límite del escalador en esos 19 casos. La diferencia EWMA anterior sí está presente. Aunque el registro puede estudiar una referencia independiente, no corresponde presentar sus resultados como cobertura del modelo exacto utilizado por la página.

**Corrección propuesta:** sellar la distribución efectiva calculada por el motor, incluidos centro, varianza, selección y límites, y conservar la referencia estadística como otro modelo explícito. Si se mantiene el registro actual, cambiar su identificación para evitar atribuir sus contrastes al simulador. Al cambiar la definición del modelo sellado, incrementar su versión y mantener intactos los sellos anteriores.

## H3 — Intereses sobre importes que ya se retiraron

**Localización:** introducción del rendimiento en `dist/assets/js/return-model.mjs:42`; integración pendiente en `path-model.mjs:442` y en la comprobación de liquidez posterior.

La trayectoria de CASH capitaliza el saldo inicial completo. `evaluatePaths()` resta después la suma nominal de retiros anteriores. Por ello, cada importe retirado conserva implícitamente sus intereses futuros dentro de la trayectoria original. El efectivo procedente de dividendos tampoco se incorpora a un saldo remunerado común.

**Caso determinista reproducido:** 10.000 USD, 100% CASH, rendimiento efectivo anual 5%, un año, retiro de 1.000 USD el 27 de abril de 2026, inicio el 27 de octubre de 2025, sin costos ni riesgo.

| Resultado terminal | USD |
|---|---:|
| Motor actual | 9.500,00 |
| Saldo con capitalización aplicada solo al efectivo restante | 9.475,22 |
| Exceso calculado | 24,78 |

Se utilizó la misma base temporal de 365,25 días del motor. La discrepancia puede afectar riqueza terminal, pisos de capital y disponibilidad para retiros siguientes.

**Corrección propuesta:** mantener un saldo de caja por trayectoria; devengar intereses entre flujos, acreditar cobros y descontar cada retiro en su fecha. Compartir ese tratamiento con atribución y comparación robusta. Comprobar un caso de caja pura con retiro intermedio y otro con dividendos pagados.

## H4 — La calibración posterior trata CASH remunerado como 0%

**Localización:** `dist/assets/js/distribution-ledger.mjs:132` y `journal.mjs:166`.

La nueva ancla de CASH puede generar 5%, pero `reconcileDistributionReturn()` devuelve incondicionalmente `{available:true, return:0}` para efectivo. La ruta sin conciliación también obtiene cero de su historial sintético. `evaluateJournal()` considera ese resultado puntuado y puede congelarlo posteriormente.

**Reproducción:** origen prospectivo con 100% CASH, tasa declarada 5%, horizonte de un año, pronóstico medio 5%, política de dividendos en efectivo e historial sintético a precio 1. Resultado del evaluador: `status: scored`, retorno realizado `0`, error `−0.05`.

Esto produciría un error aparente de **−5 puntos porcentuales** aun cuando el único supuesto fuera la remuneración declarada. No se verificó un rendimiento real de cuenta: el problema es que la ausencia de datos de intereses se convierte en un cero calificado como observado.

**Corrección propuesta:** separar rendimiento modelado de efectivo e intereses realmente conciliados. Si no existen movimientos o evidencia de intereses de cuenta, devolver un estado de conciliación pendiente para ese componente. No añadir automáticamente una tasa supuesta a una métrica identificada como realizada. Mantener la regla de no sobrescribir resultados ya sellados y versionar cualquier rectificación.

## H5 — La nueva marginal Student-t altera las correlaciones lineales

**Localización:** `dist/assets/js/path-model.mjs:296` y `conditional-risk.mjs:146`; la promesa de conservar la covarianza total permanece en `path-model.mjs:187`.

El motor factoriza una covarianza lineal histórica y transforma después cada shock aceptado mediante una función no lineal de cuantil normal a Student-t. La marginal mantiene aproximadamente varianza unitaria y conserva la cópula gaussiana, pero **no conserva automáticamente la correlación de Pearson** de la matriz de entrada. La varianza de una cartera y la interpretación de su descomposición dejan de coincidir exactamente con esa matriz.

**Verificación por integración numérica del propio `studentMarginal()`:** para ν = 4,0429192584, valor presente entre los GJR aceptados de este corte, `E[Z·T(Z)] ≈ 0,96823677` y `E[T(Z)²] ≈ 1,00000263`. En una pareja de un activo t y otro gaussiano con correlación latente 0,90, la correlación lineal resultante es aproximadamente **0,871412**, no 0,90. Es un caso controlado del transformador, no una correlación atribuida a una cartera del usuario.

**Corrección propuesta:** estimar la dependencia de la cópula en su espacio latente, o resolver los parámetros latentes necesarios para reproducir las covarianzas lineales buscadas, con verificación de la matriz conjunta resultante. Si se adopta deliberadamente una nueva covarianza, calcularla y mostrarla como tal; no conservar la afirmación de reconstrucción exacta anterior. Verificar conjuntamente innovaciones, correlaciones y varianza de cartera, además de cuantiles y varianzas marginales.

## H6 — Los resultados ausentes quedan bloqueados después de recuperarse el proveedor

**Localización:** `scripts/risk_ledger.py:186` y `risk_ledger.py:362`.

Si un snapshot ya tiene un corte global posterior pero un instrumento conserva precios antiguos, se escribe `missing_outcome` en el archivo de resultados de ese día. En las siguientes ejecuciones, la existencia del archivo hace que se omita todo el corte. Los precios recuperados posteriormente no llegan a puntuarse. El sello original permanece correctamente inmutable; el problema está en congelar también el estado incompleto de los resultados.

**Reproducción ejecutando `main()` dos veces en un directorio temporal:** sello del 23 de octubre; primera ejecución con corte global 26 de octubre y último precio de AAA del día 23; segunda ejecución con el precio de AAA del día 26 ya recuperado. El resultado sigue siendo `missing_outcome` en ambas ejecuciones.

**Corrección propuesta:** conservar cada resultado completo e inmutable por instrumento, manteniendo los ausentes pendientes; añadir los resultados recuperados con trazabilidad. Otra alternativa es usar archivos de revisiones de resultados que no modifiquen lo observado anteriormente. El resumen debe distinguir una sesión parcialmente puntuada de una sesión completa. No cambiar pronósticos ni elegir el resultado después de conocerlo.

## Comprobaciones realizadas y cambios favorables

- `npm test`: **167 pruebas aprobadas**, cero fallos.
- `python -m unittest discover -s tests -p 'test_*.py'`: **112 pruebas aprobadas**.
- `npm run check`: versiones de fuentes consistentes en **0.17.0**.
- Comprobación en navegador de la versión publicada y reproducción de H1 y H7 en F5. El selector contable se devolvió a «Total reportado» después de la prueba.
- Reproducciones adicionales: comparación sobre el mismo snapshot para H2, caja determinista y evaluación posterior para H3/H4, integración numérica para H5 y dos ejecuciones de puntuación aisladas para H6.
- Los workflows de validación de aplicación y despliegue asociados a `a9d2de2` estaban aprobados. Al cierre de la auditoría, la actualización completa de datos iniciada por ese commit y su despliegue también habían terminado correctamente (ejecución `40500919388`). Esto confirma la ejecución del flujo, no la validez económica de cada dato o pronóstico.

Los cambios de selección de informes periódicos (`8578718`) corrigen una causa comprobable de contaminación por proxy statements, aunque H7 identifica una protección que deja de ejecutarse después del cambio. La separación de escisiones y splits (`a9d2de2`) evita aplicar mecánicamente los ajustes de precio como aumentos de acciones; sigue siendo una clasificación heurística que requiere evidencia cuando existen inconsistencias. La propia documentación conserva el caso HON sin resolver.

El refresco final `6bb69cc`, generado en `2026-10-27T12:09:13.755089+00:00`, presenta BPA en 158 de 160 acciones y cero errores globales; V y FCX siguen sin BPA. Este aumento de cobertura debe interpretarse junto con H7: no equivale a 158 BPA conciliados. El filtro mantiene su intención de excluir formularios inadecuados, pero las comprobaciones que dependen de otras magnitudes no siempre llegan a ejecutarse.

La reversión parcial del múltiplo hace explícita una convención antes demasiado influyente y mantiene los múltiplos fijados por el usuario. Su vida media de diez años, los crecimientos y las confianzas siguen siendo supuestos, no estimaciones predictivas validadas. Las nuevas fuentes locales de tipografía y las etiquetas de proceso son coherentes con la pantalla examinada. La zona horaria automática del navegador se conserva.

La aprobación de las pruebas de software no demuestra precisión de retornos, cobertura futura del CVaR ni superioridad económica frente a alternativas netas de costos. Esas validaciones continúan pendientes, junto con la estabilidad de la selección, dependencia extrema conjunta, normalización de beneficios y conciliación real de cuenta.

## Orden de corrección propuesto

1. H7: restaurar el bloqueo de BPA sin base por acción conciliada, empezando por BKNG.
2. H1: unificar valor presente, múltiplo, fórmula y escenarios.
3. H3 y H4: completar el tratamiento del efectivo remunerado y su conciliación.
4. H2: separar o igualar el modelo sellado y el modelo efectivamente utilizado.
5. H6: permitir completar resultados ausentes sin reescribir pronósticos.
6. H5: verificar y documentar la dependencia conjunta después de cambiar las marginales.

Las correcciones deben conservar los sellos existentes y distinguir las pruebas de implementación de la validación económica pendiente.


## Seguimiento de correcciones · motor 0.18.0

Se revisaron `be9eeac` (backlog) y `db6fc47` (tickers e indicadores de cálculo), y la versión definitiva reescrita `f43efeb`. Esta última conserva el cambio visual y retira el archivo de skill del repositorio. El backlog proporcionado se mantiene actualizado como `docs/pendientes.md`. Se conservan los tickers, los indicadores de cálculo y la preferencia de movimiento reducido. Esos cambios no reparaban los siete hallazgos anteriores.

Se restauró el bloqueo de BPA con componentes anteriores al último split, tanto en el recolector como en el navegador al cargar snapshots previos. El caso BKNG queda excluido de nuevas compras sin fabricar un BPA. El valor presente con BPA continuado utiliza ahora el mismo múltiplo de referencia de sus escenarios y fórmula; el ejemplo OXY vuelve a 37,72 USD bajo los supuestos auditados.

El tratamiento del efectivo remunerado devenga intereses desde el cobro y hasta el retiro, incluidos varios flujos en un mismo intervalo. Atribución y comparación robusta comparten la capitalización. Los resultados sin intereses de cuenta observados permanecen sin conciliar en lugar de puntuar cero.

El registro de riesgo se identifica como referencia estadística; no se presenta como evaluación exacta del simulador. Los resultados inicialmente ausentes pueden completarse en archivos inmutables por instrumento, ligados al hash del sello y del snapshot fuente. La transformación Student-t conserva la cópula, pero su covarianza lineal inducida se calcula por separado para informar las contribuciones de varianza inicial. La validación empírica del motor exacto, del CVaR y de las colas conjuntas continúa pendiente.

Se amplió CI a cualquier cambio de `dist/**`, y se actualizaron el README, el estado consolidado y la tabla de implementación del documento técnico. Los puntos 24 y 25 se retiran del backlog; los puntos que exigen evidencia económica futura siguen abiertos.

La batería final aprobó 174 pruebas JavaScript y 114 Python; la comprobación de versiones aprobó 0.18.0. Las pruebas originales y las añadidas distinguen correcciones de implementación de validación predictiva.
