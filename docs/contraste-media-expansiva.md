# Contraste retrospectivo de la media de retornos

**Hito:** H4.1, diagnóstico de desarrollo previo a H1/H2/H3. **No es un estudio confirmatorio** ni una ejecución del portafolio integral.

El programa `scripts/benchmark_expanding_mean.mjs` toma el reporte publicado de ocho orígenes de acciones reconstruidas, el manifiesto congelado de pronósticos y el mercado de resultados fijado por commit. Contrasta la media predictiva de `pilot_kernel` con la referencia **expansiva de media aritmética diaria**, definida en `docs/protocolo-replay-integral-v1.json`.

La media se calcula con pares consecutivos de sesiones del calendario SPY cuyos precios ajustados figuran en la historia del activo **hasta el origen**. Se requieren al menos 252 retornos diarios válidos, y la proyección al horizonte de `h` sesiones es `(1 + media_diaria)^h - 1`. Nunca se usa una cotización posterior al origen para calcular la referencia. Se excluyen instrumentos sin 252 sesiones válidas, fechas exactas o datos admisibles; la ausencia no equivale a pronóstico nulo.

Cada par usa el **mismo rendimiento realizado** para modelo y referencia. Por origen y horizonte se calcula la media equiponderada de `MSE_referencia - MSE_modelo`. Una diferencia positiva favorece al modelo; una negativa, a la referencia. El resumen vuelve a promediar esos efectos **por origen**, no por cada activo como si fueran muestras independientes. Se mantienen los resultados inmaduros y se informan los cortes sin solapamiento; no se publica un valor p.

Para reproducir:

```bash
node scripts/benchmark_expanding_mean.mjs out/retrospective-expanding-mean-benchmark-v1.json
node --test tests/expanding-mean-benchmark.test.mjs
```

El resultado se distribuye como artefacto de GitHub Actions, con SHA256 del reporte de puntajes, manifiesto, mercado, protocolo y código. Los 48 cortes del calendario histórico se conservan explícitamente como seleccionados o excluidos.

**Limitación decisiva:** los precios ajustados pertenecen a un catálogo superviviente y fueron reconstruidos retrospectivamente; no son vintages históricos originales. Solo se archivaron ocho orígenes de pronósticos marginales, sin optimizador, órdenes, cuenta, universo integral o muestra independiente. Por ello esta métrica no demuestra una ventaja predictiva o económica, no sustituye las siete pruebas primarias y no reduce los 96 orígenes admisibles exigidos por v1.

## Resultado calculado sobre los archivos congelados

[Resumen numérico verificable](../data/historical/expanding-mean-benchmark-v1/summary.json), reproducido en GitHub Actions [ejecución 42448464922](https://github.com/Hardnyx/Trading/actions/runs/42448464922).

| Horizonte (sesiones) | Orígenes con resultados | MSE motor | MSE media expansiva | Orígenes con ventaja del motor | Orígenes sin solapamiento |
|---|---:|---:|---:|---:|---:|
| 21 | 8 | 0.013449 | 0.012703 | 0 de 8 | 8 |
| 63 | 7 | 0.026129 | 0.024323 | 2 de 7 | 5 |
| 252 | 4 | 0.354666 | 0.304823 | 0 de 4 | 1 |

**Resultado de desarrollo:** la referencia supera al motor en el MSE medio por origen en los tres horizontes. No hay potencia o muestra causal para una prueba formal; los resultados a 252 sesiones incluyen cuatro orígenes maduros pero solo **uno no solapado**. La evaluación se obtuvo antes de cualquier modificación de parámetros posterior; no se ajustan seeds, penalizaciones o anclas para revertir el resultado. El estado de la capacidad predictiva integral sigue **no acreditado**.

El cálculo de CI exige que los valores publicados se reproduzcan exactamente. En caso contrario falla la compilación y debe revisarse la procedencia o registrar un estudio distinto, sin sobrescribir estos resultados.
