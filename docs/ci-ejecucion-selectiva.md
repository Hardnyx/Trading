# Ejecución selectiva de GitHub Actions

**Fecha:** 9-nov-2026. **Propósito:** conservar todas las pruebas sin repetir diagnósticos estadísticos y despliegues de Pages después de cada cambio del repositorio.

**Validar aplicación** (`.github/workflows/check.yml`) se ejecuta al modificar scripts, tests, datos, JSON de protocolos, dependencias o workflows. Mantiene `npm run check`, `npm test`, la batería Python completa y los guards de fuente histórica, registro prospectivo y sobreajuste. Los cambios que solo afectan a documentación Markdown no disparan una ejecución automática.

**Auditoría integral de investigación (manual)** (`.github/workflows/research-full.yml`) conserva los comandos de la validación extensa anterior: bootstrap, control de error familiar y Holm, potencia, HAC, auditorías de fuentes, reproducción EWMA y publicación de artefactos. Ahora responde únicamente a `workflow_dispatch`. Antes de aceptar un nuevo hito metodológico, ejecutar este workflow manualmente y citar el SHA del commit verificado; un check rápido en verde no sustituye su resultado.

**Deploy to GitHub Pages** (`.github/workflows/pages.yml`) se activa por push cuando cambian `dist/**`, `package.json`, `scripts/stamp-release.mjs` o el propio workflow. Conserva ejecución manual, `workflow_call` desde el refresh de datos y comprobaciones de la compilación publicada. No se vuelve a desplegar la web por modificaciones exclusivas de scripts de investigación o documentación.

**Protección de la separación:** `python scripts/ci_workflow_policy.py --verify` y `python -m unittest tests.test_ci_workflow_policy` comprueban los triggers, gates críticos, comandos de auditoría manual y rutas de publicación. El guard no demuestra validez predictiva, disponibilidad de datos originales, rendimiento económico ni cobertura muestral.

**Uso:** GitHub > Actions > Auditoría integral de investigación (manual) > Run workflow > main. Para una comprobación rápida también se puede ejecutar Validar aplicación manualmente. La cuota y el coste efectivo, si los hubiera, deben revisarse en la facturación de GitHub; el repositorio es público y usar ejecutores estándar normalmente no consume minutos privados.

## Comprobación del cambio, 9-nov-2026 (hora de Lima)

La separación se publicó en [`5840d04`](https://github.com/Hardnyx/Trading/commit/5840d04d025e9f1d321629c4dae49c2df514944c) y el guard en [`ef13c82`](https://github.com/Hardnyx/Trading/commit/ef13c8220dabd8e712313be77bc6d165569381f2). La [CI rápida 42758137078](https://github.com/Hardnyx/Trading/actions/runs/42758137078) finalizó correctamente: **474 pruebas Python**, 16 pasos correctos, duración del job **1 min 39 s**. El guard `ci_workflow_policy.py --verify` también pasó. El segundo commit no disparó Pages; el [despliegue 42758013286](https://github.com/Hardnyx/Trading/actions/runs/42758013286), activado al modificar su propio workflow, se completó satisfactoriamente. Una actualización automática posterior del snapshot de mercado no alteró los workflows. La auditoría estadística integral sigue disponible mediante ejecución manual, pero **no se volvió a ejecutar en esta modificación**; la evidencia predictiva y las fuentes PIT continúan pendientes.
