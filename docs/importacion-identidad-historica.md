# Incorporación de identificadores históricos del proveedor

**Hito:** H1.2. **Estado:** interfaz de recuperación y conciliación implementada; todavía no se ha incorporado una fuente de precios con identidad histórica acreditada.

El [generador de solicitudes SEC](../scripts/historical_identity_requests.py) recupera el CUSIP, la posición de SPY y la evidencia original de sus fondos de comparación para el 31 de diciembre de 2024. El nuevo adaptador [historical_vendor_identity.py](../scripts/historical_vendor_identity.py) permite confrontarlos con un archivo local de identificadores permanentes y fechas de validez, sin adivinar relaciones a partir del ticker.

## Preparar la solicitud

```bash
python scripts/historical_vendor_identity.py --template out/historical-vendor-identity-template.csv
```

Este CSV contiene las 504 posiciones positivas de SPY y sus identificadores originalmente observados. **Es una solicitud de datos, no un mapa de instrumentos validado.** Puede enviarse a un sistema autorizado de datos históricos para localizar CUSIP, FIGI/ID nativo y cambios de identidad. El CSV no incluye credenciales.

## Datos necesarios para conciliar

Crear un directorio local como `input/historical-vendor-identity-v1/`, **fuera del control de versiones**. Conservar el archivo exportado o extraído autorizado como CSV UTF-8, con estas columnas exactas:

```csv
cusip,provider_instrument_id,id_namespace,security_type,currency,exchange_mic,valid_from,valid_to,record_as_of
```

La fila debe describir el instrumento y su intervalo de identidad efectivo. `valid_to` se interpreta como fecha **exclusiva**. `record_as_of` es la fecha que declara el extracto: no se infiere de la fecha de descarga ni prueba disponibilidad histórica. El proveedor ha de suministrar el ID permanente, por ejemplo FIGI o ID nativo; **un ticker no es un identificador permanente admisible**. Sin ambas fechas de validez no hay candidato de identidad. Se separan las filas sin correspondencia, duplicadas, inconsistentes, fuera de fecha, de moneda distinta, no acción o sin MIC de negociación.

En el mismo directorio incluir `manifest.json`:

```json
{
  "protocol": "historical-vendor-identity-sources-v1",
  "cut": "2024-12-31",
  "request_sha256": "<SHA256 del objeto canonical de cut + requests>",
  "exports": [
    {
      "path": "export.csv",
      "sha256": "<SHA256 real de los bytes de export.csv>",
      "provider": "<proveedor autorizado>",
      "source_reference": "<identificador de consulta/exportación>",
      "snapshot_as_of": "2024-12-31",
      "retrieved_at": "2026-11-08T05:00:00Z",
      "temporal_basis": "retrospective_asof_export"
    }
  ]
}
```

Los valores entre signos angulares son **marcadores que se deben sustituir**, no evidencia. `request_sha256` se obtiene de `request_hash(build_requests())` en `scripts/historical_vendor_identity.py`; la fecha `retrieved_at` debe ser la real. El campo `temporal_basis` admite `retrospective_asof_export` o `contemporaneous_archive`, pero **ninguno confiere certificación causal por sí solo**. Los hashes protegen los archivos contra modificaciones posteriores a la referencia, no autentican la veracidad del proveedor ni prueban disponibilidad pública en 2024.

```bash
python scripts/historical_vendor_identity.py \
  --evidence-dir input/historical-vendor-identity-v1 \
  --report out/historical-vendor-identity-reconciliation-v1.json
```

La conciliación produce cada posición con estado explícito, fuentes con SHA256 y, solo cuando el cruce es inequívoco y la fecha es compatible, un **candidato retrospectivo de identidad**. Nunca marca precios, eventos corporativos, ejecución, disponibilidad histórica ni un corte del motor como certificados.

## Restricciones y siguiente aceptación

- No publicar en el repositorio ni como artefacto de CI archivos del proveedor que tengan licencia privada, IDs derivados de esa fuente o documentación de acceso.
- No utilizar nombres de empresas, símbolos actuales, normalización de puntos o ajustes de moneda para forzar coincidencias.
- Verificar posteriormente la captura original y su semántica histórica, el enlace continuo de CUSIP a instrumento, cambios de acciones/estructura, deslistados y una serie de cierres ejecutables sin ajustes futuros.
- Mantener H1 bloqueado hasta que el auditor integral pueda demostrar **un corte completo** bajo H0, no solo un porcentaje elevado de CUSIP enlazados.
- Los datos retrospectivos se usan en desarrollo; una muestra confirmatoria necesita definición previa independiente.

El workflow de checks genera solo la plantilla pública SEC como artefacto de investigación. Las pruebas usan datos sintéticos: **no aportan observaciones nuevas del mercado ni información privada**.

**Integridad del CUSIP:** el importador comprueba el noveno carácter de control (módulo 10, ANSI X9.6) además del formato del identificador, incluyendo las codificaciones `*`, `@` y `#`. Un CUSIP con dígito de control incorrecto se rechaza antes de intentar cualquier vínculo con un instrumento de mercado. La verificación del dígito no autentica al proveedor ni certifica que ese instrumento fuera negociable en la fecha.

## Transmisión de la moneda al importador de precios

El campo `currency` del extracto CUSIP ahora se conserva explícitamente como `candidate_security_key.quote_currency` en el reporte de identidad. Esta ruta sigue rechazando como candidatos los valores no denominados en USD; el contrato de precios **nunca inventa la moneda** cuando falta el dato. Las monedas extranjeras continúan por el importador ISIN independiente, sin certificar FX ni negociabilidad en dólares.
