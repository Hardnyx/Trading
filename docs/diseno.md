# Criterios de interfaz

Herramienta personal para componer una cartera con los datos del corte disponible y revisar después diferencias relevantes. La prioridad visual es una terminal financiera: datos densos, paneles rectos, navegación por funciones y tablas.

## Flujo

1. Proponer una cartera ex ante o seleccionar manualmente activos, capital y pesos.
2. Revisar fundamentos, valoración y proyecciones.
3. Registrar una composición con su corte de precios y fundamentos.
4. Cargar cortes posteriores y revisar cambios de peso, resultados, valoración y riesgo.
5. Marcar revisiones atendidas o registrar una nueva composición.

## Decisiones aplicadas

| Criterio                     | Aplicación                                                                                              |
| ---------------------------- | ------------------------------------------------------------------------------------------------------- |
| Visibilidad del estado       | Fecha de corte, fecha del registro, estado de cálculo y avisos de datos ausentes.                       |
| Correspondencia con la tarea | Nombres financieros directos y separación entre composición, seguimiento, investigación y proyección.   |
| Consistencia                 | Mismas columnas, unidades, formatos y acciones para cada activo.                                        |
| Control                      | Supuestos editables, importación/exportación, cierre con Escape y registro explícito de la composición. |
| Prevención de errores        | Validación de archivos y pesos; el registro requiere una suma de 100%.                                  |
| Reconocimiento               | Funciones visibles F1–F8, nombres de activos, enlaces a las fuentes y motivos de cada revisión.         |
| Eficiencia                   | Búsqueda con `/`, atajos por función y simulación en un Web Worker.                                     |
| Legibilidad                  | Números tabulares, alineación decimal, signos explícitos y colores de uso estable.                      |
| Densidad                     | Resúmenes en una fila, comparaciones en tablas; sin gráficos de dona ni bloques promocionales.          |

## Color

- Naranja: encabezados, función activa y supuestos del modelo.
- Azul: acciones y enlaces a activos/documentos. Todos los tickers usan el mismo componente (`.symbol`): IBM Plex Mono en azul y, donde el activo existe en el universo, clic para abrir su ficha.
- Verde y rojo: dirección de cambios o resultados. Las cifras llevan signos o etiquetas; el color no es el único indicador.
- Gris: estructura, información secundaria y valores de referencia.

Contrastes calculados para la paleta principal sobre `#080808`: texto `#dedede`, 14.89:1; texto secundario `#ababab`, 8.72:1; enlaces `#82c3ff`, 10.68:1; verde, 10.23:1; rojo, 7.58:1. Negro sobre el naranja de encabezado: 10.21:1.

Superficies y bordes usan una escala neutra (`--panel`, `--surface`, `--raised`; `--line-soft`, `--line`, `--line-strong`). Los paneles tienen encabezado oscuro con título naranja; el naranja sólido se reserva para la función activa, la acción principal y la línea superior de las métricas.

## Tipografía y espaciado

- IBM Plex Sans para interfaz y textos explicativos; IBM Plex Mono para cifras, etiquetas, tablas y códigos. Ambas se sirven desde `dist/assets/fonts` con los archivos divididos oficiales de IBM, sin modificar (SIL Open Font License): latín, latín extendido, griego (en Sans) y símbolos, cada uno con su `unicode-range`, para que flechas, letras griegas y operadores no caigan en fuentes del sistema. Plex Sans actúa como respaldo de Plex Mono para el griego. Los índices de las fórmulas usan `<sub>`/`<sup>` y la dirección en la cinta de precios se dibuja con CSS, porque Plex no incluye esos glifos.
- Escala de tamaños: 10, 11, 12, 14, 18, 24 y 32 px (`--fs-xs` a `--fs-3xl`). No se usan tamaños menores de 10 px.
- Espaciado en múltiplos de 4 px. Los paneles tienen un relleno interior de 12 px y una separación de 12 px entre ellos. Controles y botones miden 28 px de alto.

## Movimiento

El movimiento señala cambios, nunca decora. Los diálogos aparecen con un fundido del fondo y un leve ascenso, y salen a la inversa; reemplazar un diálogo por otro no vuelve a oscurecer el fondo. Los avisos entran y salen deslizándose. Al cambiar de función (F1–F8) sólo el área de trabajo hace un fundido corto; el encabezado y la pestaña activa cambian al instante. Las cifras calculadas (métricas, propuesta, decisión, simulación) que cambian tras un recálculo se iluminan en ámbar durante 1,2 s; el destello es neutro porque en métricas de riesgo subir no es bueno, y no se aplica a valores que se editan directamente, como los deslizadores de valoración. Como la interfaz se redibuja por completo en cada cambio de estado, ninguna animación depende del redibujado: los destellos continúan donde iban. Con `prefers-reduced-motion` no hay transiciones de vista ni de diálogos.

## Cinta de mercado

La cinta superior muestra referencias fijas (SPY, QQQ, IWM, TLT, GLD, SHY) con el último cierre y la variación entre cierres; no son precios en tiempo real. Si todas caben, la cinta permanece estática. Si no caben (móvil o tablet), se reparten en filas equilibradas que giran hacia arriba cada 5 segundos. El giro se detiene con el puntero encima, con el foco del teclado dentro de la cinta y con la pestaña oculta; el foco en una referencia oculta muestra su fila. Con `prefers-reduced-motion` no hay giro: la cinta queda en una fila desplazable a mano.

## Trabajo en curso

Los cálculos largos se señalan sin bloquear la página: el botón que trabaja muestra un indicador giratorio (`aria-busy="true"`), la barra de funciones y el panel de robustez llevan una barra de progreso indeterminada, y los textos "Calculando…" pulsan con su propio indicador. Con `prefers-reduced-motion` las animaciones se sustituyen por indicadores estáticos.

Se incluyen foco visible, etiquetas de campos, enlace para saltar al contenido, navegación por teclado y diálogos con control del foco. Las tablas conservan sus columnas y permiten desplazamiento horizontal en pantallas estrechas. No se afirma una auditoría integral de conformidad WCAG.

## Referencias

- [Nielsen Norman Group: 10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/).
- [W3C: WCAG 2.2](https://www.w3.org/TR/WCAG22/).
- [W3C: contraste mínimo](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
- [W3C: referencia rápida de accesibilidad](https://www.w3.org/WAI/WCAG22/quickref/).

La referencia visual es Bloomberg Terminal. El proyecto tiene identidad propia y no utiliza sus datos, logotipos ni software.

## Estado de las fuentes

El panel distingue una descarga correcta, una descarga fallida y una fuente pendiente de configuración. Las fechas de precios y fundamentos se mantienen visibles aunque una fuente no se actualice.

Captura de verificación del 24 de octubre de 2026:

![Estado de las fuentes de datos](data-sources.jpg)

## Mandato y decisiones

F8 concentra restricciones, cuenta y ejecución; F5 conserva las hipótesis y la evidencia por emisor; F2 muestra revisiones y evaluación prospectiva. Los campos se rotulan con moneda, plazo y unidad. Las cantidades ingresadas, las referencias teóricas y las órdenes propuestas tienen contextos explícitos. Registrar una referencia no confirma una operación.

Los resultados muestran costos netos, alternativas comparables y datos faltantes. Una tesis contradicha requiere revisión. El diario diferencia pendientes, retrospectivos y casos sin realización comparable. La incertidumbre asumida se distingue de la precisión medida.
