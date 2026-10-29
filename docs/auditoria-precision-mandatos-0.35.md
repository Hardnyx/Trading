# Precisión numérica por mandato · 29-oct-2026

Se amplía el ensayo antitético a dos cortes y tres objetivos, con una nueva
pareja de semillas fijada antes de ejecutar el contraste. Se evalúa ruido de
integración numérica dentro del modelo; no se modifica la selección ordinaria.

## Protocolo fijado

- Datos completos publicados con cierres 27 y 28-oct, y los ajustes de
  volatilidad que corresponden a cada captura. No se aplican ajustes actuales
  a precios anteriores. Los commits y hashes están en el resultado.
- Mismas 19 cestas ex post de la investigación anterior, sin nueva búsqueda.
  No hay exclusiones en ninguno de los dos cortes.
- Crecimiento logarítmico, preservación con aversión 5 y capital objetivo
  USD 105.000. Capital inicial USD 100.000, horizonte anual, USD sin retiros,
  mismo efectivo, dividendos, divisa y costes. Solo cambia la utilidad/meta.
- Semillas nuevas: `0x6ca317d5` y `0x37bd921f`. La segunda proporciona el
  brazo independiente del método ordinario; el antitético comparte el primer
  brazo y usa su espejo. No son dos réplicas independientes del experimento.
- Presupuestos fijados de 1.000 y 4.000 parejas: 2.000 y 8.000 trayectorias
  por modelo y método. El presupuesto pequeño es un prefijo del grande;
  no se detiene la simulación al encontrar un resultado favorable.
- Familia simultánea aproximada: 24 casos (dos cortes, tres objetivos,
  dos presupuestos y dos métodos), además de todas las parejas de candidatas
  y modelos. Para 19 cestas y cinco modelos son 216.600 contrastes.
- Se usa la media de utilidad de cada pareja como observación independiente.
  Los controles de riesgo no se evalúan sobre esas medias.

Reutilizar precios entre objetivos evita recalcular el mismo proceso: sus
horizontes y reglas de caja, dividendos y divisa son idénticos. Una prueba
contrasta esta reutilización con generar y evaluar cada mandato por separado.
No se reconstruye el universo que elegiría el optimizador de cada mandato:
se compara la precisión de la evaluación sobre el mismo conjunto fijo.

## Menor cota superior de oportunidad en cada conjunto

Todas las cifras son USD por USD 100.000 de capital. Son cotas aproximadas
con conversión monetaria estimada, sin toda la incertidumbre de parámetros.

| Cierre | Objetivo | Ordinario, 2.000 | Antitético, 2.000 | Ordinario, 8.000 | Antitético, 8.000 |
|---|---|---:|---:|---:|---:|
| 27-oct | Crecimiento | 1.147,08 | 468,69 | 317,35 | 117,41 |
| 28-oct | Crecimiento | 1.137,60 | 472,50 | 311,94 | 117,28 |
| 27-oct | Preservación | 108,32 | 52,67 | 29,55 | 9,56 |
| 28-oct | Preservación | 113,99 | 60,90 | 35,47 | 17,57 |
| 27-oct | Capital objetivo | 0 | 0 | 0 | 0 |
| 28-oct | Capital objetivo | 0 | 0 | 0 | 0 |

El antitético mejora esta cota frente al ordinario a igual presupuesto en
crecimiento y preservación. En capital objetivo ambos ya resuelven la
comparación relativa. Aumentar presupuesto también ayuda en los dos primeros.
La comparación es por evaluaciones de utilidad, no una promesa de igual CPU
ni una medida de ventaja económica. Los tiempos de las ejecuciones locales
concurrentes se conservan como metadatos, sin usarlos como benchmark.

## Interpretación por objetivo

**Crecimiento:** ninguna cesta acota la oportunidad dentro del umbral USD 100
ni siquiera con 8.000 trayectorias. A ese presupuesto los dos cortes dan el
mismo líder puntual: SHY 35%, IGSB 35%, SHV 25%, CASH 5%. La coincidencia
no permite certificar sus pesos ni borrar la incertidumbre restante.

**Preservación:** el método antitético ya permite dos cestas dentro del
umbral con 2.000 trayectorias; con 8.000 el método ordinario también lo logra.
El líder puntual coincide con el anterior. Esto identifica decisiones con
pequeña oportunidad relativa en este conjunto y estos supuestos, no la
cartera óptima global ni su seguridad frente al mercado real.

**Capital objetivo:** el líder es SGOV 35%, IGSB 35%, SHV 25%, CASH 5%.
La cota de oportunidad cero incluye explícitamente todas las alternativas;
no procede solo de compararse consigo mismo. Aun así es una conclusión
condicional aproximada, no riesgo cero ni certeza de alcanzar USD 105.000.
El equivalente del peor modelo ronda USD 103.500, por debajo de la meta:
el criterio minimiza déficit cuadrático y puede preferir menos dispersión
frente a una alternativa con mayor retorno medio. La cota monetaria solo
expresa diferencia de utilidad frente al conjunto finito.

## Decisión y límites

Se mantienen el estimador y la política ordinarios en producción. La nueva
semilla y el segundo corte refuerzan la evidencia numérica de reducción de
ruido, pero los cortes son contiguos y no cubren ciclos de mercado. En el
mandato principal de crecimiento todavía no se cumple la precisión fijada.
No se relaja el umbral ni se cambian semillas o supuestos para lograrlo.

El conjunto es pequeño, elegido después de observar propuestas, y no prueba
cobertura del espacio de búsqueda ni óptimo sujeto a todas las restricciones.
No se certifica aquí riesgo admisible de cada cesta. Faltan retiros, suelos,
moneda distinta de USD, otros regímenes y memoria/tiempo bajo carga aislada.
La incertidumbre de anclas, dependencia y parámetros, y la ventaja financiera
fuera de muestra siguen abiertas aunque una comparación numérica se resuelva.

## Reproducción

```sh
node --test tests/antithetic-matrix.test.mjs
node scripts/antithetic_matrix_research.mjs --output out/matrix-cut28.json
```

Para repetir los cortes fechados con la revisión del código que contiene
esta auditoría, extraer los ficheros completos y pasar sus rutas:

```sh
mkdir -p out
git show d6e54473a52d24985ff274738d44826db4c78b7a:dist/data/market.json > out/matrix-market27.json
git show d6e54473a52d24985ff274738d44826db4c78b7a:dist/data/volatility.json > out/matrix-vol27.json
node scripts/antithetic_matrix_research.mjs --market out/matrix-market27.json --volatility out/matrix-vol27.json --output out/matrix-cut27.json
git show 5667d4830001bbded19a461d6972b1cd9339309d:dist/data/market.json > out/matrix-market28.json
git show 5667d4830001bbded19a461d6972b1cd9339309d:dist/data/volatility.json > out/matrix-vol28.json
node scripts/antithetic_matrix_research.mjs --market out/matrix-market28.json --volatility out/matrix-vol28.json --output out/matrix-cut28.json
```

Los [resultados completos](auditorias/antithetic-matrix-2026-10-29.json)
conservan cada candidata, política, cota y hashes de código/datos. CI ejecuta
una matriz acotada (`--quick`, 100 y 200 parejas, corte vigente) para detectar
regresiones de integración. Esa prueba no sustituye el contraste completo de
este documento ni autoriza promociones automáticas.
