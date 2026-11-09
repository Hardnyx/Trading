# Solicitudes históricas por ISIN extranjero original

**Hito:** H1.2. **Fecha de decisión investigada:** 31-dic-2024. La revisión de los originales SEC detectó **26 posiciones con CUSIP inválido, clasificadas EC, que contienen ISIN no estadounidenses válidos**. No se pueden fabricar CUSIP estadounidenses a partir de ISIN extranjeros ni confundir estos títulos con un universo de acciones estadounidenses sin verificar su plaza de negociación.

Se construye la cola con `scripts/historical_foreign_isin_requests.py`, que parte del XML SEC archivado y verificado nuevamente. Se exigen ISIN explícitos y validación ISO 6166, exactamente uno por posición, original publicado antes del corte y correspondencia exacta de posición, accession, SHA256 y peso. Un ISIN duplicado en varias posiciones origina una sola consulta de proveedor, pero conserva el peso y las posiciones por separado. Si hay múltiples identificadores distintos, se lleva a una cola de ambigüedad sin recuperar nada por nombre.

## Archivos públicos de solicitud

```bash
python scripts/historical_foreign_isin_requests.py --verify
python scripts/historical_foreign_isin_requests.py \
  --output out/historical-foreign-isin-requests-v1.json \
  --csv out/historical-foreign-isin-requests-v1.csv \
  --review out/historical-foreign-isin-unresolved-v1.csv
```

El CSV principal contiene el ISIN, la posición original de SPY, su peso, las pistas originales de ticker/LEI, el accession y la fecha en que se consideró pública la fuente. El CSV de excepciones conserva las filas que no sean inequívocas. El JSON público contiene la cobertura y un `request_sha256` determinista que se usará para vincular respuestas futuras.

## Resultado observado y cobertura real

En el commit [`6fb7f8a`](https://github.com/Hardnyx/Trading/commit/6fb7f8a6d0465e0b2efb2abf9c658510b78ad2d8) se verificaron nuevamente todos los datos originales: [GitHub Actions 42546555231](https://github.com/Hardnyx/Trading/actions/runs/42546555231), ejecución de tests completa y generación de los archivos de solicitud.

| Medida de la fuente SEC de 2024 | Resultado |
|---|---:|
| Posiciones originales con CUSIP inválido | 26 |
| Solicitudes por ISIN extranjero válido, distinto y explícito | 26 |
| Filas con ISIN irresuelto o ambiguo | 0 |
| Peso SPY original cubierto por solicitudes por ISIN | 0,03033174 del NAV |
| Identificadores de proveedor verificados | 0 |
| Cortes del motor completo admitidos | 0 de 48 |

Los 26 ISIN son observaciones **expresas del documento SEC**, no conversiones de nombres ni de ticker. La ausencia de ambigüedad en esos códigos no demuestra que haya un registro histórico de cotización o que cada instrumento fuese invertible bajo nuestras restricciones. Se mantiene intacto el CUSIP original inválido y la separación respecto de las 351 solicitudes por CUSIP válido.

**Dato requerido del proveedor:** security master que devuelva una identidad de instrumento con vigencia, bolsa/MIC original, divisa de cotización, tipo de título, posibles ADR y cadena de eventos societarios, junto con fuente y fecha de publicación o reconstrucción. El ISIN por sí solo no establece que la acción fuera negociable en la bolsa considerada, ni qué serie de precios usar.

Esta cola se mantiene **separada** de las 351 solicitudes basadas en CUSIP válidos. Ninguno de los 26 ISIN queda incorporado al motor ni certificado automáticamente. El criterio de aceptación técnico es recuperar de forma reproducible los identificadores de fuente como **solicitudes de adquisición de datos**, sin modificar el denominador histórico, los resultados del piloto o los parámetros del modelo; H1.2 permanece abierto.


## Importar respuestas originales del proveedor por ISIN extranjero

El adaptador [`historical_foreign_isin_vendor_identity.py`](../scripts/historical_foreign_isin_vendor_identity.py) permite procesar una respuesta del proveedor **sin convertirla en una serie de precios validada**. Reutiliza la comprobación de CSV, hashes SHA256, rutas seguras, fechas de instantánea y descarga, espacio de nombres estable y vigencia de `historical_vendor_identity.py`; la clave de emparejamiento es el **ISIN original** y nunca un ticker.

Generar la plantilla pública del manifiesto:

```bash
python scripts/historical_foreign_isin_vendor_identity.py \
  --template out/historical-foreign-isin-vendor-manifest-template-v1.json
```

El `manifest.json` privado debe colocarse en `input/historical-foreign-isin-vendor-v1/`, mantener los campos `protocol`, `cut`, `request_sha256` y `source_original_sha256` de la plantilla, y completar `exports` con registros como el siguiente (marcadores, **no prueba histórica**):

```json
{
  "path": "provider.csv",
  "sha256": "<SHA256 real de los bytes CSV>",
  "provider": "<proveedor autorizado>",
  "source_reference": "<ID de extracción>",
  "snapshot_as_of": "2024-12-31",
  "retrieved_at": "<hora de descarga UTC real, formato ISO 8601>",
  "temporal_basis": "retrospective_asof_export"
}
```

Las columnas **exactas** del CSV privado son:

```csv
original_isin,provider_instrument_id,id_namespace,security_type,currency,exchange_mic,valid_from,valid_to,record_as_of
```

`record_as_of` debe coincidir con `snapshot_as_of`. La vigencia `valid_to` es exclusiva, y ambos extremos deben existir para proponer una identidad efectiva al 31-dic-2024. Se permiten monedas de cotización distintas de USD y se conservan explícitas: **ni la convertibilidad histórica ni la accesibilidad en bolsas estadounidenses quedan demostradas por eso**. Nombres, tickers, ISIN usados como supuestos IDs permanentes, registros fuera de fecha, claves compartidas entre diferentes ISIN y respuestas discordantes no pasan el control.

```bash
python scripts/historical_foreign_isin_vendor_identity.py \
  --evidence-dir input/historical-foreign-isin-vendor-v1 \
  --report out/historical-foreign-isin-vendor-reconciliation-v1.json
```

Todo extracto licenciado y el informe detallado quedan **locales** bajo `input/` y `out/` ignorados por Git. CI publica **solo el manifiesto vacío** unido al hash del origen SEC. Aun una coincidencia inequívoca lleva el estado `retrospective-foreign-identity-candidate`, sin certificación de precio, eventos societarios, moneda, vigencia probada por tercero ni elegibilidad para replay.

**Aceptación técnica:** ejecutar pruebas adversariales con exportaciones sintéticas y generar el manifiesto vacío cotejando 26 ISIN del original SEC. **H1.2 sigue bloqueado** hasta recibir e investigar datos originales de proveedor, resolver identidades y disponibilidad histórica de precios y definir qué títulos extranjeros/ADR cumplen criterios de negociación en el universo objetivo.
