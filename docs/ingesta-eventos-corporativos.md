# Ingesta histórica de acciones corporativas y dividendos

**Hito:** H1.3, en preparación mientras H1.2 sigue bloqueado. **Primer corte examinado:** 31-dic-2024 (muestra de desarrollo retrospectivo). **Criterio técnico:** registrar eventos corporativos por instrumento permanente, fecha y evidencia de fuente, sin corregir automáticamente los precios ni crear dividendos recibidos antes de su fecha de pago.

El módulo `scripts/historical_corporate_action_intake.py` reutiliza el security master y las cotizaciones brutas del proveedor previamente conciliadas. Los eventos solo se asocian a una clave `(id_namespace, provider_instrument_id)` respaldada por el origen SEC, junto con MIC y divisa. La solicitud de eventos es independiente de los retornos posteriores y no altera universos, reglas de selección ni parámetros del motor.

## Plantilla pública reproducible

```bash
python scripts/historical_corporate_action_intake.py \
  --template out/historical-corporate-action-request-v1.json
```

Esta ejecución reabre las fuentes SEC originales, conserva **504 posiciones positivas** y comunica la solicitud sin revelar claves privadas del proveedor. **No implica haber recibido archivos de eventos.**

## Fuente privada y controles

Para obtener un manifiesto de acciones corporativas vinculado al hash exacto del reporte de precios originales:

```bash
python scripts/historical_corporate_action_intake.py \
  --cusip-evidence-dir input/historical-vendor-identity-v1 \
  --isin-evidence-dir input/historical-foreign-isin-vendor-v1 \
  --price-evidence-dir input/historical-raw-price-v1 \
  --private-manifest out/historical-private-corporate-action-manifest-v1.json
```

El `manifest.json` de `input/historical-corporate-actions-v1/` debe conservar los campos `protocol`, `cut`, `identity_report_sha256` y `raw_price_report_sha256` de la plantilla privada. Su matriz `exports` contiene `path`, `sha256`, `provider`, `source_reference`, `snapshot_as_of`, `retrieved_at` con zona horaria y `temporal_basis`. Los valores del proveedor se mantienen locales. El CSV debe usar exactamente:

```csv
id_namespace,provider_instrument_id,exchange_mic,quote_currency,event_id,event_type,announced_on,record_as_of,ex_date,pay_date,split_new_shares,split_old_shares,cash_per_share,cash_currency
```

Los tipos admitidos como **observaciones** son `SPLIT`, `CASH_DIVIDEND`, `SPECIAL_CASH_DIVIDEND`, `STOCK_DIVIDEND`, `SPINOFF`, `MERGER` y `DELISTING`. Los cuatro últimos tipos no reciben interpretación económica: quedan señalados como eventos sin reconstruir. Los splits requieren numerador y denominador positivos y no admiten pagos en efectivo. Los dividendos exigen importe positivo y divisa de cotización coherente, además de fechas ex y de pago válidas.

La fecha `record_as_of` debe ser posterior o igual al anuncio y anterior o igual a la instantánea declarada, que tampoco puede superar el corte. Eventos con `ex_date` futura quedan **fuera de la historia de entrenamiento**, aunque se conociera su anuncio. Un dividendo con fecha de pago posterior al corte conserva el estado `unsettled-cash-payment-at-cut` y no se suma a efectivo disponible. Ni una fecha declarada ni una exportación retrospectiva acreditan que la información fuera realmente accesible entonces.

```bash
python scripts/historical_corporate_action_intake.py \
  --cusip-evidence-dir input/historical-vendor-identity-v1 \
  --isin-evidence-dir input/historical-foreign-isin-vendor-v1 \
  --price-evidence-dir input/historical-raw-price-v1 \
  --event-evidence-dir input/historical-corporate-actions-v1 \
  --private-report out/historical-private-corporate-action-reconciliation-v1.json
```

Las pruebas detectan claves de proveedor inexistentes, MIC/divisa incompatibles, IDs duplicados, múltiples importes del mismo tipo de evento y fecha, anuncios tardíos, eventos futuros, fechas de pago incompatibles, ratios/efectivo no finitos y hashes alterados. Los estados diagnósticos se mantienen sin autorizar ajustes de precios, pago de dividendos ni operaciones.

**Criterio de cierre:** recuperar eventos reales desde fuentes autorizadas, contrastar su primera disponibilidad con evidencias externas, conciliar splits y su base accionaria, derechos ex-date/pago, efectivo, reorganizaciones, deslistes y eventuales ajustes de FX con las cotizaciones ejecutables. Las pruebas de software no constituyen evidencia de que esos datos existan ni de que el motor prediga retornos.

## Resultado verificado en CI

El commit [`f6d034d`](https://github.com/Hardnyx/Trading/commit/f6d034d8321846d3da8e45fbdb2feb16f671993f) aprobó [GitHub Actions 42567881890](https://github.com/Hardnyx/Trading/actions/runs/42567881890) y [Pages 42567881899](https://github.com/Hardnyx/Trading/actions/runs/42567881899), con **373 pruebas Python exitosas**. El workflow reabrió el contrato para **504 posiciones positivas de SPY** y generó solo la solicitud pública: **0 eventos corporativos reales del proveedor importados**. Los casos de prueba de splits, dividendos, fechas futuras y reorganizaciones son sintéticos.

La recepción técnica **no cierra H1.3**, ni acredita que una fuente exista, que sus eventos fueran públicos en cada fecha, que los dividendos se pagaran efectivamente o que la cuenta del backtest esté conciliada. El motor y las 48 fechas del protocolo se mantienen sin aptitud de replay integral.

## Auditoría de eventos contra las barras originales

El control vincula el reporte privado de eventos a **las mismas filas de precios que dieron lugar al reporte original**; no acepta sustituir el reporte o los precios después de calcular sus hashes. Para un split o dividendo cuya fecha ex ya ocurrió, busca el cierre bruto de la fecha ex y la observación inmediatamente anterior disponible. Si falta alguno o hay más de **siete días naturales** entre las dos observaciones, conserva el evento como `missing-ex-date-raw-price-bracket` y no como candidato. Esta regla es un filtro conservador de revisión, **no** una prueba del calendario oficial de negociación. Los demás valores también siguen sin autenticación point-in-time.

Si `record_as_of` supera la `ex_date`, el evento se clasifica `post-effective-event-record-quarantined`: una exportación conocida solo después de la fecha ex no se usa para reconstruir cómo se habría anticipado o procesado el evento. Para splits, el reporte privado calcula por separado la variación bruta del cierre y la variación neutralizada mecánicamente por el ratio declarado, sin confundirla con retorno total ni generar caja. Para dividendos no añade efectivo ni reinvierte automáticamente la distribución.

Una clave de proveedor **sin filas de eventos** queda como `no-event-row-not-proof-of-event-absence`; un archivo vacío no demuestra que no hubo dividendos, splits o deslistes. La cobertura documental de eventos debe acreditarse por fuera del CSV. Todos los registros y diagnósticos privados permanecen fuera de CI y del repositorio.
