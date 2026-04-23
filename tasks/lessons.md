# Lessons

- Cuando una corrección frontend no resuelve el bug reportado, no asumir que el efecto inicial sí corre: validar si el estado interno y lo que muestra el `<select>` pueden estar desincronizados.
- En componentes con datos batch + recompute interactivo, la carga inicial debe tener un camino explícito de recomputación visual; no debe depender únicamente del mismo flujo de cambio manual.
- Si una pantalla depende de opciones remotas para construir filtros válidos, no montes los componentes stateful antes de tener esas opciones; los `useState(initializer)` no se reejecutan cuando llegan props tardías.
