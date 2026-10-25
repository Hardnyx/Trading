# Trading

Terminal de research para acciones y ETFs de Estados Unidos. Incluye proyecciones, valoración y análisis de riesgo.

Herramienta de uso personal para revisar activos, configurar supuestos y analizar la distribución de resultados de una cartera.

[Abrir aplicación](https://hardnyx.github.io/Trading/)

## Qué incluye

- **Componer cartera:** propuesta ex ante con un clic, edición de pesos y registro de una referencia con fecha de corte.
- **Seguimiento:** comparación con la referencia registrada, revisiones con motivos y estado de atención.
- **Proyecciones:** Monte Carlo multiactivo con difusión lognormal correlacionada y extensión con saltos sistémicos de tipo Merton. Hasta 5,000 trayectorias, semilla reproducible y horizonte de tres meses a tres años.
- **Research:** filtros, precios, P/E, FCF yield, volatilidad y comparación contra el modelo propio.
- **Valoración:** crecimiento, múltiplo de salida, horizonte y rentabilidad exigida editables. Escenarios adverso, base y favorable.
- **Riesgo:** correlaciones, contribución a la varianza, beta, drawdown, VaR/CVaR históricos y escenarios de estrés.
- **Macro:** curva nominal del Treasury, IPC y desempleo, con fechas y enlaces a sus fuentes.

## Ejecutar

No necesita un framework, una instalación de npm ni un servidor de aplicación. Con Python 3.10 o superior:

```bash
git clone https://github.com/Hardnyx/Trading.git
cd Trading
python -m http.server 8000 --directory dist
```

Abre `http://localhost:8000`. El navegador debe soportar módulos JavaScript y Web Workers. Las simulaciones se ejecutan en un worker para mantener fluida la interfaz.

## Actualizar datos

```bash
python scripts/refresh_data.py
```

También puedes usar un corte máximo:

```bash
python scripts/refresh_data.py --as-of 2026-10-24
```

El script utiliza únicamente la biblioteca estándar de Python. Guarda respuestas temporalmente en `.cache/`, limita las solicitudes a la SEC y reemplaza el corte de forma atómica. Si una fuente falla, conserva datos previos y registra el aviso; no fabrica observaciones.

En GitHub está disponible el workflow manual **Refresh market data**. Actualiza el archivo de datos en `main` y llama al despliegue de GitHub Pages con el SHA del nuevo corte. El botón de la web **Cargar último corte publicado** descarga el archivo que ya está en el hosting, sin ejecutar el extractor.

## Composición y seguimiento

**Proponer cartera** compara hasta 400 carteras con 1,000 escenarios futuros comunes y comprueba la elegida con 5,000 escenarios nuevos. Entre las candidatas que satisfacen los límites, elige la de mayor crecimiento logarítmico esperado. La búsqueda es aproximada, con pesos en pasos de 5 puntos porcentuales; no garantiza un óptimo global.

Las acciones necesitan BPA y precio conocidos al corte y un ancla de valoración superior al rendimiento supuesto de la reserva SHY. Los índices amplios y otros ETFs permanecen disponibles para composición manual. Los precios históricos estiman covarianza y correlaciones; su rentabilidad pasada no determina la media futura de la propuesta.

Se simulan difusión correlacionada, saltos sistémicos y una distribución triangular del ancla fundamental entre los escenarios adverso y favorable, con modo en el base. Un factor compartido mueve las anclas de las acciones. Estos límites y su dependencia son supuestos explícitos, no distribuciones calibradas de beneficios ni probabilidades observadas.

Los límites iniciales, editables en la página, son: 20% por acción, 35% por sector, 50% en SHY, seis posiciones, correlación máxima de 0.85, CVaR 95% máximo de 20% y probabilidad de pérdida máxima de 45% al horizonte. Son parámetros de trabajo. Si no hay una propuesta que los cumpla, el programa conserva la cartera actual.

El corte, los fundamentos utilizados, los supuestos, las semillas y ambas simulaciones quedan registrados al exportar o registrar la composición. Cambiar pesos o supuestos marca la propuesta como modificada. La segunda simulación comprueba estabilidad numérica con nuevas realizaciones del modelo; no constituye validación predictiva con futuros datos de mercado.

La aplicación comienza sin posiciones. Selecciona activos, ajusta los pesos al 100%, configura el capital y revisa los supuestos antes de pulsar **Registrar composición**. El registro conserva precios ajustados, pesos, fundamentos y supuestos del corte utilizado. Los cambios posteriores del constructor no modifican esa referencia hasta registrar otra composición.

Al cargar un corte posterior, el seguimiento evalúa:

- Desvío del peso por evolución de los activos.
- Precio por encima del valor del modelo propio.
- Caída del BPA o cambio de signo del FCF simple.
- Aumento de volatilidad o pérdida desde el registro.
- Nuevas presentaciones 10-K, 10-Q y 8-K, entre otras, en la SEC.

Cada revisión muestra el criterio, la evidencia y qué revisar. Los umbrales son editables. La aparición de una presentación regulatoria no se interpreta por sí sola como una orden de compra o venta.

**Avisos:** se evalúan al cargar datos y al detectar un nuevo corte publicado mientras la página está abierta. Los avisos del navegador requieren permiso explícito. No hay un monitor en segundo plano con la página cerrada. El workflow de actualización publica el corte cuando termina la descarga.

La referencia se conserva en el navegador, junto con los supuestos y el estado de las revisiones. La exportación JSON permite conservarla y trasladarla. La evolución de la cartera registrada usa Adj Close y representa una evolución teórica ajustada, no una conciliación de posiciones del broker.

### Fuentes

| Fuente                                | Contenido                                              | Acceso                                                   |
| ------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------- |
| SEC EDGAR Company Facts y Submissions | Conceptos XBRL y presentaciones regulatorias recientes | API oficial, sin clave                                   |
| Yahoo Finance chart                   | Cierres, Adj Close, volumen y dividendos               | Endpoint público no oficial; disponibilidad sin garantía |
| U.S. Treasury                         | Curva par nominal                                      | Feed XML oficial                                         |
| BLS                                   | IPC y desempleo desestacionalizados                    | API pública oficial                                      |

Universo inicial: AAPL, MSFT, NVDA, AMZN, GOOGL, META, JPM, V, XOM, JNJ, PG, COST, SPY, QQQ, IWM, TLT, GLD y SHY. La cobertura financiera puede variar entre emisores: los datos ausentes se muestran como `—`.

## Cómo se calculan las proyecciones

El retorno central puede venir de la valoración propia o de un supuesto manual. Se aplica a un proceso de difusión correlacionado cuya covarianza se estima con EWMA sobre retornos logarítmicos. Se regularizan las covarianzas fuera de la diagonal un 5%.

En la extensión Merton se añaden saltos comunes a la cartera. Su frecuencia, media logarítmica y dispersión son parámetros de estrés propios. La compensación del salto preserva la media esperada del ancla. El modelo utiliza pasos semanales y mantiene constantes las unidades de cada posición, sin costos ni impuestos.

La valoración parte de BPA diluido o FCF/acción, aplica crecimiento y múltiplo de salida y descuenta el resultado. No hay un DCF completo ni consenso externo. Los dividendos por acción se mantienen constantes. El retorno anual equivalente aproxima el efectivo de dividendos como recibido al final del horizonte. El ancla ya incorpora ese efectivo y no se suma nuevamente en Monte Carlo.

Los escenarios de valoración usan variaciones explícitas respecto al supuesto base: crecimiento −7/+5 puntos porcentuales y múltiplo ×0.80/×1.15 para adverso/favorable. No se asignan probabilidades empíricas a esos escenarios.

### Comprobación histórica

El laboratorio muestra una comprobación walk forward: estima bandas de riesgo usando las últimas 126 sesiones y observa el retorno de las 21 siguientes, con ventanas futuras no solapadas. Reporta la cobertura de la banda al 90%, centrada en retorno logarítmico cero. No utiliza retornos futuros para estimar esa banda.

Esto comprueba la cobertura de un modelo de riesgo; **no valida la capacidad predictiva del ancla fundamental o de los saltos**. Las muestras son pequeñas y el universo está seleccionado con información actual.

### Límites relevantes

- Universo actual y últimos estados rectificados disponibles. No hay una base histórica point-in-time ni cobertura completa de deslistados.
- Las bandas P05–P95 son cuantiles condicionales al modelo, no intervalos de confianza del futuro real.
- Volatilidad y correlaciones pueden cambiar. EWMA fija su nivel inicial durante la proyección.
- Los saltos se añaden a la volatilidad histórica sin separar sus componentes: es un escenario de estrés, no una calibración estructural.
- El drawdown simulado usa observaciones semanales; puede omitir caídas entre esos puntos.
- Las métricas históricas utilizan pesos constantes y rebalanceo diario teórico. La proyección usa buy & hold; son ejercicios distintos y están rotulados.
- FCF = flujo de operación − capex con períodos comparables. No representa un FCFE completo. No se muestra FCF yield para el sector financiero.
- Las acciones de múltiples clases y los conceptos personalizados de XBRL pueden no tener cobertura en Company Facts. Se descartan acciones en circulación con más de 400 días de antigüedad.
- Las series macro aportan contexto y aún no son predictores incorporados al drift. Las observaciones se muestran según su período, no como si todas se publicaran el mismo día.

## Validación

Con Node.js 20+ y Python 3.10+:

```bash
npm run check
npm test
python -m unittest discover -s tests -p 'test_*.py'
```

Las pruebas cubren alineación de series, covarianzas, pesos, contribución al riesgo, valoración, reconstrucción TTM, fechas de publicación, factorización de Cholesky, semilla reproducible, media de GBM, compensación de saltos y ventanas de comprobación.

## Estructura

```text
dist/
  index.html
  assets/
    css/           Estilos y paleta
    js/            Cálculos, controladores y workers
      ui/          Vistas, formatos y carga de plantillas
  templates/       HTML por sección y gráficos
  data/market.json Corte descargado de fuentes públicas
scripts/
  refresh_data.py  Actualización y normalización
tests/            Cálculos financieros y estocásticos
```

La aplicación no envía los pesos ni los supuestos a un servidor. Se guardan en el navegador y pueden exportarse a un archivo JSON.

Referencias: [Kelly con riesgo restringido](https://www.web.stanford.edu/~boyd/papers/kelly.html), [CVaR](https://www.sciencedirect.com/science/article/pii/S0378426602002716), [Merton, retornos discontinuos](https://dspace.mit.edu/entities/publication/e63635d9-d2bf-40ce-a79b-67786dd9f105), [RiskMetrics Technical Document](https://www.msci.com/research-and-insights/paper/1996-riskmetrics-technical-document), [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [Treasury XML](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed) y [BLS API](https://www.bls.gov/developers/).

Proyecto independiente, sin afiliación a Bloomberg.

Criterios de interfaz y referencias formales: [docs/diseno.md](docs/diseno.md).
