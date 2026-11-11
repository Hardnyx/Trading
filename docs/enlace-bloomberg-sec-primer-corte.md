# Intersección local Bloomberg v4–SEC del primer corte

**Hito:** H1.2, identidad histórica y cierres originales. **Corte:** 31-dic-2024, 16:00 Nueva York. **Alcance:** investigación retrospectiva, sin datos nuevos incorporados y sin elegibilidad de replay integral.

El colector independiente `BloombergExcelCollector_v4.0` puede generar un archivo `stage/2024-12-31/stage.json` a partir de su almacén versionado local. El archivo `market.partial.json` contiene solo el snapshot; **no** contiene los recibos por registro necesarios para esta conciliación. Los históricos recuperados hoy mediante Excel/BDH quedan clasificados como capturas actuales, no como versiones verificadas en 2024.

El auditor [`historical_bloomberg_stage_audit.py`](../scripts/historical_bloomberg_stage_audit.py) confronta **exclusivamente en la estación local autorizada** los registros normalizados de ese `stage.json` con las posiciones originales del N-PORT SPY reconstruidas por `historical_identity_requests.build_requests()`. No consulta rentabilidades posteriores, resultados de modelos, universo actual ni ajusta umbrales para conseguir más coincidencias.

## Contrato requerido

Por cada posible enlace, deben existir en el almacén v4 registros de **fuente versionada con disponibilidad declarada anterior al corte**, comprobaciones de integridad, documento y versión original, semántica verificada y evidencia de identidad vigente. Se exigen:

| Dataset v4 | Campos y restricciones |
|---|---|
| `identifier_history` | `cusip` original exacto y `ticker` histórico, sin ambigüedad, con inicio y fin de validez explícitos |
| `security_master` | `currency=USD`, `type=stock` y `exchange_mic` de cuatro caracteres, provenientes de registros versionados |
| `daily_prices` | `close` positivo sin ajuste (`unadjusted-causal`), divisa USD y sesión del 31-dic-2024; sin anticipar su primera disponibilidad |

`stage` debe preservar el límite de las 16:00 de Nueva York, su huella de snapshot y los indicadores de inelegibilidad. El auditor no se limita a una coincidencia de ticker: detecta CUSIP con múltiples claves, claves del almacén reutilizadas por varios CUSIP, conflictos de ticker, datos sin intervalo histórico, precios ajustados, cierres discrepantes y valores cuya disponibilidad declarada excede el corte.

`source_hashes` del colector enumera los originales utilizados **en los activos construidos en el stage**, no todos los originales de `normalized_asof_records`. Por ello se comprueba el formato de la huella individual y el recibo de cada registro, pero no se presume que la ausencia en `source_hashes` invalide una identidad aún no incorporada al snapshot. La autenticación contra bytes originales y credenciales de Bloomberg **no se repite aquí**: continúa siendo responsabilidad verificable de la custodia local y una auditoría independiente posterior. Los sellos autodeclarados tampoco prueban publicación efectiva en la fecha histórica.

## Ejecución local

Para generar una solicitud **solo de esquema, sin identificadores privados**:

```bat
python scripts\historical_bloomberg_stage_audit.py --template out\historical-bloomberg-first-cut-request.json
```

Tras importar originales auténticos y verificar localmente los registros históricos en el almacén Bloomberg v4, generar el `stage.json` de investigación:

```bat
.venv\Scripts\python.exe collector.py stage --cutoff 2024-12-31T16:00:00-05:00 --output "%LOCALAPPDATA%\BloombergDatos"
```

El colector puede terminar con código 2 por bloqueos y aun así escribir el `stage.json`. Desde la carpeta de Trading, ejecutar la conciliación **sin mover los originales a Git ni a CI**:

```bat
python scripts\historical_bloomberg_stage_audit.py --stage "%LOCALAPPDATA%\BloombergDatos\stage\2024-12-31\stage.json" --report out\historical-bloomberg-first-cut-receipt-v1.json
```

El informe bajo `out/` es **privado**: puede contener IDs nativos de proveedor, CUSIP y huellas originales. No debe publicarse en el repositorio ni adjuntarse a los workflows públicos si la licencia restringe su difusión. La consola solo informa conteos y no expone esos identificadores.

## Criterio de aceptación y límites

La aceptación técnica consiste en reproducir la matriz de posiciones desde N-PORT SEC, cargar el `stage.json` original, comprobar el sello de snapshot, rechazar versiones fuera de fecha/ambiguas y conservar un recibo privado con **el denominador completo**. Una coincidencia permanece etiquetada `research-only-v4-sec-source-intersection`, **no** `certified`, aunque presente cierre y MIC.

La promoción a H1 requiere además identificación jurídica continua y deslistados, fuentes independientes de primeras disponibilidades, sesiones y operaciones corporativas completas, precios ejecutables, perfiles y fundamentos del resto del universo, y procedencia causal de parámetros. El resultado de la auditoría mantiene `full_engine_eligible_cuts_added=0`, `production_eligible=false` y `predictive_validation=not-established`; no se altera H0.3 ni se emite ningún pronóstico u orden.

La batería `python -m unittest tests.test_historical_bloomberg_stage_audit` prueba el contrato con registros **sintéticos**. No hay prueba de ejecución real contra Bloomberg Terminal en esta entrega.
