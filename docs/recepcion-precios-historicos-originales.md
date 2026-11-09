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
