# Cuenta histórica TTM: protocolo anterior a los resultados

Protocolo `reconstructed-ttm-account-v1`, fijado el 29-oct-2026. Contraste
económico de la señal por bloques reconstruida, no del motor completo ni
de una cartera que se hubiera emitido entonces. No modifica producción,
IC, anclas, parámetros, pesos o cohortes prospectivas.

## Entradas y fechas

- Mercado congelado del commit `8dcd06cfd06b2ca34ca6fb64e31d5b6344525cd5`,
  fichero `dist/data/market.json`, corte 28-oct-2026.
- TTM archivado en `docs/auditorias/ttm-signal-inputs-2026-10-29.json.gz`.
  Debe coincidir su hash del mercado. No se vuelven a descargar datos.
- Todos los orígenes mensuales del paquete, sin elegir fechas por resultado.
  La orden se fija con el cierre del origen y se representa en el cierre de
  la segunda sesión SPY posterior. No se opera en el cierre que generó señal.
- Se reutiliza `rawSignal` de `ttm_signal_replay.mjs`: valoración por bloques,
  TTM presentado antes del origen, dividendos históricos y exposición
  estimada con el pasado. No se consulta su retorno posterior para elegir.
- Orden descendente por señal, desempate alfabético. Cinco acciones, con
  un mínimo de treinta señales utilizables. Sin muestra suficiente se
  mantienen las posiciones; no se completa con activos elegidos después.

## Cuentas y referencias predeterminadas

Todas empiezan con USD 100.000 en efectivo, al mismo corte, sin aportes,
retiros, impuestos ni interés de efectivo. La exposición objetivo de 35%
permite comparar con SPY sin superar su tope global actual. Es una manga
diagnóstica, no el resultado del optimizador ni su presupuesto de riesgo.

| Cuenta | Regla |
|---|---|
| `ttm_monthly` | 7% a cada una de las cinco acciones de mayor señal, 65% CASH; revisar cada mes |
| `yield_monthly` | Misma muestra, exposición y revisión; ordenar solo por BPA/precio |
| `ttm_initial_hold` | Primera cesta TTM, luego mantener unidades y efectivo sin rebalancear |
| `index_monthly` | 35% SPY, 65% CASH, rebalanceo mensual |
| `index_initial_hold` | Primera compra 35% SPY, luego mantener sin rebalancear |
| `cash` | Mantener efectivo sin remuneración |

No se buscan otros números de posiciones, exposiciones, ventanas o reglas
al observar el resultado. Las cuentas que mantienen pueden desviarse de
su exposición inicial por los movimientos de precios. La referencia mensual
sí conserva la misma exposición objetivo que las señales mensuales.

## Contabilidad y costes

Se utiliza una cuenta de **unidades sintéticas de retorno total**, valoradas
con `adj_close`. Incluye la reinversión bruta implícita del proveedor; no se
vuelven a sumar dividendos, ni se interpreta como acciones ejecutadas,
pagos de caja en pay-date o la política de dividendos en efectivo de la app.
Los precios sin ajustar, pay-dates, fiscalidad y operaciones corporativas
originales son necesarios para certificar esa otra contabilidad.

El efectivo es una partida separada, sin financiación ni ventas en corto.
El plan de transición reutiliza `tradePlan` de producción, deduciendo
costes del patrimonio antes de asignar el objetivo. Comisión fija y variable
cero; spread completo 5 pb y slippage 2 pb: coste de un lado 4,5 pb del
nominal de cada compra o venta. Se repite toda la cuenta con spread y
slippage triples, sin escoger la variante favorable. Unidades fraccionarias,
sin filtro de lote o mínimo de orden. No hay liquidación final ficticia.

Se conservan NAV diario, unidades, efectivo, orden, fecha de decisión,
ejecución, composición anterior/posterior, operaciones y costes. Un precio
ausente, duplicado o inválido en una posición o ejecución interrumpe esa
cuenta y deja el periodo completo sin rendimiento publicable. No se avanza
el origen, no se rellena cero y no se sustituye el activo desaparecido.

## Diagnósticos fijados

- Patrimonio y retorno acumulado neto, CAGR por sesiones, máxima caída
  diaria, volatilidad realizada, costes, nominal negociado y rotación.
- Retornos por año y por meses completos. El último mes parcial se conserva
  en NAV, pero se excluye de la comparación de meses completos.
- Número de revisiones, cambios de nombres y cambios de pesos; grandes
  cambios se describen con la información disponible en la fecha. No se
  les atribuye ventaja esperada de un optimizador que aquí no se ejecuta.
- Comparaciones pareadas mensuales: TTM frente a BPA/precio, a mantener la
  primera cesta y al índice mensual. Banda descriptiva del promedio anual
  de diferencias logarítmicas, bloques móviles de doce meses, 2.000
  remuestreos, semilla 20261029. Requiere 24 meses completos consecutivos.
  Se declara cuántos bloques anuales no solapados contiene la muestra.
- Los intervalos son exploratorios por comparación, sin corrección de
  multiplicidad; no son pruebas formales de promoción. Los supuestos y el
  universo ya se eligieron con conocimiento de parte de este histórico.

## Qué permanece bloqueado

La reconstrucción usa universo, catálogo y datos ajustados actuales. Hereda
las exclusiones ex post por operaciones corporativas no conciliadas del
estudio TTM. No hay universo histórico verificado ni vintages originales.
El filtro por fecha de presentación no elimina esos sesgos.

El backtest completo de producción queda bloqueado hasta poder reconstruir
holdings del benchmark (neutralización CAPM/IC), perfiles de bonos, anclas de
ETF, calidad/confianza contable y vintages macro al origen. Tampoco se
reproduce aquí la selección robusta, el GJR histórico ni la distribución de
riesgo del simulador. No se rellenan esas entradas con los valores actuales.

El resultado, favorable o adverso, se publica como evidencia limitada.
`production_eligible`, `automatic_promotion` y `prospective` permanecen falsos;
la superioridad del modelo completo sigue sin acreditar. Este protocolo y
los hashes permiten separar el alcance real de esa afirmación.
