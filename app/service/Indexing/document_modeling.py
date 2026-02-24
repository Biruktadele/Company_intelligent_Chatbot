from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from enum import Enum
from .normalization_and_cleaning import NormalizedDocument
from .documnt_accution import DocumentMetadata

class DocumentStatus(Enum):
    ACQUIRED = "acquired"
    PARSED = "parsed"
    NORMALIZED = "normalized"
    CHUNKED = "chunked"
    EMBEDDED = "embedded"
    INDEXED = "indexed"
    ERROR = "error"

@dataclass
class ProcessedDocument:
    """The central model representing a document throughout the pipeline"""
    doc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_metadata: DocumentMetadata = None
    normalized_content: NormalizedDocument = None
    status: DocumentStatus = DocumentStatus.ACQUIRED
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    processing_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def update_status(self, new_status: DocumentStatus, message: str = ""):
        """Update document status and log history"""
        self.status = new_status
        self.updated_at = datetime.now()
        self.processing_history.append({
            "timestamp": self.updated_at.isoformat(),
            "status": new_status.value,
            "message": message
        })

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary for storage/API"""
        return {
            "doc_id": self.doc_id,
            "filename": self.original_metadata.filename if self.original_metadata else None,
            "status": self.status.value,
            "language": self.normalized_content.detected_language if self.normalized_content else None,
            "quality_score": self.normalized_content.quality_score if self.normalized_content else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

class DocumentRegistry:
    """Manages the collection of processed documents"""
    def __init__(self):
        self.documents: Dict[str, ProcessedDocument] = {}
        
    def register(self, doc: ProcessedDocument):
        self.documents[doc.doc_id] = doc
        
    def get_document(self, doc_id: str) -> Optional[ProcessedDocument]:
        return self.documents.get(doc_id)