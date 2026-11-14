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
