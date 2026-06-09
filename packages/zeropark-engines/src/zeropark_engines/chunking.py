import re
from typing import List

class RecursiveCharacterTextSplitter:
    """A simple text splitter that recursively splits by a list of characters."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: List[str] = None
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> List[str]:
        final_chunks = []
        separator = self._separators[-1]
        new_separators = []
        for i, _s in enumerate(self._separators):
            if _s == "":
                separator = _s
                break
            if re.search(_s, text):
                separator = _s
                new_separators = self._separators[i + 1:]
                break

        _splits = self._split_text_with_regex(text, separator)
        
        good_splits = []
        for s in _splits:
            if len(s) < self._chunk_size:
                good_splits.append(s)
            else:
                if new_separators:
                    other_info = self.split_text(s)
                    good_splits.extend(other_info)
                else:
                    good_splits.append(s)

        current_doc = []
        total_len = 0
        for doc in good_splits:
            if total_len + len(doc) > self._chunk_size and current_doc:
                chunk = separator.join(current_doc)
                final_chunks.append(chunk)
                
                # Apply overlap by keeping last items from current_doc
                overlap_len = 0
                overlap_docs = []
                for d in reversed(current_doc):
                    if overlap_len + len(d) > self._chunk_overlap:
                        break
                    overlap_docs.insert(0, d)
                    overlap_len += len(d)
                
                current_doc = overlap_docs
                total_len = overlap_len

            current_doc.append(doc)
            total_len += len(doc)
            
        if current_doc:
            chunk = separator.join(current_doc)
            final_chunks.append(chunk)

        return [c.strip() for c in final_chunks if c.strip()]

    def _split_text_with_regex(self, text: str, separator: str) -> List[str]:
        if separator:
            return text.split(separator)
        return list(text)
