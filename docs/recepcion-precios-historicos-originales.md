# Recepción de cierres históricos originales del proveedor

**Hito:** H1.2, entrada de precios negociables y reconstrucción de unidades, primer corte de investigación 31-dic-2024. No es una fuente de retorno total ni una certificación de datos point-in-time.

El catálogo congelado de investigación contiene cierres y ajustes reconstruidos con posterioridad. Las comparaciones de `historical_price_audit.py` frente a marcas N-PORT son diagnósticos, **no** una historia original de ejecuciones y distribuciones, y no resuelven sesgo de supervivencia. La ingesta `scripts/historical_raw_price_intake.py` depende de las dos pruebas de identidad de proveedor (CUSIP e ISIN) y del guardia de colisiones entre ambas rutas. **Solo requiere precios de instrumentos con una clave permanente retrospectiva no ambigua**; no inventa claves para el resto.

## Dos etapas independientes

**1. Contrato público basado en el original SEC.** Esta ejecución no requiere datos licenciados y publica solo la cantidad y clasificación de las 504 posiciones positivas del N-PORT:

```bash
python scripts/historical_raw_price_intake.py \
  --template out/historical-raw-price-source-request-v1.json
```

**2. Solicitud privada de cotizaciones.** Al disponer de ambas exportaciones de identidad fechadas, reconstruirlas desde sus CSV originales y sus hashes, generar una lista de claves permanentes sin colisiones y el manifiesto que obliga a recuperar esa misma lista:

```bash
python scripts/historical_raw_price_intake.py \
  --cusip-evidence-dir input/historical-vendor-identity-v1 \
  --isin-evidence-dir input/historical-foreign-isin-vendor-v1 \
  --private-request out/historical-private-price-requests-v1.csv \
  --private-manifest out/historical-private-price-manifest-template-v1.json
```

El resultado contiene `identity_report_sha256`. No se publican IDs ni archivos protegidos por licencia en GitHub. La solicitud incluye 252 **intervalos** mínimos de retorno diario conforme a la referencia histórica del protocolo, sin afirmar que la cifra resuelva toda la calibración de riesgo. La fecha inicial exacta queda abierta a determinar con el calendario bursátil de cada instrumento, evitando inventar 252 sesiones por conversión a días naturales.

## Formato de exportación

El CSV privado de cierres debe contener estas columnas, sin series ajustadas o retornos totales:

```csv
id_namespace,provider_instrument_id,exchange_mic,quote_currency,session_date,raw_close,record_as_of,price_basis
```

`price_basis` es literalmente `unadjusted-per-share-exchange-close`. `record_as_of` es la fecha declarada por la fuente para esa observación, entre `session_date` y el día de la instantánea. No puede exceder el corte. La propia declaración de una fecha **no autentica** que el archivo de cierre existiera en 2024.

El `manifest.json` de `input/historical-raw-price-v1/` incluye `protocol`, `cut`, `identity_report_sha256`, `price_basis` y `exports`, según la plantilla privada. Cada entrada de `exports` requiere: `path` relativo, `sha256`, `provider`, `source_reference`, `snapshot_as_of`, `retrieved_at` con zona UTC y `temporal_basis` (`retrospective_asof_export` o `contemporaneous_archive`). La segunda etiqueta no prueba por sí misma contemporaneidad.

```bash
python scripts/historical_raw_price_intake.py \
  --cusip-evidence-dir input/historical-vendor-identity-v1 \
  --isin-evidence-dir input/historical-foreign-isin-vendor-v1 \
  --price-evidence-dir input/historical-raw-price-v1 \
  --private-report out/historical-private-price-receipt-v1.json
```

Se rechazan precios futuros, filas de claves fuera del security master candidato, moneda/MIC discordantes, cierres no positivos o no finitos, columnas de precios ajustados, filas duplicadas del mismo instrumento y sesión, hashes modificados y rutas que escapan al directorio privado. Se contabiliza la cobertura **sin retirar del denominador** las posiciones que carecen de identidad o historial.

El reporte no certifica la validez de sesiones, la proveniencia original frente a un archivo reconstruido, splits, dividendos, delistings, FX ni precios ejecutables; no genera retornos ajustados ni activa `composeMultiStart`. Incluso 252 intervalos de precios **no** habilitan un corte integral. El primer paso siguiente es obtener los CSV históricos autorizados y comprobar las acciones corporativas y fechas de captura.

## Resultado comprobado

El commit [`6052f90`](https://github.com/Hardnyx/Trading/commit/6052f9064894ccbb9b967fc9fb2cf0f194ea23a8) superó la [CI 42566051139](https://github.com/Hardnyx/Trading/actions/runs/42566051139) y el [despliegue 42566051088](https://github.com/Hardnyx/Trading/actions/runs/42566051088), con **363 pruebas Python aprobadas**. La ejecución pública recuperó el contrato de **504 posiciones SEC positivas** y registró **0 filas de precios originales licenciados**. Las pruebas de importación usan archivos sintéticos, no datos de inversión recuperados.

**Aceptación técnica alcanzada:** la recepción de exportaciones CSV puede comprobar integridad, fechas declaradas, identidad, moneda y unicidad, sin provocar cambios en las carteras. **H1.2 no está cerrado**: no hay precios de proveedor suficientes para un solo replay integral ni prueba de que esas cotizaciones, su denominador o la ley de retornos fueran conocidos en el corte histórico.

## Integridad de los valores brutos en la conciliación

Cada entrada privada de seguridad ahora contiene `raw_bar_sha256`, calculado sobre **todas las barras ordenadas por sesión**, con su cierre, fecha de registro, moneda y plaza. Es distinto del SHA256 del CSV original: el primero fija el subconjunto de observaciones por identidad y el segundo preserva el archivo fuente. Dos reportes con fechas y recuentos idénticos pero precios o fechas declaradas de conocimiento distintos **no pueden tener el mismo recibo**. El cálculo es estable ante cambios de orden de las filas de la exportación y no certifica por sí mismo la autenticidad del proveedor.

## Moneda original vinculada a la identidad

La solicitud privada de cierres exige `quote_currency` explícito en el identificador permanente reconciliado. El importador **rechaza el campo ausente**: no sustituye por USD aunque la ruta CUSIP actualmente solo acepte registros estadounidenses cotizados en USD. La ruta ISIN extranjero conserva la moneda original declarada por el proveedor (por ejemplo GBP), que debe coincidir con el CSV de precios y con la plaza MIC. No se convierte GBP a USD ni se infiere un tipo de cambio histórico o una ejecución estadounidense. La prueba conjunta CUSIP/ISIN utiliza filas sintéticas de proveedor para verificar ambos recorridos.

## Verificación del contrato de moneda

El [commit `bdae67a`](https://github.com/Hardnyx/Trading/commit/bdae67a0da8bb8d6d7c9539cf1a8f21cf7be328e) completó [CI 42610807340](https://github.com/Hardnyx/Trading/actions/runs/42610807340) y [Pages 42610807404](https://github.com/Hardnyx/Trading/actions/runs/42610807404) correctamente, con **383 pruebas Python aprobadas**. La nueva prueba integrada comprueba que el proveedor CUSIP preserve USD y que la vía ISIN extranjero conserve GBP, rechazando la sustitución de la divisa y las claves sin moneda. Son identidades y barras **sintéticas**, no cotizaciones recibidas del mercado. La plantilla pública mantiene 504 posiciones positivas originales sin filas privadas de proveedor; ninguna fecha del motor completo se habilita por este cambio.
