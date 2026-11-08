# Ingesta de evidencia de parámetros históricos de riesgo

**Hito:** H1.2. **Primera fecha de investigación:** 31 de diciembre de 2024. **Estado:** adaptador preparado; ninguna calibración histórica original certificada.

El compositor puede ejecutarse sobre dos cortes retrospectivos con la política fija de 2026 y el modo EWMA, pero esto **no** demuestra que sus parámetros, selección de modelo, fuentes de precios o hiperparámetros hubieran estado disponibles en esos cortes. El objetivo de este adaptador es recibir **evidencia local** de un ajuste, auditar la integridad de sus bytes y evitar errores elementales de anticipación. No genera nuevas previsiones ni activa cortes del replay.

## Archivos requeridos

Generar la plantilla sin datos inventados:

```bash
python scripts/historical_risk_fit_intake.py --template out/historical-risk-fit-manifest-template.json
```

Se prepara un directorio local `input/historical-risk-fit-v1/` (ignorado por Git) con `manifest.json`, `policy.json`, `training.json`, `fit.json` y archivos originales de fuentes con sus hashes SHA256 reales. La plantilla es una **solicitud**, no evidencia.

`manifest.json`: copiar la estructura de la plantilla, sustituir todos los `null` y especificar `decision_at` (hora con zona, después del cierre de Nueva York), `retrieved_at`, `source_reference`, `temporal_basis`, y los punteros con `path` y `sha256` de cada archivo. Para cada elemento de `sources` incluir `provider`, `claimed_available_at`, `collected_at` y `temporal_basis`. Se acepta `retrospective_reconstruction` o `contemporaneous_archive` como clasificación declarada, nunca como certificación automática.

`policy.json` debe ser un objeto con `schema: risk-fit-policy-v1`, `model`, `policy_id`, `selected_at`, `selection_data_end`, `selection_mode` (`fixed` o `nested-chronological`) y `all_trials_recorded: false`. El valor `false` expresa que **no** podemos certificar un registro exhaustivo de ensayos anteriores: no autoriza ocultar intentos. El inventario de nuevas pruebas sigue gobernado por `data/validation/model-trials-v1.json`.

`training.json` debe incluir `schema: risk-fit-training-v1`, `cut` y `observations`. Cada observación requiere solo `instrument_id`, `observation_date`, `label_end`, `known_at` y `source_sha256`. Las fechas y disponibilidad son aseveraciones que deben ser contrastadas con fuentes independientes antes de usar el ajuste; un `label_end` posterior al corte se rechaza. El archivo de fuente del hash declarado debe estar presente en el manifiesto y coincidir byte por byte.

`fit.json` requiere `schema: risk-fit-result-v1`, `cut`, `model`, `policy_sha256`, `training_sha256`, `fitted_at`, `observations` y `parameters` (números finitos). El auditor exige que el ajuste referencie exactamente los bytes de política y entrenamiento archivados y que la cantidad de observaciones concilie.

Ejecutar una conciliación privada:

```bash
python scripts/historical_risk_fit_intake.py --evidence-dir input/historical-risk-fit-v1 --report out/historical-risk-fit-reconciliation-v1.json
```

El resultado incluye un diagnóstico temporal, pero **no** exporta las filas de entrenamiento ni los valores numéricos de parámetros. Tampoco reproduce matemáticamente el ajuste: los parámetros pueden ser inconsistentes con los datos pese a que todos los hashes coincidan. Los archivos con licencia permanecen fuera del repositorio.

## Qué permanece bloqueado

1. Verificación independiente de la publicación original y vigencia de las fuentes, más correspondencia causal del instrumento y eventos corporativos. Un `claimed_available_at` no verifica por sí mismo la disponibilidad real.
2. Ejecución reproducible del ajuste con código y versión históricamente atribuibles, y reconciliación de los parámetros obtenidos con los declarados.
3. Registro completo de selecciones e intentos, con entrenamiento cronológico anidado cuando proceda y sin utilizar resultados del periodo confirmatorio.
4. Integración auditada con `referenceRequest` / `composeMultiStart`, sin reutilizar la política fija de 2026 como si hubiera sido decidida en 2024.

**Aceptación de esta entrega técnica:** funciona la entrada de evidencia con hashes, controles de temporalidad, referencia de filas a fuentes y casos adversariales. **No se completa H1.2**, ningún parámetro se promueve a histórico certificado y el primer corte integral sigue bloqueado. La plantilla y los tests no aportan datos nuevos del mercado.
