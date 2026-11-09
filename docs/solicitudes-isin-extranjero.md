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

## Estado comprobado de la ingesta

El commit [`832f490`](https://github.com/Hardnyx/Trading/commit/832f490560666840a60da48fc7b5b1663dee7422) pasó [GitHub Actions 42552606975](https://github.com/Hardnyx/Trading/actions/runs/42552606975) y [GitHub Pages 42552607033](https://github.com/Hardnyx/Trading/actions/runs/42552607033) el 9-nov-2026 UTC. La CI ejecutó **348 pruebas Python**, incluidas pruebas con exportaciones sintéticas, fechas incompatibles, hashes adulterados, IDs inestables y respuestas discrepantes. El generador volvió a leer las 26 solicitudes del origen SEC y produjo un **manifiesto vacío**, con **0 registros reales de proveedor**.

No hay todavía ninguna identidad extranjera certificada, serie de cotizaciones verificable ni corte del motor integral admisible. **El cierre técnico del adaptador no debe interpretarse como avance medido de validación predictiva.**

## Contrato temporal común CUSIP/ISIN

El importador de ISIN extranjero y el de CUSIP usan ahora la misma validación de intervalo efectivo y fecha declarada del proveedor. Una identidad que empieza después del `record_as_of` queda en cuarentena, aunque esté vigente al corte. Las pruebas incluyen **dos ISIN con dígito de control válido** y comprueban que una clave permanente reutilizada para dos ISIN originales no genera candidatos independientes. Las pruebas usan datos sintéticos y no sustituyen verificaciones de pertenencia histórica, proveedor, precios o FX.

## Verificación de exclusividad y fecha efectiva

La [CI 42614115839](https://github.com/Hardnyx/Trading/actions/runs/42614115839) aprobó 387 pruebas Python para el commit [`7d991f5`](https://github.com/Hardnyx/Trading/commit/7d991f51d03560200f778245b05b476ff6e5ba63), incluido un caso de colisión de ID nativo entre dos ISIN de dígito correcto y una instantánea anterior a la vigencia efectiva. El resumen SEC público mantiene **26 posiciones ISIN extranjeras y 478 con CUSIP válido** de 504 positivas, con **0 filas reales de proveedor**. Estas son condiciones técnicas necesarias, no datos nuevos sobre rentabilidad ni una prueba independiente de disponibilidad point-in-time.

## Exclusividad entre orígenes de proveedor

Dos ISIN originales distintos con el mismo identificador nativo y namespace se clasifican como conflicto **incluso si cada fila declara un proveedor diferente**. La conciliación conserva además el nombre del proveedor dentro de la clave candidata, en lugar de asumir que dos respuestas de orígenes distintos se corroboran automáticamente. El control es conservador y puede requerir investigar cambios de identificador legítimos; en ningún caso habilita por sí solo la inversión ni valida el precio histórico.

## Verificación cruzada de orígenes

La [CI 42615902722](https://github.com/Hardnyx/Trading/actions/runs/42615902722) aprobó **394 pruebas Python** para el commit [`b9dbd0a`](https://github.com/Hardnyx/Trading/commit/b9dbd0a061f6d27ac4ab3974b1ffa569cdf00c9f). Las pruebas adversariales incluyen una clave FIGI compartida entre dos ISIN distintos desde proveedores diferentes: ambos quedan sin candidato. La plantilla SEC conserva 26 ISIN extranjeros originales dentro de las 504 posiciones positivas, sin que se haya recibido ninguna respuesta comercial. No existe todavía prueba de disponibilidad histórica autenticada ni de universo completo.
