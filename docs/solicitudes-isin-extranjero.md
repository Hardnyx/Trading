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
