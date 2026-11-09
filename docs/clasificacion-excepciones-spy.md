# Clasificación original de excepciones CUSIP en SPY

**Hito:** H1.2, diagnóstico de la documentación SEC del 31-dic-2024. **Alcance:** las 26 posiciones del informe original de SPY con CUSIP inválido o ausente. No se usan cotizaciones futuras, constituyentes actuales ni rentabilidades realizadas.

La [cola separada de excepciones](cola-priorizada-identidad-spy.md) identifica 26 posiciones cuya participación positiva conjunta es **0,03033174 del NAV original**. Antes de solicitarlas como acciones históricas, hay que verificar el **tipo de activo descrito en la propia fuente SEC**. Un ETF puede contener instrumentos que no sean acciones comunes y que, por ello, no deban tratarse como faltantes de un security master bursátil.

`scripts/historical_spy_exception_classification.py` abre el XML N-PORT originalmente archivado para el SPY y comprueba sus bytes y metadatos contra los hashes y objetos derivados conservados. Recorre todas las posiciones en orden, verifica CUSIP, nombre, título y porcentaje original, y solamente después extrae para las 26 excepciones las etiquetas literales `assetCat`, `curCd`, `payoffProfile` e `issuerTyp`.

## Comprobación

```bash
python scripts/historical_spy_exception_classification.py --verify
python scripts/historical_spy_exception_classification.py \
  --output out/historical-sec-cusip-exception-review-v1.json \
  --csv out/historical-sec-cusip-exception-review-v1.csv
```

El JSON contiene el número y peso por categoría original declarada. El CSV conserva las 26 filas y su posición exacta para revisión del documento. Ambos se generan en CI como artefactos públicos. La clasificación es descriptiva: `EC` se identifica como una etiqueta de acciones en N-PORT, pero un `assetCat` distinto o ausente **no** equivale automáticamente a no ser negociable; la categoría y el vínculo de precios requieren comprobación independiente.

## Resultado sobre el documento original

La ejecución de [GitHub Actions 42544845334](https://github.com/Hardnyx/Trading/actions/runs/42544845334) verificó que **26 de 26 posiciones con CUSIP inválido o ausente fueron declaradas con `assetCat = EC`** en el XML N-PORT original de SPY, por un peso conjunto de **0,03033173560207 del NAV** (3,03 puntos porcentuales). Las pruebas del programa y la reproducción de los archivos SEC terminaron correctamente.

Por tanto, la hipótesis de que esas 26 posiciones fueran principalmente instrumentos no accionarios **no está respaldada por las categorías originales**. Permanecen como observaciones de renta variable común con identidad pendiente de conciliar. No se debe excluirlas para mejorar artificialmente la cobertura del piloto. La etiqueta `EC` no aporta el CUSIP correcto, prueba de negociación continua ni precio históricamente disponible.

**Criterio de aceptación:** conciliación de la clasificación original de las 26 excepciones sin cambio del denominador SPY ni inclusión de valores inventados; casos adversariales que rechazan XML alterado, pesos cambiados, posiciones reordenadas, CUSIP incorrecto y entidades XML no seguras. No se declara ninguna identidad permanente ni se autoriza un nuevo corte integral.

**Bloqueos:** recuperar los IDs históricos y continuidad de los 351 CUSIP válidos, resolver de manera independiente los campos no concluyentes de las 26 excepciones, reconstruir eventos, precios e historial de instrumentos deslistados. El diagnóstico no reduce automáticamente el universo objetivo ni valida el rendimiento del motor.
