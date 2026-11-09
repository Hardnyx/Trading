# Límite temporal mínimo de confirmación prospectiva

**Hito:** H0.3, viabilidad operativa. **Corte:** 9-nov-2026 UTC. **Resultado:** cota inferior de calendario, no predicción ni fecha garantizada.

El protocolo integral v2 fija frecuencia mensual, primer mes posible noviembre de 2026, al menos **96 orígenes mensuales admisibles y maduros** de una misma cohorte y tres horizontes de 21, 63 y 252 sesiones. Los 48 orígenes históricos examinados no pueden incorporarse como confirmación independiente.

## Calendario más optimista

Bajo los supuestos extremadamente favorables de que la cuenta integral emita un pronóstico original admisible en **cada** mes desde noviembre de 2026, nunca falten insumos, nunca cambien las versiones incompatiblemente y todos los sellos sean auditables:

| Restricción | Resultado mínimo |
|---|---|
| Primer origen mensual elegible posible | Noviembre de 2026 |
| Origen número 96 | **Octubre de 2034** |
| Meses de observaciones requeridos, incluyendo ambos extremos | **96** |
| Separación entre el primer y el último origen | **95 meses** |
| Maduración adicional del horizonte más largo | **252 sesiones estadounidenses observadas** después del último origen |

El cierre de octubre de 2034 **no** permite terminar el contraste de 252 sesiones ese mismo día. No se inventa una fecha futura exacta de vencimiento de 252 sesiones porque no se dispone de un calendario bursátil observado para esos años. Incluso una estimación aproximada alrededor de 2035 depende de sesiones efectivas, cierres y maduración, por lo que el cálculo automatizado conserva explícitamente la fecha final como desconocida.

Este es un **límite inferior idealizado**, no un plan garantizado: cada origen no admisible, fuente original ausente, cambio incompatible del motor o pérdida de continuidad puede retrasar la primera oportunidad de cumplir el mínimo. Los 96 meses tampoco garantizan potencia suficiente ni valores p calibrados.

## Implicaciones para el proyecto

El estudio v2 se puede utilizar como **registro de gobierno prospectivo**, pero no es una ruta razonablemente rápida para certificar predictibilidad del motor integral. Para elaborar una ruta más próxima hacen falta fuentes point-in-time originales y un diseño independiente compatible con la dependencia temporal; cualquier sustitución formal de la frecuencia, unidad estadística, ventanas, método, horizontes o comparadores requiere **otro protocolo versionado antes de observar su cohorte**, no reescribir v2 ni contar activos o simulaciones como meses independientes.

No se puede retroceder a 2022 y denominar holdout al historial ya inspeccionado. Un futuro ensayo puede distinguir investigación retrospectiva de confirmación nueva, pero necesita definir de forma defendible la independencia y potencia. Este diagnóstico no selecciona una solución por resultados favorables.

## Reproducción

\`\`\`bash
python -m unittest tests.test_confirmatory_calendar_floor
python scripts/confirmatory_calendar_floor.py --verify --output out/confirmatory-calendar-floor-v1.json
\`\`\`

El programa valida las reglas congeladas y archiva los **96 meses hipotéticos** sin descargar datos de bolsa, inferir feriados futuros ni calcular retornos. CI publica el archivo bajo \`confirmatory-calendar-floor\`.

**Estado:** v2 inactivo; 0/7 efectos materiales justificados; inferencia y utilidad predictiva no acreditadas.
