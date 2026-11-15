# Materialidad y potencia de la familia de tres pruebas (H0.3, v3)

**Fecha:** 15-nov-2026 UTC. **Ejecución:** `python scripts/confirmatory_v3_power.py`. **Resultado:** [auditorias/potencia-v3-familia-21.json](auditorias/potencia-v3-familia-21.json). Cálculo analítico sin datos de Trading: los umbrales vienen de convenciones externas y las dispersiones de la teoría de muestreo o de rangos declarados.

## Umbrales materiales con fuente externa

| Prueba | Umbral | Fuente |
|---|---|---|
| `ranking_ic:21` | +0,02 o +0,03 puntos de IC de Spearman sobre BPA/precio | Grinold y Kahn: IC de 0,05 es bueno y 0,10 muy bueno; incrementos de 0,02–0,03 son materiales con amplitud de 100–160 acciones |
| `net_economic_value:21` | +1 % o +2 % anual neto de costos | El rango de comisiones de gestión activa que un inversor tendría que superar |
| `return_mse:21` | R² fuera de muestra mensual ≈ 0,5 % | Campbell y Thompson (2008). Sus meses no se calculan: la dispersión de las diferencias de error cuadrático no tiene un valor previo sin datos |

## Meses necesarios (80 % de potencia, primer escalón de Holm α/3, varianza conocida)

Son **cotas inferiores optimistas**: un KVB calibrado necesita más.

| Prueba y umbral | Supuestos de dispersión | Meses sin autocorrelación | Con AR(1) 0,3 |
|---|---|---:|---:|
| IC +0,03 | 160 acciones, ICs correlacionados 0,5 | 62 | 114 |
| IC +0,03 | 100–160 acciones, otros supuestos | 87–223 | 160–413 |
| IC +0,02 | 100–160 acciones | 139–501 | 257–929 |
| Valor neto +2 %/año | tracking error 2 % | 106 | 196 |
| Valor neto +2 %/año | tracking error 4–6 % | 424–953 | 786–1.769 |
| Valor neto +1 %/año | tracking error 2–6 % | 424–3.810 | 786–7.075 |

## Conclusión para el diseño v3

- **Confirmar estadísticamente que el motor aporta valor económico neto no es factible en un plazo práctico:** incluso +2 % anual con un tracking error bajo pide 9 años en el caso más optimista, y lo habitual son décadas. Es la dificultad conocida de distinguir habilidad de suerte en gestión activa.
- **Lo único confirmable en menos de diez años es una mejora de ranking grande (IC +0,03)** con un universo amplio, y aun así en el escenario favorable.
- **Propuesta para el registro v3:** `ranking_ic:21` como afirmación confirmatoria primaria con umbral +0,03 y KVB; `net_economic_value:21` como **vigilancia de daño** (prueba unilateral de que el motor no pierde frente a su referencia) en lugar de prueba de ventaja; `return_mse:21` descriptiva. Fijar meses, umbrales y reglas antes de abrir la cohorte.

Este documento no cambia v2, no abre cohortes y no habilita inferencia.
