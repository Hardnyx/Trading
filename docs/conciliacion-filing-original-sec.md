# Conciliación de presentaciones originales SEC con extractos FSD

**Fecha:** 9-nov-2026 UTC. **Hito:** H1.2, fuentes originales para fundamentales históricos. **Estado:** adaptador técnico, no recepción de fuentes.

Los ZIP trimestrales de [Financial Statement Data Sets de la SEC](https://www.sec.gov/dera/data/financial-statement-data-sets.html) recopilan información XBRL declarada por emisores, pero pueden omitir metadatos relevantes. La [documentación de acceso a EDGAR](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) establece que la presentación original completa se recupera mediante `Archives/edgar/data/{cik}/{accession_sin_guiones}/{accession}.txt`.

## Dos niveles de evidencia documental

1. **Extracto derivado:** `historical_sec_fsd_intake.py` conserva cada accession y filtra la fecha y hora `accepted` contra el instante de información. El ZIP tiene SHA-256 y los datos no se combinan por conveniencia entre enmiendas.
2. **Documento original:** `historical_sec_original_filing.py` exige el `.txt` completo de EDGAR y su bloque `SEC-HEADER`. Concuerda accession, CIK único, formulario, fecha de presentación y hora de aceptación. Calcula SHA-256 del original y, si se suministra nuevamente el ZIP, comprueba también la huella del archivo trimestral contra el informe de extracción.

El conciliador rechaza documentos truncados, sustituciones de encabezados, múltiples CIK principales que requieran revisión manual, enmiendas posteriores al corte, diferencias de metadatos y hashes externos incorrectos. Su aceptación **no certifica primera publicación**: tanto la aceptación mostrada en FSD como el encabezado del archivo descargado hoy se refieren a metadatos históricos. La validación documental de los importes contables y de sus dimensiones sigue siendo otro paso independiente.

## Procedimiento reproducible

Primero preparar las solicitudes, sin descargar automáticamente ni subir documentos al repositorio:

```bash
python scripts/historical_sec_fsd_intake.py --template out/historical-sec-fsd-source-request-v1.json --verify
python scripts/historical_sec_original_filing.py --template out/historical-sec-original-source-request-v1.json --verify
```

Después de obtener el ZIP trimestral oficial y una presentación completa por accession, procesar ambos **localmente**, con CIK y corte de información sustentados:

```bash
python scripts/historical_sec_fsd_intake.py --archive 2024q4.zip --cutoff 2024-12-31T21:00:00Z --cik 0000000123 --output out/sec-fsd-research.json --verify
python scripts/historical_sec_original_filing.py --fsd-report out/sec-fsd-research.json --original 0000000123-24-000001.txt --accession 0000000123-24-000001 --fsd-archive 2024q4.zip --output out/sec-original-header-check.json --verify
```

Los identificadores y nombres de archivo de este ejemplo son **ficticios para ilustrar el formato**, no una presentación disponible ni una cotización original. El `--cutoff` debe ser la hora real de decisión, no necesariamente las 16:00 de Nueva York. El hash externo `--expected-original-sha256` es opcional y solo debe suministrarse si fue obtenido de una fuente independiente.

## Evidencia y bloqueos

Las pruebas construyen una presentación SEC completa sintética; el rechazo de errores confirma el comportamiento del programa, no la disponibilidad de un archivo original real. La CI solo publica la plantilla `historical-sec-original-source-request`, sin documentos ni datos licenciados.

El informe mantiene `original_filing_first_publication_independently_verified=false`, `original_document_numeric_facts_reconciled=false`, `historical_security_identity_certified=false`, `eligible_full_engine_cuts_added=0` y `predictive_validation=not-established`. Para avanzar H1 habrá que descargar y auditar archivos reales, contrastar los hechos XBRL por periodos y dimensiones, reconstruir la identidad del activo y comprobar las operaciones y los flujos históricos sin información futura.

## Primera fuente real localizada para adquisición

Se consultó el [índice original SEC de Microsoft, accession `0000950170-24-118967`](https://www.sec.gov/Archives/edgar/data/789019/000095017024118967/0000950170-24-118967-index.html), correspondiente al 10-Q presentado **30-oct-2024, 16:07:17 hora de Nueva York**, periodo de reporte finalizado 30-sep-2024. El índice referencia el `msft-20240930.htm` iXBRL, el `msft-20240930_htm.xml` XBRL derivado y el archivo completo `0000950170-24-118967.txt`. La [ficha de adquisición](../data/historical/sec-first-cut-original-source-leads-v1.json) conserva estos enlaces, el tamaño que muestra el índice y las banderas explícitas de ausencia de bytes/hashes. Una hora de aceptación anterior al corte de investigación no certifica por sí sola disponibilidad verificable del documento exacto, cifras PIT, identidad del activo ni aptitud de una cuenta histórica. No se importaron datos reales al motor ni se alteró el contador de cortes admitidos.
