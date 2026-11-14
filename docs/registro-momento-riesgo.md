# Prueba de entrada: momento de riesgo por volatilidad

**Registro:** [estudio-momento-riesgo-v1.json](estudio-momento-riesgo-v1.json), publicado en [`6a744fa`](https://github.com/Hardnyx/Trading/commit/6a744fa1) antes de calcular. Ejecución: `python scripts/risk_timing_gate.py`. Resultado: [auditorias/momento-riesgo-1964-2018.json](auditorias/momento-riesgo-1964-2018.json).

**Regla probada.** Cada fin de mes, la proporción de acciones pasa a ser 70 % × (volatilidad media histórica ÷ volatilidad EWMA actual), acotada entre 60 % y 90 %. Bonos = 95 % − acciones; efectivo, 5 %. Se compara con 70/25/5 fijo, ambos con costos de 7 pb.

## Resultado (14-nov-2026 UTC), 1964–2018, 660 meses

| | 70/25/5 fijo | Con momento de riesgo |
|---|---:|---:|
| Sharpe (sobre letras del Tesoro) | 0,430 | **0,474** |
| Retorno anual sobre letras | 4,75 % | 5,02 % |
| Volatilidad anual | 11,0 % | 10,6 % |
| Caída máxima (sobre letras) | −44,1 % | **−39,8 %** |
| Sharpe 1964–1989 / 1990–2018 | 0,280 / 0,591 | 0,293 / 0,674 |

Diferencia de Sharpe +0,043, bootstrap por bloques p = 0,022, caída máxima menor. **Veredicto registrado: respaldada.**

La proporción de acciones cambia en promedio 5 puntos por mes, entre los límites de 60 % y 90 %.

## Cómo leerlo

Es una mejora moderada: más retorno por unidad de riesgo y una caída máxima algo menor, en los dos subperiodos. **No es independiente de la literatura:** Moreira y Muir (2017) estudiaron carteras gestionadas por volatilidad con estos mismos datos de French, y trabajos posteriores encontraron resultados más débiles fuera de muestra en otros factores. Solo cubre acciones de EE. UU. y bonos aproximados por duración.

Según el registro, un resultado respaldado no modifica `fondo-v2`: habilita una versión nueva, `fondo-v3`, con su propio registro e historial.
