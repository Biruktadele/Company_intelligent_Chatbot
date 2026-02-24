import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

class ContentType(Enum):
    """Types of content elements in documents"""
    TITLE = "title"
    HEADING = "heading"
    SUBHEADING = "subheading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    CODE_BLOCK = "code_block"
    QUOTE = "quote"
    METADATA = "metadata"
    UNKNOWN = "unknown"

@dataclass
class DocumentElement:
    """Represents a structural element in a document"""
    content: str
    element_type: ContentType
    level: int  # Hierarchy level (1 for main title, 2 for headings, etc.)
    position: int  # Position in document
    metadata: Dict[str, Any]
    parent_id: Optional[str] = None
    children_ids: List[str] = None
    
    def __post_init__(self):
        if self.children_ids is None:
            self.children_ids = []

@dataclass
class DocumentStructure:
    """Represents the complete structure of a document"""
    elements: List[DocumentElement]
    hierarchy: Dict[str, List[str]]  # parent_id -> [child_ids]
    metadata: Dict[str, Any]
    table_of_contents: List[Dict[str, Any]]
    
class DocumentParser:
    """Handles parsing and structural extraction from documents"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        
        # Patterns for different content types
        self.heading_patterns = {
            'markdown': [
                (r'^#{1,6}\s+(.+)$', lambda m: len(m.group(1).split()[0])),  # # Heading
                (r'^([A-Z][^.]*\.)$', lambda m: 1),  # Uppercase ending with period
            ],
            'general': [
                (r'^[A-Z][A-Z\s]{10,}$', lambda m: 1),  # ALL CAPS titles
                (r'^\d+\.\s+[A-Z]', lambda m: 2),  # Numbered sections
                (r'^[A-Z][a-z\s]+:$', lambda m: 2),  # Capitalized with colon
            ]
        }
        
        self.list_patterns = [
            r'^[\s]*[-•*]\s+(.+)$',  # Bullet points
            r'^[\s]*\d+\.\s+(.+)$',  # Numbered lists
            r'^[\s]*[a-zA-Z]\.\s+(.+)$',  # Letter lists
        ]
        
        self.table_patterns = [
            r'\|.*\|',  # Markdown tables
            r'^\s*\+[-+\s]+\+\s*$',  # ASCII table borders
        ]
        
        self.code_patterns = [
            r'^```[\w]*\n.*?\n```$',  # Code blocks
            r'^\s{4,}.*$',  # Indented code
        ]
    
    def parse_document(self, content: str, file_type: str = "unknown") -> DocumentStructure:
        """Parse document content and extract structure"""
        if not content or not content.strip():
            return DocumentStructure([], {}, {}, [])
        
        # Split content into lines
        lines = content.split('\n')
        
        # Detect document format
        doc_format = self._detect_format(content, file_type)
        
        # Parse elements
        elements = self._parse_elements(lines, doc_format)
        
        # Build hierarchy
        hierarchy = self._build_hierarchy(elements)
        
        # Extract metadata
        metadata = self._extract_metadata(elements, content)
        
        # Generate table of contents
        toc = self._generate_table_of_contents(elements)
        
        return DocumentStructure(
            elements=elements,
            hierarchy=hierarchy,
            metadata=metadata,
            table_of_contents=toc
        )
    
    def _detect_format(self, content: str, file_type: str) -> str:
        """Detect document format (markdown, plain_text, etc.)"""
        if file_type == 'md':
            return 'markdown'
        
        # Check for markdown patterns
        if re.search(r'^#{1,6}\s+', content, re.MULTILINE):
            return 'markdown'
        
        if re.search(r'\|.*\|', content):
            return 'markdown'
        
        return 'plain_text'
    
    def _parse_elements(self, lines: List[str], doc_format: str) -> List[DocumentElement]:
        """Parse individual elements from lines"""
        elements = []
        position = 0
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Try to identify element type
            element_type, level, content_lines, consumed = self._identify_element(
                lines, i, doc_format
            )
            
            if element_type != ContentType.UNKNOWN:
                element = DocumentElement(
                    content='\n'.join(content_lines),
                    element_type=element_type,
                    level=level,
                    position=position,
                    metadata={'line_start': i, 'line_end': i + consumed - 1}
                )
                elements.append(element)
                position += 1
                i += consumed
            else:
                # Treat as paragraph
                paragraph_lines = self._extract_paragraph(lines, i)
                element = DocumentElement(
                    content='\n'.join(paragraph_lines),
                    element_type=ContentType.PARAGRAPH,
                    level=0,
                    position=position,
                    metadata={'line_start': i, 'line_end': i + len(paragraph_lines) - 1}
                )
                elements.append(element)
                position += 1
                i += len(paragraph_lines)
        
        return elements
    
    def _identify_element(self, lines: List[str], start_idx: int, doc_format: str) -> Tuple[ContentType, int, List[str], int]:
        """Identify the type and extract content of an element"""
        line = lines[start_idx].strip()
        
        # Check headings
        for pattern, level_func in self.heading_patterns.get(doc_format, []):
            match = re.match(pattern, line)
            if match:
                return ContentType.HEADING, level_func(match), [line], 1
        
        # Check for general heading patterns
        for pattern, level_func in self.heading_patterns['general']:
            match = re.match(pattern, line)
            if match:
                return ContentType.HEADING, level_func(match), [line], 1
        
        # Check lists
        for pattern in self.list_patterns:
            match = re.match(pattern, line)
            if match:
                return ContentType.LIST_ITEM, 1, [line], 1
        
        # Check tables
        for pattern in self.table_patterns:
            if re.match(pattern, line):
                table_lines = self._extract_table(lines, start_idx)
                return ContentType.TABLE, 1, table_lines, len(table_lines)
        
        # Check code blocks
        for pattern in self.code_patterns:
            if re.match(pattern, line):
                code_lines = self._extract_code_block(lines, start_idx)
                return ContentType.CODE_BLOCK, 1, code_lines, len(code_lines)
        
        return ContentType.UNKNOWN, 0, [], 0
    
    def _extract_paragraph(self, lines: List[str], start_idx: int) -> List[str]:
        """Extract a paragraph (consecutive non-empty lines)"""
        paragraph_lines = []
        i = start_idx
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                break
            
            # Stop if we hit a structured element
            if self._is_structured_line(line):
                break
            
            paragraph_lines.append(line)
            i += 1
        
        return paragraph_lines
    
    def _extract_table(self, lines: List[str], start_idx: int) -> List[str]:
        """Extract a complete table"""
        table_lines = []
        i = start_idx
        
        while i < len(lines):
            line = lines[i]
            table_lines.append(line)
            i += 1
            
            # Stop at empty line or non-table content
            if i < len(lines) and not lines[i].strip():
                break
            
            # Stop if pattern clearly breaks
            if i < len(lines) and not re.match(r'^[\s|\|+-]', lines[i]):
                break
        
        return table_lines
    
    def _extract_code_block(self, lines: List[str], start_idx: int) -> List[str]:
        """Extract a code block"""
        code_lines = []
        i = start_idx
        line = lines[i].strip()
        
        # Handle fenced code blocks
        if line.startswith('```'):
            code_lines.append(line)
            i += 1
            
            # Find closing fence
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            
            if i < len(lines):
                code_lines.append(lines[i])
                i += 1
        else:
            # Handle indented code
            while i < len(lines) and lines[i].startswith('    '):
                code_lines.append(lines[i])
                i += 1
        
        return code_lines
    
    def _is_structured_line(self, line: str) -> bool:
        """Check if a line represents a structured element"""
        line = line.strip()
        
        # Check headings
        if re.match(r'^#{1,6}\s+', line):
            return True
        
        # Check lists
        for pattern in self.list_patterns:
            if re.match(pattern, line):
                return True
        
        # Check tables
        for pattern in self.table_patterns:
            if re.match(pattern, line):
                return True
        
        return False
    
    def _build_hierarchy(self, elements: List[DocumentElement]) -> Dict[str, List[str]]:
        """Build hierarchical relationships between elements"""
        hierarchy = {}
        parent_stack = []  # Stack of (element_id, level)
        
        for element in elements:
            element_id = f"element_{element.position}"
            
            # Find parent based on level
            while parent_stack and parent_stack[-1][1] >= element.level:
                parent_stack.pop()
            
            if parent_stack:
                parent_id = parent_stack[-1][0]
                element.parent_id = parent_id
                
                if parent_id not in hierarchy:
                    hierarchy[parent_id] = []
                hierarchy[parent_id].append(element_id)
            
            # Add to stack if it's a heading
            if element.element_type in [ContentType.TITLE, ContentType.HEADING]:
                parent_stack.append((element_id, element.level))
        
        return hierarchy
    
    def _extract_metadata(self, elements: List[DocumentElement], full_content: str) -> Dict[str, Any]:
        """Extract document metadata"""
        metadata = {
            'total_elements': len(elements),
            'element_types': {},
            'word_count': len(full_content.split()),
            'char_count': len(full_content),
            'line_count': len(full_content.split('\n'))
        }
        
        # Count element types
        for element in elements:
            element_type = element.element_type.value
            metadata['element_types'][element_type] = metadata['element_types'].get(element_type, 0) + 1
        
        # Extract title (first heading or title)
        for element in elements:
            if element.element_type in [ContentType.TITLE, ContentType.HEADING]:
                if element.level == 1:
                    metadata['title'] = element.content
                    break
        
        return metadata
    
    def _generate_table_of_contents(self, elements: List[DocumentElement]) -> List[Dict[str, Any]]:
        """Generate table of contents from headings"""
        toc = []
        
        for element in elements:
            if element.element_type in [ContentType.TITLE, ContentType.HEADING]:
                toc.append({
                    'title': element.content,
                    'level': element.level,
                    'position': element.position,
                    'element_id': f"element_{element.position}"
                })
        
        return toc
    
    def get_element_by_id(self, structure: DocumentStructure, element_id: str) -> Optional[DocumentElement]:
        """Get element by ID"""
        for element in structure.elements:
            if f"element_{element.position}" == element_id:
                return element
        return None
    
    def get_elements_by_type(self, structure: DocumentStructure, element_type: ContentType) -> List[DocumentElement]:
        """Get all elements of a specific type"""
        return [elem for elem in structure.elements if elem.element_type == element_type]
    
    def get_content_summary(self, structure: DocumentStructure) -> str:
        """Generate a summary of document structure"""
        summary_parts = []
        
        if structure.metadata.get('title'):
            summary_parts.append(f"Title: {structure.metadata['title']}")
        
        summary_parts.append(f"Elements: {structure.metadata['total_elements']}")
        summary_parts.append(f"Words: {structure.metadata['word_count']}")
        
        if structure.table_of_contents:
            summary_parts.append(f"Sections: {len(structure.table_of_contents)}")
        
        return " | ".join(summary_parts)