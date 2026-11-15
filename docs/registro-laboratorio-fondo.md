# Laboratorio del fondo: horizonte largo, duración e historia internacional

**Registro:** [estudio-laboratorio-fondo-v1.json](estudio-laboratorio-fondo-v1.json), publicado en [`f3bcca3`](https://github.com/Hardnyx/Trading/commit/f3bcca33) antes de calcular. Ejecución: `python scripts/fund_laboratory.py`. Resultados: [auditorias/laboratorio-fondo-v1.json](auditorias/laboratorio-fondo-v1.json). Ninguna prueba cambia `fondo-v2` ni la sombra `fondo-v3`.

## L1 · Ancla de acciones a 5 y 10 años (S&P 500, 1900–2018)

| Horizonte | R² fuera de muestra frente a la media histórica | Submuestras sin solapamiento con R² > 0 | Veredicto |
|---|---:|---:|---|
| 5 años | −3,1 % | 2 de 5 | **No respaldada** |
| 10 años | **+37,2 %** | 9 de 10 | **Respaldada** |

Con el P/E ajustado por ciclo (CAPE), descriptivo: +5,1 % a 5 años y +39,6 % a 10 años (10 de 10 submuestras).

**Lectura.** El rendimiento de beneficios no sirve para decidir a uno ni a cinco años, pero sí orienta el retorno esperado a diez. Las ventanas de 10 años se solapan: hay unas 11 observaciones independientes por submuestra, y el R² de horizontes largos tiende a exagerarse. Sirve para expectativas de largo plazo del mandato, no para mover la cartera mes a mes.

## L2 · Duración de bonos según el diferencial de plazos (1937–2018)

El diferencial entre el Treasury a 10 años y la letra a 3 meses pronostica el exceso de retorno del bono a 10 años sobre la letra en los 12 meses siguientes: **R² +14,6 %, Clark-West p = 0,0005**, con 82 orígenes de enero sin solapamiento. **Respaldada.**

**Lectura.** Con la curva empinada, los bonos largos han compensado más por su riesgo que la liquidez; con la curva plana o invertida, menos. Habilita a registrar una versión futura que elija entre bonos de plazo intermedio y cortos según ese diferencial.

## L3 · Historia con la parte internacional (1990–2018, descriptivo)

Datos de French para mercados desarrollados fuera de EE. UU. y emergentes, archivados desde [`4b8050c`](https://github.com/Hardnyx/Trading/commit/4b8050ca). La parte internacional se arma con 75 % desarrollados y 25 % emergentes; los bonos son el Treasury a 10 años y el efectivo no rinde.

| 1990-08 a 2018-12 (mensual) | Mezcla de `fondo-v2` | Misma mezcla solo EE. UU. |
|---|---:|---:|
| Retorno anual | 7,7 % | 8,6 % |
| Volatilidad | 10,1 % | 10,2 % |
| Peor año | −25,6 % (2008) | −23,0 % (2008) |
| Caída máxima | −37,5 % (oct-2007 a feb-2009) | −35,2 % |
| Meses hasta recuperar | 39 | 38 |
| Caída 2000–2002 | −27,5 % | −28,3 % |

Extendido hasta sep-2026: 8,3 % anual frente a 9,3 %, con las mismas caídas máximas.

**Lectura.** En este periodo la parte internacional restó retorno, porque EE. UU. fue excepcional desde 1990, y no redujo la caída de 2008: la empeoró 2,3 puntos, por debajo del umbral registrado de 5 puntos. Amortiguó levemente 2000–2002. Es un solo periodo y no demuestra que la diversificación internacional sobre o falte en el futuro; confirma que una crisis financiera puede costar alrededor de −38 % con datos mensuales y −42 % con los ETF diarios.

## Prueba de entrada · Duración según la curva (1937–2018)

Registro: [estudio-duracion-curva-v1.json](estudio-duracion-curva-v1.json), publicado en [`87b3e0a`](https://github.com/Hardnyx/Trading/commit/87b3e0a3) antes de calcular. Ejecución: `python scripts/duration_curve_gate.py`. Resultado: [auditorias/duracion-curva-1937-2018.json](auditorias/duracion-curva-1937-2018.json).

Regla: mantener el bono a 10 años si su rendimiento supera al de la letra a 3 meses; si no, letras. La curva estuvo plana o invertida en 67 de 984 meses.

| Parte de bonos | Siempre bono a 10 años | Con la regla |
|---|---:|---:|
| Retorno anual | 4,99 % | 5,34 % |
| Sharpe sobre letras | 0,25 | 0,34 |
| Caída máxima | −16,0 % | −12,3 % |

Diferencia +0,31 puntos por año, bootstrap p = 0,12: **inconclusa**. Mejora en ambos subperiodos, pero sobre la mezcla 70/25/5 el efecto es de +0,09 puntos por año, con la misma caída máxima. **No habilita una versión nueva del fondo:** el efecto es pequeño, poco frecuente y no supera el umbral registrado.
