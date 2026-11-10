# Ejecución selectiva de GitHub Actions

**Fecha:** 9-nov-2026. **Propósito:** conservar todas las pruebas sin repetir diagnósticos estadísticos y despliegues de Pages después de cada cambio del repositorio.

**Validar aplicación** (`.github/workflows/check.yml`) se ejecuta al modificar scripts, tests, datos, JSON de protocolos, dependencias o workflows. Mantiene `npm run check`, `npm test`, la batería Python completa y los guards de fuente histórica, registro prospectivo y sobreajuste. Los cambios que solo afectan a documentación Markdown no disparan una ejecución automática.

**Auditoría integral de investigación (manual)** (`.github/workflows/research-full.yml`) conserva los comandos de la validación extensa anterior: bootstrap, control de error familiar y Holm, potencia, HAC, auditorías de fuentes, reproducción EWMA y publicación de artefactos. Ahora responde únicamente a `workflow_dispatch`. Antes de aceptar un nuevo hito metodológico, ejecutar este workflow manualmente y citar el SHA del commit verificado; un check rápido en verde no sustituye su resultado.

**Deploy to GitHub Pages** (`.github/workflows/pages.yml`) se activa por push cuando cambian `dist/**`, `package.json`, `scripts/stamp-release.mjs` o el propio workflow. Conserva ejecución manual, `workflow_call` desde el refresh de datos y comprobaciones de la compilación publicada. No se vuelve a desplegar la web por modificaciones exclusivas de scripts de investigación o documentación.

**Protección de la separación:** `python scripts/ci_workflow_policy.py --verify` y `python -m unittest tests.test_ci_workflow_policy` comprueban los triggers, gates críticos, comandos de auditoría manual y rutas de publicación. El guard no demuestra validez predictiva, disponibilidad de datos originales, rendimiento económico ni cobertura muestral.

**Uso:** GitHub > Actions > Auditoría integral de investigación (manual) > Run workflow > main. Para una comprobación rápida también se puede ejecutar Validar aplicación manualmente. La cuota y el coste efectivo, si los hubiera, deben revisarse en la facturación de GitHub; el repositorio es público y usar ejecutores estándar normalmente no consume minutos privados.

## Comprobación del cambio, 9-nov-2026 (hora de Lima)

La separación se publicó en [`5840d04`](https://github.com/Hardnyx/Trading/commit/5840d04d025e9f1d321629c4dae49c2df514944c) y el guard en [`ef13c82`](https://github.com/Hardnyx/Trading/commit/ef13c8220dabd8e712313be77bc6d165569381f2). La [CI rápida 42758137078](https://github.com/Hardnyx/Trading/actions/runs/42758137078) finalizó correctamente: **474 pruebas Python**, 16 pasos correctos, duración del job **1 min 39 s**. El guard `ci_workflow_policy.py --verify` también pasó. El segundo commit no disparó Pages; el [despliegue 42758013286](https://github.com/Hardnyx/Trading/actions/runs/42758013286), activado al modificar su propio workflow, se completó satisfactoriamente. Una actualización automática posterior del snapshot de mercado no alteró los workflows. La auditoría estadística integral sigue disponible mediante ejecución manual, pero **no se volvió a ejecutar en esta modificación**; la evidencia predictiva y las fuentes PIT continúan pendientes.

## Procesos dependientes de Refresh market data (10-nov-2026)

La captura prospectiva de **Stock signal validation** conserva el evento de finalización de **cada** actualización de mercado, incluidas las fallidas o canceladas. La verificación `validation_watch.py` registra los meses sin evidencia y no se suprime para ahorrar tiempo. El despliegue Pages posterior se solicita únicamente si el propio ledger de señales escribió y publicó un commit con evidencia nueva; en caso contrario, se omite la segunda compilación web.

**Finite-pool opportunity uncertainty (shadow)** conserva los diagnósticos y artefactos exploratorios, pero deja de ejecutarse diariamente tras Refresh. Se ejecuta los **domingos a las 02:37 UTC** (sábados 21:37 en Lima), con lanzamientos manuales y por cambios de scripts relevantes. El trabajo observado el 10-nov-2026 duró **2 min 33 s**; la reducción a 4-5 revisiones mensuales en vez de unas 30 implica un ahorro de tiempo de cómputo estimado de 64 a 66 minutos por mes, sin afirmar ahorro facturable real.

El guard `validate_refresh_dependents()` y `tests/test_ci_refresh_dependents.py` evitan la pérdida del registro de errores upstream, la vuelta a los diagnósticos diarios y el despliegue de Pages sin nuevas publicaciones. No se modifican datos históricos, protocolos v1/v2, forecasts ni inferencia confirmatoria.

## Evitar la segunda batería Python de Pages

El primer despliegue generado por `Refresh market data` continúa ejecutando **todo** el conjunto JS y Python. La publicación posterior del ledger prospectivo puede reutilizar esa validación Python **únicamente si** se invocó desde la finalización exitosa del refresh. Aun así, el segundo despliegue ejecuta `npm run check`, `npm test` y la comprobación pública del commit/SHA servido. Para despliegues manuales, cambios directos en Pages o ejecuciones de señales sin refresh exitoso, la batería Python permanece obligatoria. Este ajuste evita repetir una validación que en los dos últimos despliegues diarios tardó aproximadamente dos minutos; no omite la primera validación ni la auditoría prospectiva específica del ledger.

## Evidencia y resultado de la auditoría (10-nov-2026)

Los cuatro cambios de implementación publicados en `main` son [`edac6c1`](https://github.com/Hardnyx/Trading/commit/edac6c1b0b0a4c2968273412f79666736d92bb43), [`d1eb649`](https://github.com/Hardnyx/Trading/commit/d1eb6491341e7392d2c89d3da2cafcd90892e428), [`c412797`](https://github.com/Hardnyx/Trading/commit/c412797dcdcb907d256b7a28538a26e5917015fe) y [`bbb92d3`](https://github.com/Hardnyx/Trading/commit/bbb92d35e2286dafdcec0d24bf260e2af627ae3c). La [CI 42766190724](https://github.com/Hardnyx/Trading/actions/runs/42766190724) se completó: **482 pruebas Python y 16 pasos correctos**, incluida la protección del registro upstream ante manipulación y la ruta condicional de Pages. La auditoría pool lanzada por el cambio de su propio workflow también concluyó correctamente. Un despliegue Pages realizado sobre el SHA anterior a la corrección del guard falló durante sus pruebas Python: no debe contarse como despliegue validado, y la siguiente publicación real comprobará la corrección también en Pages.

La próxima ejecución semanal y la optimización real de la **segunda** batería Python después de un refresh exitoso no se han observado aún, por lo que los ahorros de tiempo estimados no son cifras ejecutadas ni de facturación. H0.3 y H1 permanecen abiertos: este hito es de infraestructura, no una certificación de capacidad predictiva.

## Auditoría estática de coste y cadencia (10-nov-2026)

La política `scripts/ci_workflow_policy.py --verify`, incluida en la CI rápida, examina los **27 workflows**: admite únicamente runners estándar `ubuntu-latest` y `ubuntu-24.04`, exige límites explícitos de duración de hasta 60 minutos y fija el inventario de tres calendarios automáticos: actualización de mercado diaria (23:30 UTC), archivo histórico semanal (sábado 13:17 UTC) y diagnóstico exploratorio de pool semanal (domingo 02:37 UTC). Una ampliación de runners o de cron ahora exige revisar y modificar explícitamente esta política. Las pruebas adversariales verifican que el guard rechaza runners no estándar, timeouts excesivos y cron no aprobados.

Los commits que `refresh-data.yml` y `signal-validation.yml` publican con el `GITHUB_TOKEN` del workflow **no disparan nuevos workflows de `push`** según la regla documentada de GitHub Actions. Por ello, los filtros `dist/**` existentes no implican una segunda ejecución automática por esos commits; las publicaciones se efectúan por los jobs `workflow_call` explícitos. Esta propiedad debe volver a revisarse antes de utilizar un PAT o token de GitHub App para los commits automáticos. El guard es estático y **no consulta cuotas, facturación ni costes observados**, ni garantiza que otros cambios de configuración de la cuenta no introduzcan cargos. Ninguna prueba estadística o contrato predictivo se altera.
