# Cola priorizada de identidad histórica de SPY

**Hito:** H1.2, recuperación de fuentes para el corte de investigación 31-dic-2024. **Alcance:** 351 CUSIP válidos que figuran en el informe SEC público de SPY y están ausentes de la selección retrospectiva del piloto. No son recomendaciones ni un universo invertible verificado.

La [auditoría de pertenencia](pertenencia-historica-spy.md) cuantificó una brecha de **0,38488811 del NAV original de SPY**. De esta, **0,35455637** corresponde a posiciones con CUSIP válido ausentes del piloto y **0,03033174** corresponde a posiciones con CUSIP original inválido o ausente. Esta descomposición surgió de la prueba sobre archivos SEC reales; no puede sustituirse por una equivalencia ficticia entre el total omitido y los 351 CUSIP. El nuevo generador `scripts/historical_priority_vendor_queue.py` vincula cada CUSIP omitido con las **posiciones originales y sus hashes documentales**, preservando la solicitud completa de 504 posiciones de `historical_vendor_identity.py`.

## Exportar la cola de investigación

```bash
python scripts/historical_priority_vendor_queue.py \
  --template out/historical-priority-vendor-requests-v1.csv \
  --summary out/historical-priority-vendor-requests-v1.json
```

El CSV principal contiene únicamente **351 CUSIP válidos** con prioridad por peso documentado de SPY, CUSIP original, observaciones literales de ticker como **pistas no vinculantes**, posiciones originales, accession, periodo de la declaración, fecha de disponibilidad conservadora y fecha de decisión. No contiene IDs de proveedor ni precios. El JSON de resumen conserva los hashes de procedencia y el total conciliado de peso. CI genera ambos archivos públicos como artefactos, pero **jamás publica exportaciones privadas**.

La salida adicional `out/historical-priority-cusip-exceptions-v1.csv` contiene las posiciones SEC con **CUSIP original inválido o ausente**, peso, accession y número de fila para corregir la documentación antes de pedir un enlace de precios. La fecha, pesos y nombres no se completan por inferencia. Este archivo es una solicitud de revisión de fuente, no una petición de mapeo al security master.

El orden de prioridad **no** utiliza rendimientos realizados, sobrevida del emisor, éxito predictivo ni composición actual. No modifica el protocolo, el motor, los escenarios Monte Carlo ni la muestra confirmatoria. La pertenencia a SPY por sí sola no basta para aprobar una acción.

## Solicitar e ingresar datos de un proveedor

Usar el CSV anterior como lista de investigación para solicitar un **security master histórico** que cubra vigencias, cambios de identificación, deslistes y precios originales. El proveedor debe devolver el formato estricto documentado en [importación de identidad histórica](importacion-identidad-historica.md), no completar los campos de salida de este CSV.

Para conciliar localmente la exportación autorizada con el contrato existente:

```bash
python scripts/historical_priority_vendor_queue.py \
  --evidence-dir input/historical-vendor-identity-v1 \
  --local-report out/historical-priority-vendor-reconciliation-v1.json
```

El manifiesto privado mantiene `request_sha256` calculado sobre las **504 posiciones originales**, no sobre la sublista de 351. Esto evita que un proveedor devuelva solo las coincidencias más fáciles y que el denominador cambie sin registrarlo.

La conciliación reaprovecha los controles de SHA256, vigencia, moneda, MIC, tipo de valor y exclusividad CUSIP/ID del adaptador preexistente. La salida privada compara los estados por **CUSIP distinto**, sin contar como duplicados los diferentes lotes/posiciones de un mismo CUSIP, y conserva los pesos originales por estado. Incluso una coincidencia inequívoca se etiqueta `retrospective-identity-candidate`: no certifica disponibilidad real en 2024, desliste, precios de ejecución ni eventos corporativos.

## Resultados comprobados con los originales SEC

La ejecución [42544204365](https://github.com/Hardnyx/Trading/actions/runs/42544204365) del commit [`b856614`](https://github.com/Hardnyx/Trading/commit/b856614263d74dc29cf24532c88f68153a6ef714) completó las pruebas de aplicación, las pruebas Python y la generación del CSV y el JSON sobre el archivo congelado de SEC. El despliegue web [42544204368](https://github.com/Hardnyx/Trading/actions/runs/42544204368) también se completó.

| Resultado sobre el corte del 31-dic-2024 | Valor |
|---|---:|
| CUSIP válidos sin representación en el piloto | 351 |
| Peso original SPY de los CUSIP válidos omitidos | 0,35455637 del NAV |
| Posiciones originales con CUSIP inválido o ausente | 26 |
| Peso de posiciones con identificador defectuoso | 0,03033174 del NAV |
| Peso total no cubierto por el piloto | 0,38488811 del NAV |
| Identidades permanentes del proveedor certificadas | 0 |
| Cortes admisibles del motor integral | 0 de 48 |

La discrepancia del primer intento quedó registrada por la [CI fallida 42543721270](https://github.com/Hardnyx/Trading/actions/runs/42543721270): los 351 CUSIP válidos **no** representaban por sí solos el peso completo de 0,38488811. El arreglo evita un test con un total incorrecto y genera dos colas diferenciadas. Ningún porcentaje anterior se redistribuye para ocultar las 26 excepciones.

## Criterio de aceptación y límites

**Entrega técnica:** reproducir una solicitud priorizada y otra de excepciones de CUSIP, con pesos y posiciones que cuadren exactamente con SEC, enlazar cada fila con el manifiesto congelado, ofrecer una conciliación reproducible de futuros extractos y probar rechazos de alteraciones y ambigüedades.

**H1.2 sigue bloqueado:** no existen todavía respuestas originales de un proveedor que certifiquen las 351 identidades y su historia. Tampoco está demostrado que este conjunto sea todo el universo estadounidense elegible, ni que cada posición del informe continuara vigente al cierre de 2024. El primer corte completo sigue inadmisible y la capacidad predictiva no está validada.
