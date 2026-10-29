# Incertidumbre de selección · corte 28-oct, auditoría 29-oct-2026

El motor sigue en 0.35.0. Este cambio añade investigación y controles del
diagnóstico; no cambia la ley de precios, la composición ni autoriza operaciones.

## Pregunta y protocolo

La pérdida por desempatar frente al líder estimado es cero al elegir a ese
mismo líder. Esa identidad no mide cuánto podría mejorar otra candidata.
Ahora se compara cada alternativa con **todas** las demás bajo los cinco
modelos declarados, con escenarios comunes dentro de cada experimento.

Para la candidata i, se calcula el máximo sobre j de la diferencia entre
sus utilidades en el peor modelo. Se incluyen todas las parejas de modelos:
la diferencia de dos mínimos no es el mínimo de diferencias emparejadas.
El máximo incorpora la comparación consigo misma, con pérdida cero.
Las cotas usan el procedimiento pareado aproximado del motor, con familia
K² × M² × dos experimentos (18.050 contrastes). La conversión de utilidad a
USD usa una base estimada. No es un intervalo predictivo ni una garantía
exacta de cobertura bajo cualquier distribución.

Se congela un conjunto de 19 exposiciones: las candidatas factibles de la
auditoría anterior y las dos cestas del contraste 27–28-oct. No se vuelve a
optimizar ni se escogen semillas después de mirar el resultado. Se usan
2.000 trayectorias por modelo y semilla, horizonte anual y los cinco modelos
económicos, más Student solo para riesgo. Las semillas son 1218542633 y
1536675889, distintas de cribado, selección y confirmación de producción.
Los datos completos son los publicados por el commit
`72c273b59242fecc665248d34cc0c42eed6c9056`, con precios del 28-oct.

## Resultado

| Experimento | Líder estimado | Equivalente cierto del peor modelo | Cota superior de oportunidad frente al conjunto |
|---|---|---:|---:|
| Semilla 1218542633 | SHY 35%, IGSB 35%, SHV 25%, CASH 5% | USD 104.180,97 | USD 862,30 |
| Semilla 1536675889 | SGOV 35%, IGSB 35%, TIP 25%, CASH 5% | USD 104.179,53 | USD 763,72 |

El cambio entre esos líderes reasigna el 60% del capital. La primera cesta
comparte solo IGSB 35% y CASH 5% con la segunda. El presupuesto de simulación
y las fechas son iguales; cambia la semilla de evaluación del conjunto fijo.

Ninguna de las 19 candidatas tiene una cota superior de oportunidad dentro
del umbral de USD 100 en ninguno de los dos experimentos. La menor cota
entre todas es USD 862,30 en el primero y USD 759,73 en el segundo. Esto
**no demuestra** que su pérdida real sea esa cantidad ni que todas sean
malas inversiones. Impide afirmar esa precisión de selección con este
presupuesto y estas aproximaciones.

Para la cesta sellada SPY 35%, LQD 35%, TIP 25%, CASH 5%, las diferencias
puntuales frente al líder son USD 21,82 y USD 119,99; las cotas superiores
son USD 906,13 y USD 1.004,72, respectivamente. En ambos experimentos la
cota inferior de pérdida es cero. No se acredita una alternativa superior.

Las 19 cestas pasan las comprobaciones individuales de riesgo en esta
muestra, incluido el estrés Student. Esos controles no certifican cobertura
simultánea de todo el conjunto ni capacidad predictiva. El diagnóstico
conserva cualquier candidata con fallos de riesgo y los muestra por separado:
excluir una candidata limítrofe podría esconder incertidumbre de oportunidad.
En otros cortes, el máximo podría incluir alternativas no operables; solo
su cota superior serviría como envolvente conservadora del conjunto factible.

## Qué cambia en la confianza

Se elimina un punto ciego del diagnóstico: el líder ya no recibe una falsa
precisión por compararse únicamente consigo mismo. El control de operar
frente a mantener y la regla de desempate de producción permanecen como
estaban. La propuesta desde efectivo continúa siendo una candidata bajo
convenciones, con pesos poco determinados.

Faltan cobertura del espacio de búsqueda, incertidumbre de parámetros y
supuestos económicos, y ventaja prospectiva neta. Aumentar simulaciones
puede reducir ruido de Monte Carlo; por sí solo no acredita esas otras
fuentes. No se promueve una cartera usando este contraste retrospectivo.

## Reproducción y conservación

```sh
node --test tests/pool-opportunity.test.mjs
node scripts/pool_opportunity_audit.mjs
```

La CLI ejecuta el protocolo sobre los ficheros actuales. Para reproducir el
resultado fechado, primero se extraen los ficheros completos del commit:

```sh
mkdir -p out
git show 72c273b59242fecc665248d34cc0c42eed6c9056:dist/data/market.json > out/pool-market.json
git show 72c273b59242fecc665248d34cc0c42eed6c9056:dist/data/volatility.json > out/pool-volatility.json
node scripts/pool_opportunity_audit.mjs --market out/pool-market.json --volatility out/pool-volatility.json
```

El [resumen fechado](auditorias/pool-opportunity-2026-10-29.json) conserva
cada candidata, sus cotas, fallos de riesgo y el competidor que más amplía
su cota superior. Registra hashes del código, mercado, volatilidad y conjunto
original. La salida completa conserva todas las comparaciones; su hash
está en el resumen. CI ejecuta el mismo protocolo en sombra con cambios de
modelos o datos y tras terminar correctamente «Refresh market data». Conserva la salida completa durante 90 días, sin publicar
señales ni escribir datos de producción.

Las pruebas cubren el líder incierto, pérdidas exactas con modelos en
desacuerdo, invariancia al orden, multiplicidad y rechazo de pares incompletos.
