# Fondo simulado · política `fondo-v1`

**Adoptada:** 14-nov-2026. **Código:** [`fund-policy.mjs`](../dist/assets/js/fund-policy.mjs), [`fund_review.mjs`](../scripts/fund_review.mjs). **Estado:** simulación de investigación; la capacidad predictiva no está acreditada.

## Qué es

Un fondo de USD 100.000 que invierte solo en ETF cotizados en EE. UU. Cada revisión parte de **sus propias posiciones**, no de efectivo, y solo cambia de cartera cuando la mejora queda demostrada dentro del modelo. La política está fija en código: un cambio del motor no mueve el fondo salvo que pase la misma regla de decisión, y cambiar la política exige un identificador nuevo y su propio historial.

## Parámetros

| Parámetro | Valor | Motivo |
|---|---|---|
| Universo de compra | ETF que cotizan en EE. UU., incluidos los de exposición internacional | Primera versión sin selección de acciones individuales, que aún no está validada |
| Renta variable total | 60 %–90 % | Mandato de crecimiento habitual en un fondo mixto agresivo |
| Efectivo mínimo | 5 % | Mandato de referencia |
| CVaR 95 % a un año | ≤ 30 % | Consistente con 60–90 % en renta variable; el 20 % de la referencia impide cualquier cartera de ese rango |
| Concentración sectorial | ≤ 50 % (cota conservadora) | Con 35 %, la cota para holdings sin clasificar hacía inviable toda cartera con 60 % en acciones |
| Resto de límites | Los de la referencia: 35 % por instrumento, correlación ≤ 0,95, 8 posiciones | Sin cambios |
| Modelos que deciden | Base, sin re-rating, estrés de margen y combinado | La cartera debe mejorar a mantener en todos |
| Modelo solo de riesgo | Baja convicción (prima de acciones e IC cero) | Debe cumplir los límites de riesgo, pero no elige la cartera |
| Umbral de cambio | Cota inferior Monte Carlo de la mejora ≥ max(USD 250, 3 × costo) en cada modelo que decide | Separa mejoras reales del ruido de simulación |
| Histéresis | Volver a una cartera abandonada en las últimas 20 sesiones exige el doble del umbral | Evita el ida y vuelta entre candidatas casi empatadas |
| Revisión | Tras cada actualización diaria de mercado | Permite aprovechar oportunidades sin rotar por ruido |
| Dividendos | Reinvertidos en el mismo ETF (precio ajustado) | Comparación coherente con referencias de retorno total |

## Cómo seguirlo en un simulador

Cada revisión deja en `data/fund/reviews/<fecha>.json` el estado (`hold` o `rebalance`), las ganancias confirmadas por modelo y, si hay cambio, las órdenes con acciones fraccionarias y enteras (`target_whole_shares`, `trade_whole_shares`). Para un simulador sin fracciones, usar las acciones enteras y dejar el resto en efectivo. `data/fund/state.json` guarda las posiciones simuladas del fondo.

## Referencias de comparación

La referencia principal es una cartera pasiva 60/40 (SPY/AGG) rebalanceada mensualmente, medida por ratio de Sharpe y caída máxima netos de costos. Se informan también SPY y letras del Tesoro (BIL).

## Límites

Los retornos esperados de índices, bonos y acciones subyacentes no están validados fuera de muestra; la prueba de riesgo 2008–2019 fue inconclusa. La política reduce cambios por ruido y por código, pero no demuestra que las decisiones superen a sus referencias. Eso solo lo dirá el historial del fondo y la validación de retornos.
