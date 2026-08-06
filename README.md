# Agente WhatsApp con LangGraph, Langfuse, y Cal.com

Este repositorio contiene un agente conversacional para WhatsApp Business que:
- Atiende mensajes de clientes.
- Muestra el catálogo de productos de WhatsApp Business.
- Agenda citas con Cal.com.
- Registra todas las interacciones en Langfuse Cloud para monitoreo y análisis.

## Despliegue en GCP

1. Configura las variables de entorno en Secret Manager.
2. Crea la instancia de Cloud SQL PostgreSQL.
3. Habilita Firestore.
4. Conecta tu repositorio a Cloud Build (trigger en main).
5. Despliega con `gcloud builds submit` o mediante el trigger automático.

## Instrumentación con Langfuse

Cada interacción del usuario genera una traza en Langfuse con:
- ID de usuario (número de teléfono).
- Latencia de cada nodo y herramienta.
- Costo estimado de tokens de OpenAI.
- Errores y logs.

Puedes ver el dashboard en [cloud.langfuse.com](https://cloud.langfuse.com).
