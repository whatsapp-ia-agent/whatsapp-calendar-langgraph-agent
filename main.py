import os
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks
from contextlib import asynccontextmanager
from typing import Dict, Any

# LangGraph y LangChain
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.prebuilt import ToolExecutor
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain_core.messages import HumanMessage, AIMessage

# Clientes propios
from whatsapp_client import send_text_message, send_catalog, send_product
from calcom_client import check_availability, create_booking
from langfuse_setup import get_langfuse_handler, langfuse_client
from models import AgentState

# Google Cloud Firestore (para cache de perfil)
from google.cloud import firestore
db_firestore = firestore.AsyncClient()

# --- 1. Configuración inicial ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql://user:pass@/db?host=/cloudsql/...

# Checkpointer de PostgreSQL
checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)

# Inicializar el grafo una sola vez al levantar el servicio
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup de checkpointer
    await checkpointer.setup()
    yield
    # Cierre de conexiones si es necesario

app = FastAPI(lifespan=lifespan)

# --- 2. Definir herramientas (tools) ---
@tool
async def show_catalog(chat_id: str) -> str:
    """Muestra el catálogo de productos al usuario."""
    await send_catalog(chat_id)
    return "Catálogo enviado"

@tool
async def book_appointment(name: str, email: str, date: str, time: str) -> str:
    """Agenda una cita en Cal.com."""
    booking = await create_booking(name, email, date, time)
    return f"Cita agendada para {date} a las {time}. ID: {booking['id']}"

@tool
async def send_message(chat_id: str, text: str) -> str:
    """Envía un mensaje de texto al usuario."""
    await send_text_message(chat_id, text)
    return "Mensaje enviado"

tools = [show_catalog, book_appointment, send_message]
tool_executor = ToolExecutor(tools)

# --- 3. Definir el LLM con binding de herramientas ---
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
llm_with_tools = llm.bind_tools(tools)

# --- 4. Nodos del grafo ---

async def classify_intent(state: AgentState) -> Dict[str, Any]:
    """
    Clasifica la intención del usuario usando el LLM.
    """
    # Construir mensajes para el LLM
    messages = state.messages.copy()
    # Añadir un prompt de sistema
    system_prompt = (
        "Eres un asistente de perfumería. Clasifica la intención del usuario en: "
        "'catalog' si quiere ver productos, 'schedule' si quiere agendar cita, "
        "'respond' para otros casos. Si pide ambos, prioriza 'schedule'. "
        "Responde con el siguiente formato: {\"intent\": \"catalog|schedule|respond\"}"
    )
    messages.insert(0, HumanMessage(content=system_prompt))
    
    # Llamar al LLM con callback de Langfuse
    handler = get_langfuse_handler(user_id=state.chat_id)
    response = await llm.ainvoke(messages, config={"callbacks": [handler]})
    
    # Parsear la respuesta (simplificado, en producción usarías JSON)
    content = response.content
    if "catalog" in content.lower():
        next_step = "catalog"
    elif "schedule" in content.lower():
        next_step = "schedule"
    else:
        next_step = "respond"
    
    # Guardar la respuesta en el estado
    state.messages.append(AIMessage(content=content))
    return {"next_step": next_step, "messages": state.messages}

async def handle_catalog(state: AgentState) -> Dict[str, Any]:
    """
    Ejecuta la herramienta de catálogo.
    """
    result = await show_catalog(state.chat_id)
    # Responder con un mensaje de texto
    await send_text_message(state.chat_id, "Aquí tienes nuestro catálogo. ¿Te gusta algún producto?")
    return {"messages": state.messages + [AIMessage(content=result)]}

async def handle_schedule(state: AgentState) -> Dict[str, Any]:
    """
    Maneja el agendamiento. Extrae nombre, email, fecha y hora de la conversación.
    En producción usarías un sistema de extracción de entidades.
    """
    # Simulación: extraer datos del mensaje (deberías usar un parser o pedir al usuario)
    # Por ahora, pedimos los datos al usuario mediante mensajes.
    await send_text_message(state.chat_id, "Para agendar, por favor dinos tu nombre, correo, fecha (YYYY-MM-DD) y hora (HH:MM).")
    # Aquí deberías guardar un estado intermedio para esperar la respuesta.
    return {"messages": state.messages + [AIMessage(content="Solicitando datos de cita.")]}

async def handle_respond(state: AgentState) -> Dict[str, Any]:
    """
    Genera una respuesta general usando el LLM.
    """
    handler = get_langfuse_handler(user_id=state.chat_id)
    response = await llm.ainvoke(state.messages, config={"callbacks": [handler]})
    await send_text_message(state.chat_id, response.content)
    return {"messages": state.messages + [AIMessage(content=response.content)]}

# --- 5. Construcción del grafo ---
workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_intent)
workflow.add_node("catalog", handle_catalog)
workflow.add_node("schedule", handle_schedule)
workflow.add_node("respond", handle_respond)

workflow.set_entry_point("classify")

# Transiciones condicionales
workflow.add_conditional_edges(
    "classify",
    lambda state: state.next_step,
    {
        "catalog": "catalog",
        "schedule": "schedule",
        "respond": "respond",
    }
)
workflow.add_edge("catalog", END)
workflow.add_edge("schedule", END)
workflow.add_edge("respond", END)

# Compilar el grafo con el checkpointer de PostgreSQL
graph = workflow.compile(checkpointer=checkpointer)

# --- 6. FastAPI Endpoints ---

@app.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook que recibe los mensajes de OpenWA.
    """
    data = await request.json()
    chat_id = data.get("chatId")
    message_text = data.get("body", "")
    sender_name = data.get("senderName", "")

    # Iniciar una traza raíz con Langfuse usando el decorador manual
    # Usamos background_tasks para no bloquear la respuesta de OpenWA
    background_tasks.add_task(process_message, chat_id, message_text, sender_name)
    return {"status": "ok"}

async def process_message(chat_id: str, message: str, sender_name: str):
    """
    Procesa el mensaje con el agente de LangGraph, envolviendo con Langfuse.
    """
    # Creamos una traza con Langfuse de forma manual para todo el proceso
    trace = langfuse_client.trace(
        name="whatsapp-conversation",
        user_id=chat_id,
        metadata={"sender_name": sender_name}
    )

    # Obtener el span para la ejecución del grafo
    with trace.span(name="langgraph-execution") as span:
        # Estado inicial
        initial_state = AgentState(
            messages=[{"role": "user", "content": message}],
            chat_id=chat_id,
            user_name=sender_name,
        )

        # Configuración para el checkpointer (thread_id = chat_id)
        config = {"configurable": {"thread_id": chat_id}}

        # Invocar el grafo con el callback handler de Langfuse
        handler = get_langfuse_handler(user_id=chat_id, session_id=chat_id)
        try:
            final_state = await graph.ainvoke(
                initial_state.dict(),
                config=config,
                config={"callbacks": [handler]}
            )
            span.update(output=final_state)
        except Exception as e:
            span.update(status="error", status_message=str(e))
            raise

        # Actualizar el perfil en Firestore con la información extraída
        # (simplificado: guardamos el último mensaje)
        user_ref = db_firestore.collection("users").document(chat_id)
        await user_ref.set({"last_message": message, "name": sender_name}, merge=True)

    # Finalizar la traza
    trace.flush()

@app.post("/webhook/calcom")
async def calcom_webhook(request: Request):
    """
    Webhook que recibe notificaciones de Cal.com (booking creado).
    """
    data = await request.json()
    # Aquí se puede programar un recordatorio con un scheduler (por ejemplo, Celery o BackgroundTasks)
    # Por simplicidad, solo lo logueamos
    print(f"Booking creado: {data}")
    # Podríamos enviar un mensaje de confirmación por WhatsApp
    return {"status": "ok"}

# Endpoint de salud para GCP
@app.get("/health")
async def health():
    return {"status": "healthy"}
