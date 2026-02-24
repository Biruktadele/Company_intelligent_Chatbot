#!/usr/bin/env python3
"""
Test script for complete document processing pipeline up to modeling
"""

import sys
import os
from pathlib import Path

# Add app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from service.Indexing.documnt_accution import DocumentAcquisition
from service.Indexing.document_paresing_and_extracting_structuerd import DocumentParser
from service.Indexing.normalization_and_cleaning import DocumentNormalizer, CleaningLevel
from service.Indexing.document_modeling import ProcessedDocument, DocumentRegistry, DocumentStatus
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_complete_pipeline():
    """Test the complete document processing pipeline"""
    print("\n" + "="*60)
    print("TESTING COMPLETE DOCUMENT PROCESSING PIPELINE")
    print("="*60)
    
    # Initialize components
    doc_acq = DocumentAcquisition(logger)
    doc_parser = DocumentParser(logger)
    doc_normalizer = DocumentNormalizer(CleaningLevel.STANDARD, logger)
    registry = DocumentRegistry()
    
    # Test files
    test_files = [
        'test/sample.txt',
        'test/sample.md', 
        'test/sample.html'
    ]
    
    processed_docs = []
    
    for file_path in test_files:
        print(f"\n🔍 Processing: {file_path}")
        print("-" * 40)
        
        try:
            # Step 1: Acquisition
            print("1️⃣  Acquiring document...")
            acquired_doc = doc_acq.acquire_single_file(file_path)
            if not acquired_doc:
                print(f"❌ Failed to acquire {file_path}")
                continue
            
            print(f"   ✅ Acquired: {acquired_doc.metadata.filename} ({len(acquired_doc.content)} chars)")
            
            # Step 2: Parsing
            print("2️⃣  Parsing document structure...")
            structure = doc_parser.parse_document(acquired_doc.content, acquired_doc.metadata.file_type)
            print(f"   ✅ Parsed: {len(structure.elements)} elements, {len(structure.table_of_contents)} sections")
            
            # Step 3: Normalization
            print("3️⃣  Normalizing content...")
            normalized_doc = doc_normalizer.normalize_document(structure)
            print(f"   ✅ Normalized: {normalized_doc.detected_language} lang, quality: {normalized_doc.quality_score:.2f}")
            
            # Step 4: Modeling
            print("4️⃣  Creating document model...")
            processed_doc = ProcessedDocument(
                original_metadata=acquired_doc.metadata,
                normalized_content=normalized_doc
            )
            processed_doc.update_status(DocumentStatus.NORMALIZED, "Document processed successfully")
            
            # Register document
            registry.register(processed_doc)
            processed_docs.append(processed_doc)
            
            print(f"   ✅ Modeled: {processed_doc.doc_id[:8]}... status: {processed_doc.status.value}")
            
            # Show cleaning summary
            summary = doc_normalizer.get_cleaning_summary(normalized_doc)
            print(f"   📊 Cleaning: {summary}")
            
        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")
            import traceback
            traceback.print_exc()
    
    return processed_docs, registry

def test_document_registry():
    """Test document registry functionality"""
    print("\n" + "="*60)
    print("TESTING DOCUMENT REGISTRY")
    print("="*60)
    
    # Create test documents
    registry = DocumentRegistry()
    
    # Test registration
    print("\n📝 Testing document registration...")
    for i in range(3):
        doc = ProcessedDocument()
        doc.update_status(DocumentStatus.ACQUIRED, f"Test document {i+1}")
        registry.register(doc)
        print(f"   ✅ Registered: {doc.doc_id[:8]}...")
    
    # Test retrieval
    print("\n🔍 Testing document retrieval...")
    doc_ids = list(registry.documents.keys())
    for doc_id in doc_ids:
        doc = registry.get_document(doc_id)
        if doc:
            print(f"   ✅ Retrieved: {doc.doc_id[:8]}... status: {doc.status.value}")
        else:
            print(f"   ❌ Failed to retrieve: {doc_id[:8]}...")
    
    # Test serialization
    print("\n📋 Testing document serialization...")
    for doc_id in doc_ids[:2]:  # Test first 2 documents
        doc = registry.get_document(doc_id)
        if doc:
            doc_dict = doc.to_dict()
            print(f"   ✅ Serialized: {doc_dict['doc_id'][:8]}... -> {doc_dict['status']}")
    
    print(f"\n📊 Registry contains {len(registry.documents)} documents")

def test_cleaning_levels():
    """Test different cleaning levels"""
    print("\n" + "="*60)
    print("TESTING CLEANING LEVELS")
    print("="*60)
    
    # Create test content with various issues
    test_content = """
    
    Page 1
    
    # Sample Document
    
    This is a test document with various issues.
    
    Confidential Draft - Do Not Distribute
    
    ## Section 1
    
    This content has    multiple   spaces.
    
    It also has
    
    broken line breaks that should be fixed.
    
    Page 2
    
    ## Section 2
    
    More content here.
    
    © 2024 All Rights Reserved
    
    """
    
    from service.Indexing.document_paresing_and_extracting_structuerd import DocumentStructure, DocumentElement, ContentType
    
    # Create mock structure
    element = DocumentElement(
        content=test_content,
        element_type=ContentType.PARAGRAPH,
        level=0,
        position=0,
        metadata={}
    )
    
    structure = DocumentStructure(
        elements=[element],
        hierarchy={},
        metadata={},
        table_of_contents=[]
    )
    
    # Test different cleaning levels
    levels = [CleaningLevel.MINIMAL, CleaningLevel.STANDARD, CleaningLevel.AGGRESSIVE]
    
    for level in levels:
        print(f"\n🧹 Testing {level.value} cleaning...")
        normalizer = DocumentNormalizer(level, logger)
        normalized = normalizer.normalize_document(structure)
        
        print(f"   Original chars: {normalized.cleaning_stats.original_chars}")
        print(f"   Cleaned chars: {normalized.cleaning_stats.cleaned_chars}")
        print(f"   Reduction: {normalized.cleaning_stats.get_reduction_percentage():.1f}%")
        print(f"   Quality score: {normalized.quality_score:.2f}")
        print(f"   Headers removed: {normalized.cleaning_stats.headers_removed}")
        print(f"   Footers removed: {normalized.cleaning_stats.footers_removed}")
        
        # Show preview
        preview = normalized.cleaned_elements[0].content[:200] if normalized.cleaned_elements else "No content"
        print(f"   Preview: {repr(preview)}...")

def main():
    """Run all pipeline tests"""
    print("🚀 STARTING COMPLETE PIPELINE TESTS")
    print(f"Working directory: {os.getcwd()}")
    
    try:
        # Test complete pipeline
        processed_docs, registry = test_complete_pipeline()
        
        # Test registry
        test_document_registry()
        
        # Test cleaning levels
        test_cleaning_levels()
        
        print("\n" + "="*60)
        print("🎉 ALL PIPELINE TESTS COMPLETED")
        print("="*60)
        print(f"📊 Processed {len(processed_docs)} documents successfully")
        print(f"📋 Registry contains {len(registry.documents)} documents")
        
    except Exception as e:
        logger.error(f"Pipeline test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
