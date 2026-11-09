# Adquisición local de presentaciones originales SEC

**Hito:** H1.2. **Fecha:** 9-nov-2026 UTC. **Alcance:** obtención y auditoría local de bytes, sin afirmar que se han descargado en CI.

El script [sec_original_acquisition.py](../scripts/sec_original_acquisition.py) usa exclusivamente las URL incluidas en la [lista de fuentes originales previamente revisadas](../data/historical/sec-first-cut-original-source-leads-v1.json). La primera es el [10-Q de Microsoft, accession 0000950170-24-118967](https://www.sec.gov/Archives/edgar/data/789019/000095017024118967/0000950170-24-118967-index.html), presentado el 30-oct-2024 a las 16:07:17 hora de Nueva York. La documentación oficial de [acceso a EDGAR](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) especifica el archivo completo de presentación en su carpeta por accession.

## Uso en Windows CMD, sin privilegios de administrador

Se necesita un agente de usuario identificable para respetar la política de acceso de la SEC. Debe contener el nombre del solicitante y **un correo de contacto real**, pero no se guarda ese texto en el repositorio ni se imprime en el recibo. En `cmd.exe`, desde la raíz de Trading:

```bat
set "SEC_USER_AGENT=TradingResearch Contacto@dominio.com"
python scripts/sec_original_acquisition.py --accession 0000950170-24-118967
```

El contacto anterior es un marcador de posición que debe sustituirse por uno real. No ejecutar el comando literalmente con un correo ficticio.

Los archivos se guardan de forma predeterminada en `out/sec-originals/`, una ruta ignorada por Git. El original esperado es `0000950170-24-118967.txt`, junto con `0000950170-24-118967.receipt.json`. La descarga no reintenta ni sobrescribe un original existente. Si SEC devuelve un rechazo, redirección inesperada, tamaño distinto del índice o encabezado discordante, el proceso falla sin promover la fuente.

## Qué valida el recibo

- URL HTTPS exacta del accession oficial previamente registrado; nunca URL arbitraria.
- Respuesta HTTP 200 sin cambio de origen y límite de tamaño.
- Integridad local SHA-256, número de bytes e instante de recuperación; cotejo contra la longitud indicada en el índice SEC.
- `SEC-HEADER` original con CIK, formulario, fecha de presentación, accession y hora de aceptación coherentes con la ficha registrada.
- Campos explícitos `first_publication_independently_verified=false`, `numeric_xbrl_facts_reconciled=false`, `eligible_full_engine_cuts_added=0` y `predictive_validation=not-established`.

**Límite:** el encabezado de la presentación recuperada hoy puede corroborar qué declara EDGAR, pero no demuestra mediante evidencia independiente que ese mismo archivo, o la extracción FSD trimestral, estuviera disponible al corte de investigación. Aún falta cotejar hechos iXBRL originales por periodo y dimensión, reconciliar enmiendas, construir TTM y verificar el enlace histórico CIK–valor negociable. El primer corte integral permanece no admisible.

CI prueba el cliente HTTP mediante respuestas sintéticas, no descarga el documento SEC ni emplea contactos privados. La operación real requiere acceso de red y un contacto proporcionado por quien ejecuta el comando.
