# Conciliación de identidades históricas entre CUSIP e ISIN

**Hito:** H1.2, primer corte de investigación 31-dic-2024. **Criterio técnico:** proteger la unicidad de identidades y el peso original del fondo cuando se reciban exportaciones privadas de proveedor para las dos rutas de solicitud.

El módulo `scripts/historical_identity_cross_namespace_gate.py` combina únicamente los resultados ya verificados de [identidades por CUSIP](importacion-identidad-historica.md) e [identidades por ISIN extranjero](solicitudes-isin-extranjero.md). La **posición original de SPY** sigue siendo la unidad contable, no el identificador del proveedor, el ticker ni la consulta comercial.

## Contratos y verificación

Se reconstruye el archivo SEC original, se vuelven a calcular los hashes de solicitudes de las dos rutas y se exige que los 504 registros positivos aparezcan exactamente una vez. El auditor coteja que las posiciones con CUSIP inválido estén cubiertas por los ISIN extranjeros de la misma declaración (o figuren como excepción explícita) y nunca sean recuperadas ficticiamente por el importador CUSIP.

Si un proveedor devuelve el mismo par `(id_namespace, provider_instrument_id)` para dos identificadores originales diferentes, la identidad queda **en cuarentena** en la conciliación global. No se suman dos veces pesos, se elige la coincidencia por nombre ni se convierte el ISIN en CUSIP. La colisión requiere evaluación documentada incluso si representa un cambio legítimo de identificador o una doble representación de un mismo instrumento.

Se conserva la moneda de negociación original y se exige fecha efectiva histórica, pero estas condiciones por sí solas no prueban la negociabilidad ni los precios ex ante. Las propuestas coincidentes permanecen **candidatos retrospectivos**.

## Ejecutar la auditoría

Generar el resumen público sin datos del proveedor:

```bash
python scripts/historical_identity_cross_namespace_gate.py \
  --template out/historical-cross-namespace-identity-template-v1.json
```

Con ambos extractos locales, previamente preparados bajo los formatos de sus respectivos importadores:

```bash
python scripts/historical_identity_cross_namespace_gate.py \
  --cusip-evidence-dir input/historical-vendor-identity-v1 \
  --isin-evidence-dir input/historical-foreign-isin-vendor-v1 \
  --private-report out/historical-cross-namespace-identity-private-v1.json
```

El reporte privado contiene trazabilidad de posiciones y claves de proveedor para investigar colisiones. Ambas rutas son obligatorias para una conciliación conjunta; pasar solo una se rechaza. Los directorios `input/` y `out/` están ignorados por Git. El workflow CI ejecuta **solo el modo sin exportaciones privadas** y publica el resumen sin IDs de proveedor.

**Pendiente para H1.2:** recibir fuentes históricas originales, resolver efectividad temporal, identificadores, clases de acción, moneda/FX, cierres de negociación, dividendos, splits, delistings y naturaleza exacta de las 26 posiciones extranjeras. Incluso la ausencia de colisiones no certifica el universo integral ni la capacidad predictiva.
