# Confrontación exploratoria SEC: clase de acción e identidad de MSFT

**Hito:** H1.2. **Corte examinado:** 31-dic-2024. **Estado:** adaptador y pruebas sintéticas; intersección sobre originales pendiente de ejecución.

El archivo 10-Q de Microsoft de 30-oct-2024 declara en la tabla de valores registrados conforme a la sección 12(b) una acción ordinaria negociada como \`MSFT\` en NASDAQ, **pero también dos emisiones de deuda que muestran el mismo símbolo \`MSFT\`**. Por ello no es correcto equiparar un ticker con una identidad única de instrumento, ni usar la aparición de la cadena MSFT en un documento como prueba de que se trata de acciones.

El programa \`scripts/sec_first_cut_equity_bridge.py\` lee exclusivamente el archivo \`.txt\` original SEC asociado al accession \`0000950170-24-118967\`, exige su SHA-256 ya contrastado y el instante exacto del encabezado EDGAR anterior al corte. Extrae únicamente la tabla de clases registradas del documento principal 10-Q (no anexos), mediante el parser XML que conserva los bytes originales. Rechaza tablas ausentes/duplicadas, varias clases ordinarias bajo el mismo símbolo y etiquetas incompatibles. Registra explícitamente las filas de deuda que reutilizan ese símbolo.

La otra mitad de la intersección procede de \`historical_identity_requests.build_requests()\`: reabre el N-PORT original de SPY para el corte, verifica las fuentes de ticker fechadas y reconstruye el CUSIP tal como aparece en la declaración del fondo. Solo se admite exactamente una posición positiva con observación original \`MSFT\`, CUSIP de control válido y recibos anteriores al corte, sin acudir al catálogo de tickers de 2026, nombres de empresas ni precios ajustados retrospectivamente.

Cuando se ejecute con el original local:

\`\`\`bash
python -m unittest tests.test_sec_first_cut_equity_bridge
python scripts/sec_first_cut_equity_bridge.py --original out/sec-originals/0000950170-24-118967.txt --output out/sec-msft-equity-bridge-research.json
\`\`\`

El resultado es **una candidatura de correspondencia entre dos declaraciones originales fechadas**. Ni el 10-Q ni un ticker de N-PORT acreditan por sí solos que el CUSIP corresponde jurídicamente a ese CIK en todo el periodo; para ello se requiere evidencia histórica independiente de clases, cambios de identificador, fuente de proveedor permanente y precios con eventos corporativos. La fuente no promueve posiciones a universo invertible, no modifica H0.3 ni suma cortes u orígenes confirmatorios.

**Aceptación técnica:** ejecución con ambos originales, clasificación correcta de todas las filas de la tabla 12(b), comprobación de los recibos N-PORT del símbolo, CUSIP documentado y pruebas adversariales. **Aceptación de H1.2:** sigue pendiente de cadena completa CUSIP–instrumento–serie de precios y disponibilidad temporal de la totalidad del universo.
