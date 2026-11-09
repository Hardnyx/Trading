# Reproducción independiente de covarianza EWMA del piloto

**Hito:** H1.2, procedencia matemática del riesgo. **Fecha de revisión:** 8-nov-2026 UTC.

El estudio ya dispone de dos ejecuciones retrospectivas del compositor (`2024-12-31` y `2025-04-30`) con una política EWMA fijada en 2026, pero no dispone de una calibración contemporánea certificada. Para separar un error aritmético de un error de procedencia, `scripts/archived_ewma_independent_replay.py` reproduce **sin importar los cálculos JS** la matriz de covarianza anualizada registrada para cada fecha.

## Algoritmo contrastado

1. Leer `inputs.json.gz` y `results.json.gz` de `scoped-engine-pilot-v1` y verificar SHA-256 junto con el protocolo registrado.
2. Conservar exactamente los símbolos seleccionados del corte y reconstruir el activo sintético `CASH` a partir de la secuencia de fechas de `SPY`. No volver a seleccionar activos a partir de resultados.
3. Construir retornos logarítmicos de `adj_close` de cada instrumento, intersectar las sesiones y conservar como máximo las últimas 500. Comprobar que la última sesión y la cantidad coincidan con los registros del compositor.
4. Inicializar la covarianza usando la muestra convencional con divisor `n - 1` sobre hasta 60 retornos. Para cada retorno posterior, actualizar `C = λ C + (1-λ) r rᵀ`, sin centrar el choque actualizado, tal como hace `risk-math.mjs`.
5. Anualizar por 252 y multiplicar por 0,95 solo las covarianzas fuera de la diagonal; contrastar cada celda con la matriz congelada y la volatilidad registrada con tolerancias numéricas explícitas. Si el factor SPY se calcula fuera de la muestra seleccionada, conservar su intersección independiente.

No se rerrealiza la búsqueda Monte Carlo, no se reoptimiza la cartera y no se cambian parámetros ni resultados originales. El verificador falla si una cifra congelada difiere de la recomputación, si hay precios posteriores al origen, si el efectivo deja de ser sintético o si las filas y fechas no coinciden.

```bash
python scripts/archived_ewma_independent_replay.py --verify
python -m unittest tests.test_archived_ewma_independent_replay
```

CI genera un reporte en `out/archived-ewma-independent-replay-v1.json` y lo publica como artefacto de investigación. El reporte no publica los precios subyacentes ni crea resultados predictivos nuevos.

**Criterio de aceptación:** reproducir numéricamente el riesgo de los dos pilotos históricos congelados con una segunda implementación. Esto puede acreditar la aritmética **condicional a los datos guardados**, pero no su disponibilidad histórica real, ausencia de sesgo de supervivencia, ajuste GJR, calibración previa a la fecha ni calidad de las previsiones.

**Bloqueo restante:** el primer corte integral sigue en 0/48 admisibles. Recuperar y verificar fuentes originales de precios y eventos, identidad continua, selección ex ante de parámetros, fundamentales point-in-time y perfiles de bonos/ETF. No usar esta prueba de software para certificar capacidad predictiva o económica.
