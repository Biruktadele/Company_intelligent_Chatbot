import re
import unicodedata
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from langdetect import detect, LangDetectException
from .document_paresing_and_extracting_structuerd import DocumentStructure, DocumentElement, ContentType

class CleaningLevel(Enum):
    """Levels of cleaning intensity"""
    MINIMAL = "minimal"  # Basic whitespace and unicode fixes
    STANDARD = "standard"  # Include header/footer removal
    AGGRESSIVE = "aggressive"  # Include pattern-based content filtering

@dataclass
class CleaningStats:
    """Statistics about cleaning operations"""
    original_chars: int = 0
    cleaned_chars: int = 0
    headers_removed: int = 0
    footers_removed: int = 0
    unicode_fixed: int = 0
    whitespace_normalized: int = 0
    line_breaks_fixed: int = 0
    invisible_chars_removed: int = 0
    language_detected: str = "unknown"
    
    def get_reduction_percentage(self) -> float:
        """Calculate percentage of content reduction"""
        if self.original_chars == 0:
            return 0.0
        return ((self.original_chars - self.cleaned_chars) / self.original_chars) * 100

@dataclass
class NormalizedDocument:
    """Represents a cleaned and normalized document"""
    original_structure: DocumentStructure
    cleaned_elements: List[DocumentElement]
    cleaning_stats: CleaningStats
    detected_language: str
    quality_score: float  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

class DocumentNormalizer:
    """Handles normalization and cleaning of document content"""
    
    def __init__(self, cleaning_level: CleaningLevel = CleaningLevel.STANDARD, 
                 logger: Optional[logging.Logger] = None):
        self.cleaning_level = cleaning_level
        self.logger = logger or logging.getLogger(__name__)
        
        # Common header/footer patterns
        self.header_patterns = [
            r'^.{0,50}?(?:page|p\.)\s*\d+$',  # Page numbers
            r'^.{0,30}?(?:confidential|draft|internal)',  # Confidential markers
            r'^.{0,30}?\d{1,2}/\d{1,2}/\d{2,4}',  # Dates
            r'^.{0,30}?(?:chapter|ch\.|section)\s+\d+',  # Chapter/section numbers
        ]
        
        self.footer_patterns = [
            r'.{0,50}?(?:page|p\.)\s*\d+$',  # Page numbers at bottom
            r'.{0,30}?\d{1,2}/\d{1,2}/\d{2,4}',  # Dates
            r'.{0,30}?(?:copyright|©|all rights reserved)',  # Copyright
        ]
        
        # Invisible and problematic characters
        self.invisible_chars = [
            '\u200b',  # Zero-width space
            '\u200c',  # Zero-width non-joiner
            '\u200d',  # Zero-width joiner
            '\u2060',  # Word joiner
            '\uFEFF',  # Byte order mark
            '\u00A0',  # Non-breaking space
            '\u3000',  # Ideographic space
        ]
        
        # Language-specific patterns
        self.language_patterns = {
            'en': r'[a-zA-Z\s.,!?;:\'"()-]+',
            'am': r'[\u1200-\u137F\s.,!?;:\'"()-]+',  # Amharic
            'ar': r'[\u0600-\u06FF\s.,!?;:\'"()-]+',  # Arabic
            'zh': r'[\u4e00-\u9fff\s.,!?;:\'"()-]+',  # Chinese
        }
    
    def normalize_document(self, structure: DocumentStructure) -> NormalizedDocument:
        """Normalize and clean a complete document structure"""
        stats = CleaningStats()
        stats.original_chars = sum(len(elem.content) for elem in structure.elements)
        
        cleaned_elements = []
        detected_languages = []
        
        for element in structure.elements:
            cleaned_element = self._clean_element(element, stats)
            if cleaned_element and cleaned_element.content.strip():
                # Detect language for content
                if len(cleaned_element.content.strip()) > 50:  # Only detect for substantial content
                    try:
                        lang = detect(cleaned_element.content)
                        detected_languages.append(lang)
                    except LangDetectException:
                        pass
                
                cleaned_elements.append(cleaned_element)
        
        # Determine overall language
        final_language = self._determine_language(detected_languages)
        stats.language_detected = final_language
        
        # Calculate quality score
        quality_score = self._calculate_quality_score(cleaned_elements, stats)
        
        # Update stats
        stats.cleaned_chars = sum(len(elem.content) for elem in cleaned_elements)
        
        return NormalizedDocument(
            original_structure=structure,
            cleaned_elements=cleaned_elements,
            cleaning_stats=stats,
            detected_language=final_language,
            quality_score=quality_score,
            metadata={
                'cleaning_level': self.cleaning_level.value,
                'elements_processed': len(structure.elements),
                'elements_kept': len(cleaned_elements)
            }
        )
    
    def _clean_element(self, element: DocumentElement, stats: CleaningStats) -> Optional[DocumentElement]:
        """Clean a single document element"""
        content = element.content
        
        # Skip empty elements
        if not content or not content.strip():
            return None
        
        # Apply cleaning steps based on level
        if self.cleaning_level in [CleaningLevel.STANDARD, CleaningLevel.AGGRESSIVE]:
            content = self._remove_headers_footers(content, stats)
        
        # Always apply these basic cleanings
        content = self._normalize_unicode(content, stats)
        content = self._remove_invisible_characters(content, stats)
        content = self._fix_line_breaks(content, stats)
        content = self._standardize_whitespace(content, stats)
        
        # Aggressive cleaning
        if self.cleaning_level == CleaningLevel.AGGRESSIVE:
            content = self._remove_redundant_content(content, stats)
        
        # Create cleaned element
        cleaned_element = DocumentElement(
            content=content,
            element_type=element.element_type,
            level=element.level,
            position=element.position,
            metadata={**element.metadata, 'cleaned': True}
        )
        
        return cleaned_element
    
    def _remove_headers_footers(self, content: str, stats: CleaningStats) -> str:
        """Remove common header and footer patterns"""
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            removed = False
            
            # Check header patterns (usually at top)
            for pattern in self.header_patterns:
                if re.match(pattern, line_stripped, re.IGNORECASE):
                    stats.headers_removed += 1
                    removed = True
                    break
            
            # Check footer patterns (usually at bottom)
            if not removed:
                for pattern in self.footer_patterns:
                    if re.search(pattern, line_stripped, re.IGNORECASE):
                        stats.footers_removed += 1
                        removed = True
                        break
            
            if not removed:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _normalize_unicode(self, content: str, stats: CleaningStats) -> str:
        """Normalize unicode characters"""
        try:
            # Normalize to NFC form (canonical decomposition + composition)
            normalized = unicodedata.normalize('NFC', content)
            
            if normalized != content:
                stats.unicode_fixed += 1
            
            return normalized
        except Exception as e:
            self.logger.warning(f"Unicode normalization failed: {str(e)}")
            return content
    
    def _remove_invisible_characters(self, content: str, stats: CleaningStats) -> str:
        """Remove invisible and problematic characters"""
        original_length = len(content)
        
        # Remove invisible characters
        for char in self.invisible_chars:
            content = content.replace(char, '')
        
        # Remove control characters except newlines and tabs
        content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
        
        removed_count = original_length - len(content)
        if removed_count > 0:
            stats.invisible_chars_removed += removed_count
        
        return content
    
    def _fix_line_breaks(self, content: str, stats: CleaningStats) -> str:
        """Fix broken line breaks and normalize line endings"""
        # Normalize line endings to \n
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Fix broken sentences (line breaks in the middle of sentences)
        lines = content.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # If line ends with lowercase letter and next line starts with lowercase, 
            # it's probably a broken sentence
            if (i < len(lines) - 1 and 
                line and 
                line[-1].islower() and 
                lines[i + 1].strip() and 
                lines[i + 1].strip()[0].islower()):
                
                fixed_lines.append(line + ' ')
                stats.line_breaks_fixed += 1
            else:
                fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _standardize_whitespace(self, content: str, stats: CleaningStats) -> str:
        """Standardize whitespace characters"""
        original_content = content
        
        # Replace multiple spaces with single space
        content = re.sub(r' {2,}', ' ', content)
        
        # Replace multiple tabs with single space
        content = re.sub(r'\t+', ' ', content)
        
        # Remove spaces at line beginnings and ends
        lines = content.split('\n')
        lines = [line.strip() for line in lines]
        content = '\n'.join(lines)
        
        # Remove multiple consecutive newlines (keep max 2)
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        if content != original_content:
            stats.whitespace_normalized += 1
        
        return content
    
    def _remove_redundant_content(self, content: str, stats: CleaningStats) -> str:
        """Remove redundant and low-quality content (aggressive cleaning)"""
        lines = content.split('\n')
        filtered_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip very short lines (likely noise)
            if len(line) < 3:
                continue
            
            # Skip lines with mostly special characters
            special_char_ratio = sum(1 for c in line if not c.isalnum() and not c.isspace()) / len(line)
            if special_char_ratio > 0.7:
                continue
            
            # Skip duplicate consecutive lines
            if filtered_lines and filtered_lines[-1] == line:
                continue
            
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    
    def _determine_language(self, detected_languages: List[str]) -> str:
        """Determine the primary language from detected languages"""
        if not detected_languages:
            return "unknown"
        
        # Count language occurrences
        language_counts = {}
        for lang in detected_languages:
            language_counts[lang] = language_counts.get(lang, 0) + 1
        
        # Return the most common language
        return max(language_counts, key=language_counts.get)
    
    def _calculate_quality_score(self, elements: List[DocumentElement], stats: CleaningStats) -> float:
        """Calculate quality score for the cleaned document"""
        score = 1.0
        
        # Penalize excessive content reduction
        reduction = stats.get_reduction_percentage()
        if reduction > 50:
            score -= 0.3
        elif reduction > 30:
            score -= 0.2
        elif reduction > 15:
            score -= 0.1
        
        # Reward good structure
        if len(elements) > 0:
            avg_content_length = sum(len(elem.content) for elem in elements) / len(elements)
            if avg_content_length > 100:
                score += 0.1
            elif avg_content_length < 20:
                score -= 0.1
        
        # Penalize too many removed headers/footers (might be over-cleaning)
        if stats.headers_removed + stats.footers_removed > len(elements) * 0.5:
            score -= 0.2
        
        # Ensure score is between 0 and 1
        return max(0.0, min(1.0, score))
    
    def get_cleaning_summary(self, normalized_doc: NormalizedDocument) -> str:
        """Generate a summary of cleaning operations"""
        stats = normalized_doc.cleaning_stats
        
        summary_parts = [
            f"Language: {stats.language_detected}",
            f"Quality: {normalized_doc.quality_score:.2f}",
            f"Reduction: {stats.get_reduction_percentage():.1f}%",
            f"Headers removed: {stats.headers_removed}",
            f"Footers removed: {stats.footers_removed}",
            f"Elements: {len(normalized_doc.cleaned_elements)}/{normalized_doc.metadata['elements_processed']}"
        ]
        
        return " | ".join(summary_parts)
    
    def validate_cleaning(self, normalized_doc: NormalizedDocument) -> Dict[str, Any]:
        """Validate the quality of cleaning"""
        validation = {
            'is_valid': True,
            'warnings': [],
            'errors': []
        }
        
        # Check for excessive content loss
        reduction = normalized_doc.cleaning_stats.get_reduction_percentage()
        if reduction > 60:
            validation['errors'].append("Excessive content reduction detected")
            validation['is_valid'] = False
        elif reduction > 40:
            validation['warnings'].append("High content reduction detected")
        
        # Check quality score
        if normalized_doc.quality_score < 0.5:
            validation['errors'].append("Low quality score")
            validation['is_valid'] = False
        elif normalized_doc.quality_score < 0.7:
            validation['warnings'].append("Moderate quality score")
        
        # Check if any content remains
        if len(normalized_doc.cleaned_elements) == 0:
            validation['errors'].append("No content remaining after cleaning")
            validation['is_valid'] = False
        
        return validation