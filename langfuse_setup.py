import os
from langfuse import Langfuse
from langfuse.callback import CallbackHandler

# Variables de entorno
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

# Inicializar cliente para uso general (ej. scoring, creación manual)
langfuse_client = Langfuse(
    public_key=LANGFUSE_PUBLIC_KEY,
    secret_key=LANGFUSE_SECRET_KEY,
    host=LANGFUSE_HOST
)

# Handler para LangChain/LangGraph (se pasa a invoke)
langfuse_handler = CallbackHandler(
    public_key=LANGFUSE_PUBLIC_KEY,
    secret_key=LANGFUSE_SECRET_KEY,
    host=LANGFUSE_HOST
)

# Función para obtener el handler con metadatos específicos (usuario, sesión)
def get_langfuse_handler(user_id: str, session_id: str = None):
    """
    Retorna un CallbackHandler con metadatos enriquecidos.
    """
    metadata = {
        "user_id": user_id,
        "session_id": session_id or user_id,
        "environment": os.getenv("ENV", "production")
    }
    return CallbackHandler(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
        metadata=metadata
    )
