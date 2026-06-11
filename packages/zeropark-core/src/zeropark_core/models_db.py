import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True) # Nullable for OAuth users
    full_name = Column(String, nullable=True)
    provider = Column(String, default="local") # e.g., 'local', 'google'
    provider_id = Column(String, nullable=True, index=True) # e.g., google user ID
    role = Column(String, default="user")  # 'admin', 'user'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    workspaces = relationship("Workspace", back_populates="owner")

class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="workspaces")
    chat_sessions = relationship("ChatSession", back_populates="workspace")
    workflows = relationship("Workflow", back_populates="workspace")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(String, primary_key=True, default=generate_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    workspace = relationship("Workspace", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False) # 'user', 'assistant', 'system'
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("ChatSession", back_populates="messages")

class App(Base):
    """A configured agent app — created/published by admins, used by everyone.

    This is the server-side registry that replaces per-browser localStorage:
    an admin builds an agent (name + mode + optional system prompt/params),
    publishes it, and every user in the deployment sees and uses it.
    """
    __tablename__ = "apps"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    mode = Column(String, nullable=False)            # router mode (chat, slides, ...)
    system_prompt = Column(String, nullable=True)    # optional persona/instructions
    params = Column(String, nullable=True)           # JSON: default task params
    published = Column(Boolean, default=True)        # only published apps show to users
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RagCollection(Base):
    """A logical knowledge collection with role-based read access.

    Vectors live in one physical Qdrant collection; every chunk is tagged with
    collection_id and queries filter on the collections the caller may read.
    """
    __tablename__ = "rag_collections"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    # JSON list of roles allowed to READ, e.g. ["user","admin"] or ["admin"]
    allowed_roles = Column(String, default='["user", "admin"]')
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Job(Base):
    """A long-running agent task, persisted so it survives reconnects/restarts."""
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=True, index=True)
    mode = Column(String, nullable=False)
    prompt = Column(String, nullable=False)
    params = Column(String, nullable=True)   # JSON string
    status = Column(String, default="pending", index=True)  # pending/running/succeeded/failed/cancelled
    result = Column(String, nullable=True)   # JSON string of the TaskResult
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WorkflowRun(Base):
    """One execution of a workflow, with its per-node log — run observability."""
    __tablename__ = "workflow_runs"
    id = Column(String, primary_key=True, default=generate_uuid)
    workflow_name = Column(String, nullable=True)
    user_id = Column(String, nullable=True, index=True)
    status = Column(String, default="running", index=True)
    node_runs = Column(String, nullable=True)  # JSON list of NodeRun
    duration_ms = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Workflow(Base):
    __tablename__ = "workflows"
    id = Column(String, primary_key=True, default=generate_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    workspace = relationship("Workspace", back_populates="workflows")
    nodes = relationship("Node", back_populates="workflow", cascade="all, delete-orphan")
    edges = relationship("Edge", back_populates="workflow", cascade="all, delete-orphan")

class Node(Base):
    __tablename__ = "nodes"
    id = Column(String, primary_key=True, default=generate_uuid)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    type = Column(String, nullable=False) # 'llm', 'search', 'crawl', etc.
    label = Column(String, nullable=False)
    position_x = Column(String, nullable=True) # Stored as string for flexibility
    position_y = Column(String, nullable=True)
    data = Column(String, nullable=True) # JSON string of properties
    
    workflow = relationship("Workflow", back_populates="nodes")

class Edge(Base):
    __tablename__ = "edges"
    id = Column(String, primary_key=True, default=generate_uuid)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    source_node_id = Column(String, ForeignKey("nodes.id"), nullable=False)
    target_node_id = Column(String, ForeignKey("nodes.id"), nullable=False)
    
    workflow = relationship("Workflow", back_populates="edges")

class PromptTemplate(Base):
    """Container for prompt versions."""
    __tablename__ = "prompt_templates"
    id = Column(String, primary_key=True, default=generate_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    versions = relationship("PromptVersion", back_populates="template", cascade="all, delete-orphan")

class PromptVersion(Base):
    """A specific immutable version of a prompt."""
    __tablename__ = "prompt_versions"
    id = Column(String, primary_key=True, default=generate_uuid)
    template_id = Column(String, ForeignKey("prompt_templates.id"), nullable=False)
    version_tag = Column(String, nullable=False) # e.g. 'v1', 'v2'
    content = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    template = relationship("PromptTemplate", back_populates="versions")

class Dataset(Base):
    """Knowledge base dataset for RAG."""
    __tablename__ = "datasets"
    id = Column(String, primary_key=True, default=generate_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    documents = relationship("Document", back_populates="dataset", cascade="all, delete-orphan")

class Document(Base):
    """A file or text uploaded to a dataset."""
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=generate_uuid)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    filename = Column(String, nullable=False)
    status = Column(String, default="pending") # pending, processing, completed, error
    word_count = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    dataset = relationship("Dataset", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

class DocumentChunk(Base):
    """A single embedded chunk of a document."""
    __tablename__ = "document_chunks"
    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    content = Column(String, nullable=False)
    vector_id = Column(String, nullable=True) # ID in Qdrant
    created_at = Column(DateTime, default=datetime.utcnow)
    
    document = relationship("Document", back_populates="chunks")
