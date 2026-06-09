from __future__ import annotations

import os
from abc import ABC, abstractmethod


class ArtifactStore(ABC):
    """Abstract interface for storing artifacts.
    
    This decouples engines from knowing where files actually go
    (e.g., local disk, AWS S3, GCS, DB).
    """

    @abstractmethod
    def save(self, filename: str, content: bytes | str) -> str:
        """Saves the content and returns a URI string referencing the artifact."""
        pass


class LocalArtifactStore(ArtifactStore):
    """Stores artifacts to a local directory."""

    def __init__(self, base_dir: str = "artifacts") -> None:
        self.base_dir = base_dir
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)

    def save(self, filename: str, content: bytes | str) -> str:
        filepath = os.path.join(self.base_dir, filename)
        
        # Determine mode
        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"
        
        with open(filepath, mode, encoding=encoding) as f:
            f.write(content)
            
        # For local, the URI can just be the absolute path or a local http structure if served.
        # Returning absolute filepath.
        return os.path.abspath(filepath)
