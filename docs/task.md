# Python Backend Challenge

# Document Processing Gateway

## Formato de entrega

> El código debe entregarse en un repositorio git (evitar mencionar Inceptia para prevenir indexación). Notificando del mismo enviando un mail a: [gustavo.mahia@inceptia.ai](mailto:gustavo.mahia@inceptia.ai)
> 

---

## Contexto

Estás construyendo un microservicio que orquesta el procesamiento de documentos a través de un pipeline de proveedores externos. El sistema recibe documentos, los pasa por distintas etapas de procesamiento (extracción de texto, análisis y enriquecimiento), y publica eventos de cada paso para que otros servicios downstream puedan reaccionar.

---

## Arquitectura General

```
                         ┌───────────────────┐
   Request de            │                   │
   procesamiento ──────► │    Document       │ ◄──► Proveedor de Extracción (mock)
                         │    Processing     │
                         │    Gateway        │ ◄──► Proveedor de Análisis (mock)
                         │                   │
   Consulta de estado ──►│                   │ ◄──► Proveedor de Enriquecimiento (mock)
                         └────────┬──────────┘
                                  │
                                  ▼
                          Event Streaming
                       (eventos del pipeline)
                                  │
                                  ▼
                           Consumer(s)
                        (servicios downstream)
```

---

## Requerimientos

### 1. API REST — Gestión del pipeline de procesamiento

Diseñar e implementar una API que exponga los siguientes endpoints:

| Acción | Descripción |
| --- | --- |
| **Enviar documento a procesar** | Recibe metadata del documento (nombre, tipo, contenido simulado como string) y un `pipeline_config` que indica qué etapas ejecutar. Crea una sesión de procesamiento y retorna un `job_id`. |
| **Consultar estado de un job** | Dado un `job_id`, retorna el estado actual del procesamiento y los resultados parciales disponibles. |
| **Cancelar un job** | Cancela un procesamiento en curso. Solo es posible si el job no finalizó. |
| **Listar jobs** | Retorna los jobs con soporte para filtrado por estado. |

**Sobre las sesiones de procesamiento:**

- Cada job debe tener un ciclo de vida con estados claros: `pending`, `processing`, `completed`, `failed`, `cancelled`.
- Las transiciones de estado deben ser consistentes (e.g., no se puede pasar de `completed` a `processing`).
- El diseño de rutas, payloads, status codes y estructura de respuestas queda a criterio del candidato.

### 2. Pipeline de procesamiento con proveedores externos

El procesamiento de un documento pasa por hasta 3 etapas secuenciales. Cada etapa la resuelve un proveedor externo (simulado):

| Etapa | Descripción del mock |
| --- | --- |
| **Extracción** | Recibe el contenido crudo, retorna texto extraído. |
| **Análisis** | Recibe texto extraído, retorna entidades/categorías detectadas. |
| **Enriquecimiento** | Recibe entidades, retorna metadata enriquecida. |

**Requerimientos del pipeline:**

- Las etapas ejecutadas dependen del `pipeline_config` enviado en el request (ej: un documento puede necesitar solo extracción y análisis, sin enriquecimiento).
- Los proveedores deben estar detrás de una **interfaz/abstracción** que permita intercambiarlos sin modificar la lógica del gateway.
- Implementar al menos **dos variantes mock** de un mismo proveedor (ej: `FastExtractor` que responde en 100ms y `SlowExtractor` que responde en 2s) para demostrar que la abstracción funciona.
- Los mocks deben simular latencia real (100-500ms) para que el manejo asincrónico tenga sentido.

### 3. Event Streaming — Publicación y consumo de eventos

Cada transición relevante del pipeline debe publicarse como evento mediante una tecnología de **event streaming** que garantice:

- **Persistencia de mensajes** (los eventos no se pierden si un consumer no está disponible).
- **Consumer groups** o equivalente (múltiples consumers independientes pueden procesar el mismo stream).
- **Acknowledgment** (un mensaje se considera procesado solo cuando el consumer lo confirma explícitamente).

La elección de tecnología es libre y debe justificarse en el README.

**Eventos mínimos esperados:**

- `job.created` — cuando se recibe un documento a procesar
- `job.stage_started` — cuando comienza una etapa del pipeline
- `job.stage_completed` — cuando finaliza una etapa exitosamente (incluye resultado parcial)
- `job.completed` — cuando finaliza todo el pipeline
- `job.failed` — cuando una etapa falla
- `job.cancelled` — cuando se cancela un job

Cada evento debe incluir al menos: `job_id`, `timestamp`, `event_type` y `payload` relevante.

**Implementar además un consumer** que lea del stream usando consumer groups (o equivalente en la tecnología elegida) y loguee los eventos procesados. Este consumer simula un servicio downstream.

### 4. Manejo de errores y resiliencia

- ¿Qué pasa si un proveedor falla o responde con timeout en una etapa intermedia del pipeline? El sistema debe manejar esto sin perder el progreso de las etapas anteriores.
- ¿Qué pasa si el broker de eventos no está disponible momentáneamente?
- Implementar al menos **una estrategia** de resiliencia (retry con backoff, circuit breaker, fallback, dead letter queue, etc.) y justificar la elección en el README.

### 5. Testing

- Tests unitarios para la lógica central (gestión de sesiones, transiciones de estado, orquestación del pipeline).
- Al menos un test de integración que valide el flujo completo: creación de job → ejecución del pipeline → publicación de eventos → finalización.

---

## Bonus (opcional)

Exponer una interfaz **gRPC** como alternativa a la API REST para al menos dos operaciones del gateway (por ejemplo, enviar documento a procesar y consultar estado de un job).

Se valorará:

- Diseño del archivo `.proto` (definición de mensajes y servicios).
- Que la lógica de negocio no se duplique entre la interfaz REST y gRPC (ambas deben compartir la misma capa de servicio).

---

## Entregables

1. **Repositorio git**.
2. [**README.md**](http://readme.md/) con instrucciones para levantar el proyecto (idealmente con Docker Compose) y un diagrama simple de la arquitectura implementada.
3. **Tests** ejecutables.

---

## Restricciones

- **Framework**: libre elección (FastAPI, Flask, Django, etc.).
- **Python 3.10+**
- **Event streaming**: cualquier tecnología o implementación que cumpla los requisitos de persistencia, consumer groups y acknowledgment (ver sección 3).
- No se espera un sistema production-ready, pero sí que las decisiones de diseño reflejen experiencia profesional.
