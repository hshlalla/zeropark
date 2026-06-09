from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.orm import Session
from .models_db import Base, User, Workspace, ChatSession, ChatMessage, Workflow, Node, Edge

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: dict) -> ModelType:
        db_obj = self.model(**obj_in)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: ModelType, obj_in: dict) -> ModelType:
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: Any) -> ModelType:
        obj = db.query(self.model).get(id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj

class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(self.model).filter(self.model.email == email).first()

from .cache import redis_cache

class ChatRepository(BaseRepository[ChatSession]):
    def __init__(self):
        super().__init__(ChatSession)

    def get_messages(self, db: Session, session_id: str) -> List[ChatMessage]:
        cache_key = f"chat_messages:{session_id}"
        
        # 1. Try Cache
        cached_data = redis_cache.get(cache_key)
        if cached_data:
            # Reconstruct model objects from cached dicts (or just return dicts depending on usage)
            return [ChatMessage(**msg) for msg in cached_data]
            
        # 2. Cache Miss -> Query DB
        messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
        
        # 3. Save to Cache
        if messages:
            msg_dicts = [{"id": m.id, "session_id": m.session_id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in messages]
            redis_cache.set(cache_key, msg_dicts, ttl_seconds=86400) # 24 hours TTL
            
        return messages

    def add_message(self, db: Session, session_id: str, role: str, content: str) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, role=role, content=content)
        db.add(msg)
        db.commit()
        db.refresh(msg)
        
        # Invalidate cache so next read fetches fresh data
        redis_cache.delete(f"chat_messages:{session_id}")
        
        return msg

class WorkflowRepository(BaseRepository[Workflow]):
    def __init__(self):
        super().__init__(Workflow)

    def get_full_workflow(self, db: Session, workflow_id: str) -> Optional[Workflow]:
        # Utilizing SQLAlchemy relationships to eager load nodes and edges could be added here
        return self.get(db, workflow_id)

user_repo = UserRepository()
chat_repo = ChatRepository()
workflow_repo = WorkflowRepository()
