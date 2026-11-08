# Libro de cuenta del motor integral: efectivo y derechos por cobrar

**Hito H3.2:** primer motor de contabilidad aislado, sin cohorte prospectiva integral admisible todavía.

El adaptador `scripts/full_engine_cash_ledger.mjs` recibe decisiones ya selladas, un calendario explícito de sesiones observadas, cierres originales sin ajuste, índices completos de distribución, splits, costos de ejecución y flujos externos fechados con SHA256. **No genera pronósticos ni decide objetivos nuevos.** El rebalanceo simulado usa la cartera objetivo publicada y el cierre **de la primera sesión observada después del corte**, nunca el cierre del mismo día.

El libro lleva cantidades de cada instrumento y efectivo liquidado. En la fecha exdividendo registra un derecho por cobrar con base en las participaciones tenidas **antes** de cualquier rebalanceo al cierre; en la fecha de pago cancela ese derecho y acredita efectivo neto de retención. Las divisiones de acciones multiplican cantidades antes de valorar el cierre sin crear rentabilidad ficticia. Los depósitos, retiros e intereses deben tener eventos externos con fecha y huella. La tasa de efectivo predicha no equivale a un interés realizado.

Se verifica diariamente la identidad:

`NAV_t - NAV_(t-1) = variación de valor de acciones + derechos por cobrar nuevos - retenciones + flujos externos + intereses efectivamente cobrados - costos de negociación`.

Una discrepancia detiene el libro. También lo hacen un cierre ausente, un índice de dividendos incompleto, una operación imposible de financiar, una publicación posterior a la apertura siguiente, una orden asignada a la segunda sesión para eludir un problema en la primera, un dividendo sin fecha de pago reconciliable, FX sin fuente o retiros programados sin detalle de liquidación. Se conserva el prefijo observado y el motivo del bloqueo, sin completar la cuenta con CASH ficticio.

La contabilidad emplea los costos base de `policy.mjs` y calcula órdenes **hipotéticas a partir de pesos objetivos**. No implica que el broker hubiera ejecutado las órdenes ni reproduce necesariamente los filtros originales de `trade_plan` de la propuesta. No se debe mezclar con `account_replay.mjs`, que trabaja con unidades sintéticas de precios ajustados por retorno total. Tampoco se debe agregar dividendos en efectivo a la rentabilidad de una serie ajustada.

**Pruebas:** `node --test tests/full-engine-cash-ledger.test.mjs` cubre fechas, efectivo, venta total, liquidación y retención de dividendos, splits, flujos externos, costos, reconciliación de NAV y fallos ante fuentes ausentes.

**Pendiente:** un origen mensual original, precios de ejecución capturados en su momento, eventos corporativos con cobertura oficial, consentimiento de la fuente y conciliación con la política real de órdenes. Hasta entonces, H3.2 es un adaptador de investigación sin libro de resultados de mercado, no una prueba de rendimiento financiero.

Se comprueban todas las sesiones originales de SPY dentro del intervalo, sin permitir ocultar la primera sesión de ejecución. Se rechazan eventos duplicados, ajustes corporativos no conciliados y una emisión anterior al cierre de origen; un deslistado exige un registro de liquidación específico que este adaptador todavía no admite.

**Semántica de HOLD:** la orden sellada con estado `hold` no establece una nueva asignación objetivo ni invoca `tradePlan`; conserva las unidades y el efectivo existentes incluso con dividendos pendientes. La distribución publicada se conserva únicamente como evidencia para revisar divergencias con la cuenta simulada. La decisión `proposed` sigue calculando el rebalanceo a precios de la primera sesión observada.
