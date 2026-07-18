import os
import re
import sys

# Override sqlite3 with pysqlite3 for ChromaDB compatibility on Vercel
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass
import uuid
import json
import logging
import asyncio
from pathlib import Path
from queue import Queue, Empty

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure project root is in python path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import settings

# Serverless environment modifications (must execute before other imports evaluate settings)
if os.environ.get("VERCEL"):
    settings.persist_directory = "/tmp/vector_db"
    settings.repos_dir = "/tmp/repos"

from git_utils.clone_repo import RepoManager
from rag.indexer import RepositoryIndexer
from rag.retriever import CodeRetriever
from agents.planner import PlannerAgent
from agents.reader import ReaderAgent
from agents.writer import WriterAgent
from agents.reviewer import ReviewerAgent
from prompts.reviewer.schema import ReviewState
from prompts.writer.schema import WriterResult


SENSITIVE_PATTERNS = [
    (re.compile(r'(Authorization:\s*Bearer\s+)[a-zA-Z0-9_\-\.]{10,}', re.IGNORECASE), r'\1[REDACTED_BEARER_TOKEN]'),
    (re.compile(r'(api[-_]key\s*[:=]\s*[\'"]?)[a-zA-Z0-9_\-\.]{10,}([\'"]?)', re.IGNORECASE), r'\1[REDACTED_API_KEY]\2'),
    (re.compile(r'(password\s*[:=]\s*[\'"]?)[a-zA-Z0-9_\-\.]{6,}([\'"]?)', re.IGNORECASE), r'\1[REDACTED_PASSWORD]\2'),
]

def redact_sensitive_info(msg: str) -> str:
    redacted_msg = msg
    
    # 1. Environment variable values replacement
    sensitive_env_keys = [
        k for k in os.environ.keys()
        if any(term in k.upper() for term in ["KEY", "TOKEN", "SECRET", "PASS", "AUTH"])
    ]
    for key in sensitive_env_keys:
        value = os.environ.get(key)
        if value and len(value) > 4:
            redacted_msg = redacted_msg.replace(value, f"[{key}_REDACTED]")
            
    # 2. Pattern-based regex replacement
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted_msg = pattern.sub(replacement, redacted_msg)
        
    return redacted_msg

# Custom log handler to collect logs for active SSE sessions
class SessionLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.queues = {}  # session_id -> Queue

    def emit(self, record):
        msg = self.format(record)
        msg = redact_sensitive_info(msg)
        for q in self.queues.values():
            q.put(msg)

session_log_handler = SessionLogHandler()
session_log_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logging.getLogger().addHandler(session_log_handler)
logging.getLogger().setLevel(logging.INFO)

# Initialize FastAPI
app = FastAPI(title="AutoPR-AI API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class IndexRequest(BaseModel):
    repo_url: str
    collection_name: str

class RunRequest(BaseModel):
    collection_name: str
    request: str

PROVIDER_ENV_MAP = {
    "mistralai": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GEMINI_API_KEY",
    "google-genai": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY"
}

def update_env_file(key_name: str, value: str):
    env_path = Path(project_root) / ".env"
    lines = []
    key_exists = False
    
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key_name}="):
            lines[i] = f"{key_name}={value}"
            key_exists = True
            break
            
    if not key_exists:
        lines.append(f"{key_name}={value}")
        
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key_name] = value

class ConfigUpdate(BaseModel):
    model_name: str
    model_provider: str
    api_key: str | None = None
    embedding_model_name: str
    chunk_size: int
    chunk_overlap: int
    default_top_k: int
    default_fetch_k: int
    default_score_threshold: float
    max_context_chars: int
    max_review_cycles: int

@app.get("/api/config")
def get_config():
    provider = settings.model_provider.lower()
    env_var = PROVIDER_ENV_MAP.get(provider, "MISTRAL_API_KEY")
    has_api_key = bool(os.environ.get(env_var))
    
    return {
        "model_name": settings.model_name,
        "model_provider": settings.model_provider,
        "has_api_key": has_api_key,
        "embedding_model_name": settings.embedding_model_name,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "default_top_k": settings.default_top_k,
        "default_fetch_k": settings.default_fetch_k,
        "default_score_threshold": settings.default_score_threshold,
        "max_context_chars": settings.max_context_chars,
        "max_review_cycles": settings.max_review_cycles
    }

@app.post("/api/config")
def update_config(cfg: ConfigUpdate):
    settings.model_name = cfg.model_name
    settings.model_provider = cfg.model_provider
    settings.embedding_model_name = cfg.embedding_model_name
    settings.chunk_size = cfg.chunk_size
    settings.chunk_overlap = cfg.chunk_overlap
    settings.default_top_k = cfg.default_top_k
    settings.default_fetch_k = cfg.default_fetch_k
    settings.default_score_threshold = cfg.default_score_threshold
    settings.max_context_chars = cfg.max_context_chars
    settings.max_review_cycles = cfg.max_review_cycles
    
    # Save custom API Key locally to .env if provided and not masked
    if cfg.api_key and cfg.api_key != "••••••••••••":
        provider = cfg.model_provider.lower()
        env_var = PROVIDER_ENV_MAP.get(provider, "MISTRAL_API_KEY")
        logging.info(f"Saving custom API Key locally in .env for provider '{provider}' ({env_var})")
        update_env_file(env_var, cfg.api_key)
        
    logging.info("System configuration settings updated successfully.")
    return {"status": "success"}


def get_collections_list():
    db_path = Path(settings.persist_directory)
    if not db_path.exists():
        return []
    collections = []
    for f in db_path.glob("*_manifest.json"):
        name = f.name.replace("_manifest.json", "")
        collections.append(name)
    return collections

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "persist_directory": settings.persist_directory,
        "collections": get_collections_list()
    }

@app.get("/api/collections")
def list_collections():
    return {"collections": get_collections_list()}

def run_indexing_task(session_id: str, repo_url: str, collection_name: str):
    try:
        logging.info(f"Indexing repository: {repo_url} under collection: {collection_name}")
        indexer = RepositoryIndexer(repo_url=repo_url, collection_name=collection_name)
        indexer.index()
        logging.info("Indexing process completed successfully.")
        
        queue = session_log_handler.queues.get(session_id)
        if queue:
            result = {"type": "result", "status": "completed", "collection_name": collection_name}
            queue.put(f"[RESULT] {json.dumps(result)}")
    except Exception as e:
        logging.exception("Failed to index repository")
        queue = session_log_handler.queues.get(session_id)
        if queue:
            error_res = {"type": "error", "message": str(e)}
            queue.put(f"[ERROR] {json.dumps(error_res)}")

def run_agents_task(session_id: str, collection_name: str, request_text: str):
    try:
        logging.info(f"Executing agent workflow. Collection: {collection_name}. Task: {request_text}")
        
        # 1. Paths
        repo_root = Path(settings.repos_dir) / collection_name
        
        # 2. Retriever and Agents
        retriever = CodeRetriever(collection_name=collection_name)
        planner = PlannerAgent(model=settings.model_name, model_provider=settings.model_provider)
        reader = ReaderAgent(retriever, model=settings.model_name, model_provider=settings.model_provider)
        writer = WriterAgent(model=settings.model_name, model_provider=settings.model_provider)
        reviewer = ReviewerAgent(repo_root=repo_root, model=settings.model_name, model_provider=settings.model_provider)
        
        # 3. Plan
        logging.info("Running Planner Agent...")
        plan = planner.plan(request_text)
        logging.info(f"Generated Execution Plan: Goal='{plan.goal}', Next Agent='{plan.next_agent}'")
        queue = session_log_handler.queues.get(session_id)
        if queue:
            queue.put(f"[STEP] {json.dumps({'step': 'planner', 'data': plan.model_dump()})}")
        
        # 4. Read
        logging.info("Running Reader Agent...")
        reader_result, repository_context = reader.read(plan)
        logging.info(f"Reader completed codebase search: found {len(reader_result.relevant_files)} relevant files.")
        if queue:
            queue.put(f"[STEP] {json.dumps({'step': 'reader', 'data': reader_result.model_dump()})}")
        
        # 5. Initial write
        logging.info("Running Writer Agent (initial draft)...")
        writer_result = writer.write(
            plan=plan,
            reader_result=reader_result,
            repository_context=repository_context
        )
        logging.info("Initial patch drafted successfully.")
        if queue:
            queue.put(f"[STEP] {json.dumps({'step': 'writer', 'data': writer_result.model_dump()})}")
        
        # 6. Review Loop
        review_state = ReviewState()
        approved = False
        final_writer_result = writer_result
        
        for cycle in range(1, settings.max_review_cycles + 1):
            logging.info(f"Running Reviewer Agent (cycle {cycle}/{settings.max_review_cycles})...")
            review_result = reviewer.review(
                plan=plan,
                reader_result=reader_result,
                writer_result=final_writer_result,
                review_state=review_state
            )
            
            if queue:
                queue.put(f"[STEP] {json.dumps({'step': 'reviewer', 'cycle': cycle, 'data': review_result.model_dump()})}")
                
            if review_result.approved:
                logging.info(f"Review approved after {cycle} cycle(s).")
                approved = True
                break
                
            if cycle == settings.max_review_cycles:
                logging.warning("Max review cycles reached. Approving code changes as-is.")
                break
                
            logging.info(f"Review failed. {len(review_result.issues)} issues raised. Initiating Writer revision...")
            
            final_writer_result = writer.revise(
                plan=plan,
                reader_result=reader_result,
                repository_context=repository_context,
                previous_result=final_writer_result,
                review_feedback=review_result
            )
            
            if queue:
                queue.put(f"[STEP] {json.dumps({'step': 'revision', 'cycle': cycle, 'data': final_writer_result.model_dump()})}")
                
            review_state.cycle = cycle
            review_state.unresolved_issues = review_result.issues
            
        # 7. Dispatch result
        result_payload = {
            "status": "completed" if approved else "failed_review",
            "approved": approved,
            "plan": plan.model_dump(),
            "patch": final_writer_result.model_dump()
        }
        
        queue = session_log_handler.queues.get(session_id)
        if queue:
            queue.put(f"[RESULT] {json.dumps(result_payload)}")
            
    except Exception as e:
        logging.exception("Agent process failed")
        queue = session_log_handler.queues.get(session_id)
        if queue:
            error_res = {"type": "error", "message": str(e)}
            queue.put(f"[ERROR] {json.dumps(error_res)}")

@app.post("/api/index")
def index_repository(req: IndexRequest, background_tasks: BackgroundTasks):
    session_id = str(uuid.uuid4())
    session_log_handler.queues[session_id] = Queue()
    background_tasks.add_task(run_indexing_task, session_id, req.repo_url, req.collection_name)
    return {"session_id": session_id}

@app.post("/api/run")
def run_agent_loop(req: RunRequest, background_tasks: BackgroundTasks):
    session_id = str(uuid.uuid4())
    session_log_handler.queues[session_id] = Queue()
    background_tasks.add_task(run_agents_task, session_id, req.collection_name, req.request)
    return {"session_id": session_id}

@app.get("/api/stream/{session_id}")
async def stream_session_logs(session_id: str):
    if session_id not in session_log_handler.queues:
        raise HTTPException(status_code=404, detail="Session not found")
        
    queue = session_log_handler.queues[session_id]
    
    async def sse_generator():
        try:
            while True:
                try:
                    log_msg = queue.get_nowait()
                    if log_msg.startswith("[RESULT] "):
                        payload = json.loads(log_msg[9:])
                        yield f"data: {json.dumps({'type': 'result', 'payload': payload})}\n\n"
                        break
                    elif log_msg.startswith("[ERROR] "):
                        payload = json.loads(log_msg[8:])
                        yield f"data: {json.dumps({'type': 'error', 'message': payload['message']})}\n\n"
                        break
                    elif log_msg.startswith("[STEP] "):
                        payload = json.loads(log_msg[7:])
                        yield f"data: {json.dumps({'type': 'step', 'step': payload['step'], 'data': payload.get('data'), 'cycle': payload.get('cycle')})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'log', 'message': log_msg})}\n\n"
                except Empty:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            session_log_handler.queues.pop(session_id, None)
            
    return StreamingResponse(sse_generator(), media_type="text/event-stream")

# Mount static files at the root
public_dir = Path(project_root) / "public"
if public_dir.exists():
    app.mount("/", StaticFiles(directory=str(public_dir), html=True), name="public")

