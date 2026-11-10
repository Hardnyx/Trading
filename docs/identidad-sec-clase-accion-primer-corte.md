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

## Primera confrontación real de clases de valores

El trabajo se publicará primero con pruebas sintéticas y un control de las declaraciones originales N-PORT del corte. La ejecución del workflow EDGAR-only con el mismo hash original recogerá el símbolo y su **clase de valor** del 10-Q, y contrastará ese símbolo con los recibos N-PORT. El archivo JSON se conservará en `out/` hasta auditar su contenido; un fallo de extracción no se interpreta como una incongruencia de identidad ni autoriza un reemplazo por información actual.

## Primera intersección real de fuentes originales (10-nov-2026 UTC)

El [workflow de investigación 42888451636](https://github.com/Hardnyx/Trading/actions/runs/42888451636) se completó correctamente, verificando el SHA-256 del archivo EDGAR 10-Q original antes de extraer la tabla de registro de valores. El original enumera una **acción ordinaria MSFT (Nasdaq)** y, separadamente, notas de deuda al 3,125 % con vencimiento 2028 y al 2,625 % con vencimiento 2033, ambas con el **mismo** símbolo MSFT. El ticker solo no permite inferir la clase de activo.

Desde el N-PORT original de SPY, accession `0001752724-24-264697` y SHA-256 `abdf627787ebf4d536b9166be4416a1d434a30ed38d630dba7f57c39f58bcbd5`, se recuperó una única posición de Microsoft con `CUSIP 594918104`, número de posición original **181** y peso **0,06566774536397**. El símbolo se sustenta en otro N-PORT original, del fondo **ILCB**, accession `0001752724-24-295861`, con posiciones fechadas 31-oct-2024 y disponibilidad conservadora desde 30-dic-2024, anterior al corte de 31-dic-2024. No se incorpora ese hecho como si hubiera sido conocido en octubre, ni se equipara una posición del fondo con una cotización ejecutable.

El [informe íntegro](../data/historical/sec-first-cut-msft-equity-bridge-v1.json) se conserva con el SHA-256 exacto del artefacto real `0c689aa0573a7b945c6b210509549b77edc3daf6401d8fe5caa40ef91d4ba3bf`. El auditor `python scripts/sec_first_cut_equity_bridge_receipt.py --verify` vuelve a reconstruir desde los originales SEC del repositorio la posición SPY, sus recibos de ticker y sus hashes, y rechaza manipulaciones de clase, peso, CUSIP, fecha de disponibilidad y banderas de elegibilidad.

**Alcance aprobado:** correspondencia exploratoria de **dos fuentes originales con fecha** para un valor y una clase de acciones. **No aprobado:** vínculo jurídico histórico CIK–CUSIP, continuidad del instrumento, FIGI/ID permanente, identificación del mercado de ejecución, precios históricos brutos, dividendos, splits, delistings, cobertura del universo ni habilidades predictivas. El conjunto de 504 solicitudes originales sigue necesitando fuentes de proveedor y la revisión de identidades/fechas para un corte integral.
