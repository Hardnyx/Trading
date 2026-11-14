# Fondo simulado · política `fondo-v2`

**Registro:** 14-nov-2026 UTC, antes de implementar y de ejecutar sus pruebas. Contrato: [fondo-v2-registro.json](fondo-v2-registro.json). Reemplaza a [`fondo-v1`](fondo-simulado-v1.md), que queda archivado con su historial.

## Principio

El dinero solo se mueve por el mandato o por componentes con una prueba registrada y veredicto **respaldada**. Todo lo demás queda en una opción diversificada de mercado. `fondo-v1` tomaba apuestas regionales basadas en el ancla de valoración de acciones, que [no superó a la media histórica](registro-anclas-valoracion.md); por eso se reemplaza.

## Cartera objetivo

| ETF | Peso | Papel |
|---|---:|---|
| VTI | 42 % | Mercado total de acciones de EE. UU. |
| VXUS | 28 % | Acciones fuera de EE. UU. |
| AGG | 25 % | Mercado agregado de bonos de EE. UU. |
| Efectivo | 5 % | Liquidez |

70 % en acciones, dentro del mandato de 60–90 %; dentro de las acciones, 60 % en EE. UU. y 40 % fuera, la convención de los fondos indexados de ciclo de vida.

## Reglas

- **Rebalanceo por desviación:** solo se opera si algún componente se aparta más de 5 puntos de su peso objetivo, y en ese caso se vuelve a los pesos objetivo. Se revisa tras cada actualización de mercado.
- **Apuestas del motor apagadas:** valoración, duración de bonos, momento de riesgo y selección de acciones. Cada una solo entra como versión nueva tras una prueba registrada respaldada.
- **Excepciones:** con precios faltantes o de más de tres sesiones, no se opera ese día. Ante una caída mayor que la peor histórica, no se vende por discreción: la regla sigue y el panel marca una revisión.
- **Ajustes personales:** la web ofrece sliders para calcular una variante propia; el fondo publicado siempre sigue los pesos registrados.

## Pruebas de aceptación, fijadas antes de ejecutarlas

1. **Historia larga (1900–2018):** peor año, caída máxima, meses hasta recuperar, retornos típicos y volatilidad de 70/25/5 frente a 60/40 y 100 % acciones. Es descriptiva: los rangos se aceptan antes de empezar.
2. **Era de ETF (desde feb-2011):** con VTI, VXUS y AGG reales y costos, error de seguimiento frente a la misma mezcla rebalanceada cada mes ≤ 1,5 % anual, operaciones ≤ 6 por año y costos ≤ 0,10 % anual.
3. **Ensayo operativo:** en los últimos 30 cortes, ninguna orden sin desviación mayor a 5 puntos, el mismo resultado al repetir y órdenes en acciones enteras sin efectivo negativo.
