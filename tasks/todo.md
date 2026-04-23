# Todo

- [x] Actualizar README con modelo, precios y manejo del archivo Excel raw.
- [x] Revisar por qué la sección de insights muestra narrativa pero no gráfica/tabla en la primera carga.
- [x] Corregir la inicialización de filtros y recomputación visual inicial.
- [x] Verificar typecheck, lint disponible y tests relevantes.

## Review

- Se quitó el salto del primer recompute visual para que las secciones se recalculen al montar si tienen filtros válidos.
- Si una sección llega sin findings y el filtro queda vacío, se hidrata desde la métrica mencionada en narrativa/recomendación cuando llegan las opciones.
- El reporte ahora espera a tener `filter-options` antes de montar las tarjetas, así los filtros iniciales nacen completos y no dependen de hidratación posterior.
- Las tarjetas usan `report.generated_at` en la key para no conservar estado visual viejo entre generaciones.
- El selector de métricas ahora muestra un placeholder cuando el estado interno no tiene métrica, evitando que el navegador muestre una opción que no corresponde al estado real.
- README actualizado con GPT-5.4 mini, tarifas oficiales consultadas y costo observado de pruebas.
- Verificación: `npx tsc --noEmit`, `npm run typecheck`, `ruff check .`, `pytest tests/test_insights/test_service.py tests/test_insights/test_charts.py`, y `pytest` completo pasan.
- `npm run lint` sigue bloqueado por el setup interactivo de `next lint`; no es causado por este cambio.
