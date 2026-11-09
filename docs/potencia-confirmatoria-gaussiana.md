# Viabilidad de potencia con siete hipótesis y dependencia serial

**Hito:** H0.3. **Fecha:** 9-nov-2026 UTC. **Alcance:** cálculo analítico de sensibilidad para un contraste hipotético, no un estimador de potencia real.

El registro v2 exige 96 meses completos maduros, conserva siete hipótesis primarias y Holm unilateral con error familiar de 5 %, pero aún no especifica ventajas económicamente relevantes ni un procedimiento con calibración confirmatoria defendible. Esta auditoría cuantifica una limitación previa a la disponibilidad de datos: ¿qué efecto estandarizado podría detectarse con un contraste normal idealizado?

## Modelo analítico

Se presupone **una única serie mensual de diferencias con distribución gaussiana AR(1) estacionaria**, desviación típica incondicional conocida y autocorrelación \(\phi\) conocida y no negativa. El objetivo hipotético es una media positiva constante de \(\delta\) desviaciones típicas mensuales. No se deducen estos supuestos de los resultados de Trading.

Para \(n\) meses, la varianza de la suma en unidades de varianza marginal es:

\[
V_n(\phi)=n+2\sum_{k=1}^{n-1}(n-k)\phi^k.
\]

El primer escalón de Holm usa \(\alpha/7=0,007142857\). Con normalidad y parámetros conocidos, su potencia marginal frente a \(\delta>0\) es:

\[
\operatorname{Power}(n,\phi,\delta)=1-\Phi\left(z_{1-\alpha/7}-\frac{n\delta}{\sqrt{V_n(\phi)}}\right).
\]

Una hipótesis con valor p por debajo del primer escalón es necesariamente rechazada por Holm, aunque las otras seis sean arbitrariamente dependientes. Por tanto, **esta probabilidad es una cota inferior de potencia de rechazo individual de Holm si los valores p fueran válidos**, no la potencia conjunta de la familia ni la del bootstrap v2. La media mínima para 80 % de esa potencia se calcula invirtiendo la fórmula, sin búsqueda de parámetros sobre resultados observados.

## Magnitud hipotética para lograr 80 % de potencia

Valores expresados exclusivamente en **desviaciones típicas mensuales de la serie de mejoras**, no puntos básicos de retorno, correlación IC ni rentabilidad de cartera.

| Autocorrelación \(\phi\) | 96 meses | 192 meses |
|---|---:|---:|
| 0,00 | 0,336 SD | 0,238 SD |
| 0,30 | 0,456 SD | 0,323 SD |
| 0,60 | 0,665 SD | 0,473 SD |
| 0,85 | 1,142 SD | 0,821 SD |

Con \(\phi=0,60\), una ventaja hipotética de **0,25 SD mensuales** tiene solo **11,3 % de potencia** al primer escalón de Holm con 96 meses y **23,9 %** con 192. Para llegar a 80 % con una ventaja de **0,10 SD**, serían necesarios **4.333 meses** bajo ese mismo supuesto (aproximadamente 361 años de observaciones mensuales); con independencia temporal serían 1.084 meses. Son requerimientos matemáticos del escenario idealizado, no horizontes realistas ni propuestas para la investigación.

El informe contiene 12 combinaciones de longitud/autocorrelación (96/192/360; 0/0,30/0,60/0,85), tres efectos estandarizados hipotéticos (0,10/0,25/0,50), tamaño efectivo idealizado y la inversión exacta de potencia hasta un techo ilustrativo de 50.000 meses. Los casos que no alcancen ese techo se representan mediante un valor nulo en JSON.

## Reproducibilidad

Ejecutar desde la raíz del repositorio:

    python -m unittest tests.test_confirmatory_power_feasibility
    python scripts/confirmatory_power_feasibility.py --verify --output out/confirmatory-power-feasibility-v1.json

Se comprueban la varianza de suma por fórmula cerrada frente a la suma explícita, el tamaño bajo efecto nulo, la inversión algebraica del 80 % de potencia, la minimalidad del tamaño muestral y la inmutabilidad del contrato v2. CI conserva el informe bajo el nombre de artefacto confirmatory-power-feasibility.

## Decisiones que no se han tomado

**No** se fijan como efectos mínimos económicos 0,10, 0,25 o 0,50 SD. Los tres objetivos de Trading se expresan en unidades distintas, requieren umbrales justificados mediante pérdidas esperadas, costes, riesgo y utilidad económica, y no deben identificarse a partir de este análisis hipotético. Tampoco se elige una autocorrelación por cuál produzca una potencia conveniente.

Este estudio **no corrige** el exceso de falsos rechazos detectado en el bootstrap registrado, **no estima** la potencia de ese bootstrap y **no habilita** v2. El modelo gaussiano con parámetros conocidos no representa los cambios de régimen, colas pesadas, dependencia entre horizontes ni ausencias de series reales. La siguiente decisión de diseño requiere un método inferencial calibrado y efectos mínimos económicamente defendibles, registrados antes de examinar evidencia confirmatoria independiente.
