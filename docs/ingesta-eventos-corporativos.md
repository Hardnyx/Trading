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
