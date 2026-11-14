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

## Dónde verlo

Panel **Fondo simulado · fondo-v2** al inicio de la vista Cartera, leído de `dist/data/fund.json`. Muestra posiciones, pesos objetivo, desviación, órdenes en acciones enteras y la comparación con 60/40, SPY y letras. La sección **Ajustar mi mezcla** calcula en el navegador una variante personal (acciones, parte de EE. UU., efectivo y capital) sobre los mismos ETF y precios; se guarda solo en ese navegador y no cambia el fondo publicado. Estado y revisiones: `data/fund/fondo-v2/`.

## Resultados de aceptación (14-nov-2026)

Pruebas fijadas en [`c653fbb`](https://github.com/Hardnyx/Trading/commit/c653fbb1) antes de ejecutarlas. Reproducción: `python scripts/fund_v2_acceptance.py` y `node scripts/fund_v2_replay.mjs`. Detalle: [aceptación](auditorias/fondo-v2-aceptacion.json) y [ensayo](auditorias/fondo-v2-ensayo.json).

**T3 · Historia larga de EE. UU., 1900–2018** (S&P 500 con dividendos, Treasury a 10 años, efectivo sin rendimiento; precios promedio mensuales, que suavizan algo las caídas):

| Mezcla | Retorno anual | Volatilidad | Peor año | Caída máxima | Meses hasta recuperar | 12 meses: mediana / peor 5 % | 12 meses en pérdida |
|---|---:|---:|---:|---:|---:|---:|---:|
| **70/25/5 (fondo)** | **8,3 %** | **10,5 %** | **−30,2 % (1931)** | **−67,1 % (1929–1932)** | **85** | **+10,3 % / −13,2 %** | **24 %** |
| 60/40 | 8,1 % | 9,2 % | −26,1 % (1931) | −61,0 % | 82 | +9,4 % / −10,6 % | 22 % |
| 100/0 | 9,6 % | 14,7 % | −41,7 % (1931) | −81,7 % | 183 | +12,5 % / −21,3 % | 27 % |

Desde 1946 (descriptivo), la peor caída del fondo fue **−33,6 % (oct-2007 a mar-2009)**, recuperada en 39 meses; 60/40 cayó −26,7 % y 100/0, −49,0 %. La mezcla rebalanceó en promedio 0,5 veces por año.

**T4 · Era de ETF, feb-2011 a nov-2026** (VTI, VXUS y AGG reales, costos de 7 pb): retorno anual 8,3 % frente a 8,1 % de la misma mezcla rebalanceada cada mes; error de seguimiento 0,45 % anual (límite 1,5 %); 10 rebalanceos en 15,8 años (0,6 por año; límite 6); costos inferiores a 0,01 % anual (límite 0,10 %). Caída máxima −25,0 % (feb–mar 2020), recuperada en 110 sesiones. **Cumple los tres criterios.**

**T5 · Ensayo operativo, 5-oct a 13-nov-2026:** 30 cortes sin operaciones (desviación máxima 1,4 pp), resultado idéntico al repetir, y órdenes en acciones enteras sin efectivo negativo. **Cumple los tres criterios.**

**Regla de excepción calibrada por T3:** una caída mayor que −67,1 % desde el máximo activa un aviso de revisión, sin ventas discrecionales.

**Límites.** T3 usa solo acciones de EE. UU.; el fondo tiene 40 % de sus acciones fuera de EE. UU., cuya historia larga no está en el archivo. Son retornos nominales, sin impuestos. Un historial pasado describe riesgos posibles; no garantiza retornos.

## Sombra `fondo-v3`

Desde el 14-nov-2026 la web muestra bajo el fondo una sombra registrada en [fondo-v3-registro.json](fondo-v3-registro.json): el mismo fondo con la proporción de acciones ajustada por volatilidad según la [prueba respaldada](registro-momento-riesgo.md). Se revisa a diario con los mismos precios y costos, pero nadie opera con ella. Solo puede reemplazar a `fondo-v2` con un registro nuevo tras al menos 12 objetivos mensuales, comparando su Sharpe y su caída en vivo. Estado y revisiones: `data/fund/fondo-v3/`.
