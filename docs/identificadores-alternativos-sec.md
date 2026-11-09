# Identificadores alternativos originales SEC para CUSIP inválidos

**Hito:** H1.2. **Primer corte retrospectivo:** 31-dic-2024. La fuente de SPY contiene 26 posiciones de renta variable clasificadas `EC` cuyo CUSIP original no supera la comprobación de identidad. Su peso original conjunto es 0,03033173560207 del NAV. No se eliminan del denominador ni se convierten en instrumentos por inferencia.

`scripts/historical_sec_alternate_identity.py` reabre la declaración N-PORT original del SEC y comprueba que los hashes, fechas, posiciones, CUSIP, nombre, título y peso coincidan con el informe congelado. Extrae **únicamente identificadores expresamente etiquetados en el XML**:

- ISIN directo `<isin>` u `<other otherDesc="ISIN">`, comprobado según el dígito ISO 6166.
- Ticker literal de `<ticker>` o etiqueta equivalente. Solo sirve de pista.
- LEI, si figura en el nodo original. Por ahora se conserva como pista sin validar correspondencia de clase de acción.

Un ISIN válido que empiece por `US` puede contener una cadena CUSIP estructuralmente válida en posiciones 3 a 11. Se registra **solo como candidato de revisión por estructura de ISIN original**, nunca como corrección automática del CUSIP ni identidad confirmada. Múltiples candidatos distintos se marcan ambiguos; ISIN extranjeros o con dígito erróneo no producen CUSIP estadounidense.

## Ejecución y entregables

```bash
python scripts/historical_sec_alternate_identity.py --verify
python scripts/historical_sec_alternate_identity.py \
  --output out/historical-sec-alternate-identity-v1.json \
  --csv out/historical-sec-alternate-identity-v1.csv
```

Se publican un resumen de estados, pesos y recuentos, más un CSV de 26 observaciones que incluye la posición SEC y el hash original para posterior cotejo de documentación independiente. Los campos derivables no pasan a `historical_vendor_identity.py` sin otra fuente independiente que valide la identidad de emisor, título, clase, vigencia y precio. Los símbolos y nombres no se usan para forzar un match, y no se consulta la cartera actual.

**Criterio de aceptación:** reclasificar únicamente lo que ya contiene el documento original, preservar 26/26 posiciones y el peso original íntegro, rechazar ambigüedades, fechas futuras y alteraciones del archivo, sin modificar el motor de inversión. **No cierra H1.2**: un candidato estructural no prueba la historia temporal del security master ni su continuidad bursátil, y los 351 CUSIP válidos restantes siguen necesitando datos licenciados de proveedor.

## Resultado observado en el archivo SEC

La [CI 42545960677](https://github.com/Hardnyx/Trading/actions/runs/42545960677), commit [`557664d`](https://github.com/Hardnyx/Trading/commit/557664d3f42d84e8c324c5a5c9ddf41d816d8530), encontró **26 posiciones con un ISIN extranjero válido** en el XML original, sin un US ISIN que permita extraer CUSIP estadounidense. No se certificó ninguna identidad de precio. Este resultado modifica la vía de recuperación: se preparan [solicitudes por ISIN extranjero](solicitudes-isin-extranjero.md) en lugar de intentar completar esos 26 CUSIP como si fueran títulos estadounidenses.
