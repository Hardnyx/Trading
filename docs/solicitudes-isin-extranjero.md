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

**Dato requerido del proveedor:** security master que devuelva una identidad de instrumento con vigencia, bolsa/MIC original, divisa de cotización, tipo de título, posibles ADR y cadena de eventos societarios, junto con fuente y fecha de publicación o reconstrucción. El ISIN por sí solo no establece que la acción fuera negociable en la bolsa considerada, ni qué serie de precios usar.

Esta cola se mantiene **separada** de las 351 solicitudes basadas en CUSIP válidos. Ninguno de los 26 ISIN queda incorporado al motor ni certificado automáticamente. El criterio de aceptación técnico es recuperar de forma reproducible los identificadores de fuente como **solicitudes de adquisición de datos**, sin modificar el denominador histórico, los resultados del piloto o los parámetros del modelo; H1.2 permanece abierto.
