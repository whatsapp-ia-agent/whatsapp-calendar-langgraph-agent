import os
import asyncpg
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

# --- 1. Configuración inicial ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql://user:pass@host:port/db

# Checkpointer de PostgreSQL
checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)

# --- Función para crear tablas automáticamente ---
async def init_db():
    """Crea las tablas necesarias si no existen."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Tabla para perfiles de usuario (reemplaza Firestore)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                chat_id TEXT PRIMARY KEY,
                user_name TEXT,
                last_message TEXT,
                context JSONB,
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        print("✅ Tabla 'user_profiles' verificada/creada.")
    finally:
        await conn.close()

# --- Lifespan para inicializar todo ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Setup del checkpointer de LangGraph
    await checkpointer.setup()
    print("✅ Checkpointer de LangGraph inicializado.")
    
    # 2. Crear tablas adicionales (perfiles de usuario)
    await init_db()
    print("✅ Base de datos lista.")
    
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

# --- 4. Funciones auxiliares para perfiles de usuario (reemplaza Firestore) ---
async def get_user_profile(chat_id: str) -> Dict[str, Any]:
    """Obtiene el perfil de un usuario desde PostgreSQL."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT chat_id, user_name, last_message, context FROM user_profiles WHERE chat_id = $1",
            chat_id
        )
        if row:
            return {
                "chat_id": row["chat_id"],
                "user_name": row["user_name"],
                "last_message": row["last_message"],
                "context": row["context"] or {}
            }
        return {}
    finally:
        await conn.close()

async def update_user_profile(chat_id: str, data: Dict[str, Any]):
    """Actualiza o crea el perfil de un usuario en PostgreSQL."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("""
            INSERT INTO user_profiles (chat_id, user_name, last_message, context)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (chat_id) DO UPDATE SET
                user_name = EXCLUDED.user_name,
                last_message = EXCLUDED.last_message,
                context = EXCLUDED.context,
                updated_at = NOW()
        """, chat_id, data.get("user_name"), data.get("last_message"), data.get("context"))
    finally:
        await conn.close()

# --- 5. Nodos del grafo ---
async def classify_intent(state: AgentState) -> Dict[str, Any]:
    messages = state.messages.copy()
    system_prompt = (
        "Eres un asistente de perfumería. Clasifica la intención del usuario en: "
        "'catalog' si quiere ver productos, 'schedule' si quiere agendar cita, "
        "'respond' para otros casos. Si pide ambos, prioriza 'schedule'. "
        "Responde con el siguiente formato: {\"intent\": \"catalog|schedule|respond\"}"
    )
    messages.insert(0, HumanMessage(content=system_prompt))
    
    handler = get_langfuse_handler(user_id=state.chat_id)
    response = await llm.ainvoke(messages, config={"callbacks": [handler]})
    
    content = response.content
    if "catalog" in content.lower():
        next_step = "catalog"
    elif "schedule" in content.lower():
        next_step = "schedule"
    else:
        next_step = "respond"
    
    state.messages.append(AIMessage(content=content))
    return {"next_step": next_step, "messages": state.messages}

async def handle_catalog(state: AgentState) -> Dict[str, Any]:
    result = await show_catalog(state.chat_id)
    await send_text_message(state.chat_id, "Aquí tienes nuestro catálogo. ¿Te gusta algún producto?")
    return {"messages": state.messages + [AIMessage(content=result)]}

async def handle_schedule(state: AgentState) -> Dict[str, Any]:
    await send_text_message(state.chat_id, "Para agendar, por favor dinos tu nombre, correo, fecha (YYYY-MM-DD) y hora (HH:MM).")
    return {"messages": state.messages + [AIMessage(content="Solicitando datos de cita.")]}

async def handle_respond(state: AgentState) -> Dict[str, Any]:
    handler = get_langfuse_handler(user_id=state.chat_id)
    response = await llm.ainvoke(state.messages, config={"callbacks": [handler]})
    await send_text_message(state.chat_id, response.content)
    return {"messages": state.messages + [AIMessage(content=response.content)]}

# --- 6. Construcción del grafo ---
workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_intent)
workflow.add_node("catalog", handle_catalog)
workflow.add_node("schedule", handle_schedule)
workflow.add_node("respond", handle_respond)

workflow.set_entry_point("classify")

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

graph = workflow.compile(checkpointer=checkpointer)

# --- 7. FastAPI Endpoints ---
@app.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    chat_id = data.get("chatId")
    message_text = data.get("body", "")
    sender_name = data.get("senderName", "")
    
    background_tasks.add_task(process_message, chat_id, message_text, sender_name)
    return {"status": "ok"}

async def process_message(chat_id: str, message: str, sender_name: str):
    trace = langfuse_client.trace(
        name="whatsapp-conversation",
        user_id=chat_id,
        metadata={"sender_name": sender_name}
    )
    
    with trace.span(name="langgraph-execution") as span:
        initial_state = AgentState(
            messages=[{"role": "user", "content": message}],
            chat_id=chat_id,
            user_name=sender_name,
        )
        
        config = {"configurable": {"thread_id": chat_id}}
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
        
        # Actualizar perfil en PostgreSQL (reemplaza Firestore)
        await update_user_profile(chat_id, {
            "user_name": sender_name,
            "last_message": message,
            "context": {}  # Puedes guardar más datos aquí
        })
    
    trace.flush()

@app.post("/webhook/calcom")
async def calcom_webhook(request: Request):
    data = await request.json()
    print(f"Booking creado: {data}")
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
