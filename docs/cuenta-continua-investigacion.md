# Decisiones mensuales con estado de cuenta continuo

**Hito:** H3.3, integración de estado patrimonial. **Estado:** prototipo de investigación con pruebas sintéticas; ninguna cohorte confirmatoria nueva está activada.

## Problema y alcance

El \`referenceRequest\` fijo de v2 usa \`settings.account.enabled=false\`, \`capital=100000\` y ninguna posición anterior. Repetirlo cada mes supone abrir una cuenta nueva en efectivo, no gestionar una cartera existente. Aplicar sus pesos después a una cuenta ya invertida cambiaría el problema de decisión y podría atribuir retrospectivamente al motor órdenes que nunca calculó.

El compositor v0.35.0 ya admite un estado explícito: \`settings.account={enabled:true,cash,positions:[{symbol,quantity,costBasis}]}\`. El adaptador \`scripts/continuous_account_origin.mjs\` aprovecha esa interfaz sin modificar el núcleo de precios, la política, las semillas, los límites ni los archivos congelados del protocolo.

**La diferencia entre una cuenta inicial vacía y una cuenta existente puede alterar realmente la decisión.** Por eso el adaptador crea la cohorte distinta \`continuous-account-research-v1\` y no reemplaza los sellos de \`full-engine-prospective-registration-v2\`. Nunca se mezclan resultados de las dos políticas como si fueran un mismo experimento.

## Contrato de continuidad

El operador proporciona el snapshot original del cierre, el resultado íntegro de \`full_engine_cash_ledger.mjs\`, sus bytes exactos y la hora de emisión. \`prepareContinuousAccountRequest\` exige:

1. El último NAV y el snapshot corresponden **al mismo cierre observado**, posterior a la sesión y anterior a la siguiente apertura conservadora; no hay una marca futura en precios, órdenes, flujos ni NAV.
2. El libro termina íntegro en esa fecha, con identidad diaria conciliada, cantidades reales hipotéticas, efectivo liquidado no negativo y ausencia de posiciones ocultas.
3. Cada posición tiene cierre bruto original en USD y cantidad exacta que concilia con \`final_units\`; la suma de valores y efectivo coincide con NAV.
4. No hay dividendos por cobrar pendientes, retenciones diferidas ni otras partidas que \`currentAccount\` no pueda representar. Si los hay, el adaptador **rechaza el nuevo origen**; no los agrega al cash.
5. Se preserva el mandato y el costo del preset de referencia, sin buscar otro seed, horizonte o presupuesto de búsqueda para ajustar el resultado.

Se genera una solicitud de \`composeMultiStart\` con la misma lógica y búsqueda original, pero cuenta habilitada, capital igual al NAV y cantidades traídas del libro. Se registra SHA256 de los bytes del estado previo y se mantiene explícita la condición \`confirmatory_eligible=false\`. \`continuousAccountHandoff\` evita que la fase de investigación altere la semilla o el presupuesto. \`composeContinuousAccountResearch\` es una entrada separada de investigación; **no llama a \`captureMonthlyProposal\`**, no produce un sello v2 y no certifica la fuente ni la primera publicación por sí misma.

## Qué se ha demostrado y qué no

Las pruebas verifican la igualdad entre cantidades y pesos reconstruidos por el propio \`currentAccount\`, la conservación del cash, la ausencia de filtración desde fechas futuras y el rechazo de derechos por cobrar. No existe una secuencia mensual de decisiones nuevas compuesta y sellada con entradas originales. Los hechos de mercado, días feriados, pagos efectivos y cumplimiento de órdenes aún no están certificados.

La cohorte adicional queda asentada en el registro append-only de intentos, sin selección de variante por rendimiento. Antes de proponer pruebas confirmatorias deberán registrarse expresamente su política, origen inicial, calendario, reglas de cuenta, incertidumbre, potencia y muestras futuras independientes, conforme a la [política de sobreajuste](politica-control-sobreajuste.md).

**Pruebas:** \`node --test tests/continuous-account-origin.test.mjs\`. H3.3 no se cierra hasta reproducir una cadena de decisiones mensuales y una cuenta continua con datos de primera captura y todas las partidas reconciliadas.

**Inmutabilidad entre preparación y ejecución:** el adaptador conserva además los SHA256 de la solicitud completa y del snapshot de decisión. Antes de ejecutar el motor, los coteja con sus entradas actuales; así se rechaza un cambio posterior de supuestos, precios o datos de mercado aun cuando se conserve la misma fecha de corte. No son certificados de primera publicación externos.

## Cuenta con derechos por cobrar: cohorte v2 de investigación

`prepareSegregatedAccountRequest` conserva el NAV contable, pero prepara la decisión sobre **NAV invertible = NAV total menos derechos pendientes**. El estado original incluye el importe de cada derecho, su ex-date, pay-date, cantidad e importe por participación. La función exige que cada derecho coincida con un único asiento de devengo ya registrado, que no haya sido pagado y que la suma concilie con el NAV. Un evento con fuente futura, una divergencia o un derecho duplicado provoca rechazo.

El motor v0.35.0 no modifica su ley de retornos ni optimiza los derechos como activos negociables. Solo recibe cantidades y efectivo disponibles en `settings.account`, mientras el informe mantiene `total_account_nav`, `investable_account_nav`, `segregated_receivables`, `account_basis` y el hash del libro. El libro de ejecución reconoce el mismo `account_basis='settled-investable-only'` exclusivamente cuando se identifica la cohorte `continuous-account-research-v2`; no transforma retroactivamente ninguna decisión del protocolo integral v2.

La cohorte anterior `continuous-account-research-v1` sigue rechazando derechos pendientes. Esta modificación es deliberadamente incompatible para propósitos de investigación; no se suman sus resultados. Las pruebas comprueban derechos pendientes, asientos repetidos, cálculos de capital y pagos posteriores sin utilizar retornos para elegir un parámetro. Se mantiene pendiente la certificación del origen independiente, la fecha de primera publicación, el calendario oficial y la cuenta continua sobre sellos reales. El reconocimiento contable de un derecho **no acredita que el emisor realmente lo haya pagado**.
