# Challenge 1b: Multi-Collection PDF Analysis

## Overview

Advanced PDF analysis solution that processes multiple document collections and extracts relevant content based on specific personas and use cases using semantic similarity and machine learning techniques.

## Project Architecture

```
Challenge_1b/
├── Collection 1/                    # Travel Planning
│   ├── PDFs/                       # South of France guides (7 documents)
│   ├── model_inputs/               # Parsed JSON from PDFs
│   ├── challenge1b_input.json      # Input configuration
│   └── challenge1b_output.json     # Analysis results
├── Collection 2/                    # Adobe Acrobat Learning
│   ├── PDFs/                       # Acrobat tutorials (15 documents)
│   ├── model_inputs/               # Parsed JSON from PDFs
│   ├── challenge1b_input.json      # Input configuration
│   └── challenge1b_output.json     # Analysis results
├── Collection 3/                    # Recipe Collection
│   ├── PDFs/                       # Cooking guides (9 documents)
│   ├── model_inputs/               # Parsed JSON from PDFs
│   ├── challenge1b_input.json      # Input configuration
│   └── challenge1b_output.json     # Analysis results
├── venv/                           # Virtual environment
└── README.md
```

## Document Collections

### Collection 1: Travel Planning
- **Challenge ID**: `round_1b_002`
- **Persona**: Travel Planner
- **Task**: Plan a 4-day trip for 10 college friends to South of France
- **Documents**: 7 travel guides covering cities, cuisine, history, hotels, activities, tips, and culture

### Collection 2: Adobe Acrobat Learning
- **Challenge ID**: `round_1b_003`
- **Persona**: HR Professional
- **Task**: Create and manage fillable forms for onboarding and compliance
- **Documents**: 15 Acrobat guides covering creation, editing, exporting, sharing, and AI features

### Collection 3: Recipe Collection
- **Challenge ID**: `round_1b_001`
- **Persona**: Food Contractor
- **Task**: Prepare vegetarian buffet-style dinner menu for corporate gathering
- **Documents**: 9 cooking guides with recipes and preparation techniques

## Processing Pipeline

### Phase 1: PDF Parsing
1. **Input**: PDF documents from each collection
2. **Process**: Utilize Challenge 1a PDF parser to extract structured content
3. **Output**: JSON files with parsed sections and subsections stored in `model_inputs/`

### Phase 2: Semantic Analysis
1. **Query Construction**: Combine persona role and job-to-be-done into unified query
2. **Embedding Generation**: Use MiniLM sentence transformer to encode:
   - Combined query string
   - All document subsections
3. **Similarity Scoring**: Calculate cosine similarity between query and content embeddings
4. **Ranking**: Sort subsections by relevance score (highest to lowest)

### Phase 3: Output Generation
1. **Section Extraction**: Select top 10 most relevant sections
2. **Metadata Compilation**: Include processing details and input parameters
3. **JSON Formatting**: Structure results according to specified output schema

## Input Format

```json
{
  "challenge_info": {
    "challenge_id": "round_1b_XXX",
    "test_case_name": "specific_test_case",
    "description": "Collection description"
  },
  "documents": [
    {
      "filename": "document.pdf",
      "title": "Document Title"
    }
  ],
  "persona": {
    "role": "User Persona"
  },
  "job_to_be_done": {
    "task": "Specific use case description"
  }
}
```

## Output Format

```json
{
  "metadata": {
    "input_documents": ["list of processed documents"],
    "persona": "User Persona",
    "job_to_be_done": "Task description",
    "processing_timestamp": "ISO timestamp"
  },
  "extracted_sections": [
    {
      "document": "source.pdf",
      "section_title": "Relevant Section Title",
      "importance_rank": 1,
      "page_number": 1
    }
  ],
  "subsection_analysis": [
    {
      "document": "source.pdf",
      "refined_text": "Relevant content excerpt",
      "page_number": 1
    }
  ]
}
```

## Technical Implementation

### Core Technologies
- **PDF Processing**: Challenge 1a parser for content extraction
- **NLP Model**: Sentence Transformers MiniLM for semantic embeddings
- **Similarity Engine**: PyTorch cosine similarity for relevance scoring
- **Text Processing**: Optional TextRank summarization for content refinement

### Key Algorithm Steps

1. **Query Embedding**:
   ```python
   query = f"{persona}. {job_to_be_done}"
   query_embedding = model.encode(query, convert_to_tensor=True)
   ```

2. **Content Scoring**:
   ```python
   for subsection in all_sections:
       text_embedding = model.encode(subsection.text, convert_to_tensor=True)
       score = util.pytorch_cos_sim(text_embedding, query_embedding).item()
   ```

3. **Result Ranking**:
   ```python
   ranked_results = sorted(scored_sections, key=lambda x: x['score'], reverse=True)
   ```

## Key Features

- **Persona-Driven Analysis**: Content relevance based on user role and objectives
- **Multi-Collection Processing**: Scalable architecture for different document types
- **Semantic Understanding**: Advanced NLP for context-aware content extraction
- **Importance Ranking**: Quantified relevance scoring for prioritized results
- **Structured Output**: Standardized JSON format for downstream processing
- **Optional Summarization**: Content condensation for improved readability

## Installation & Setup

1. **Environment Setup**:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

2. **Dependencies**:
   - sentence-transformers
   - torch
   - pymupdf (from Challenge 1a)
   - sumy (optional, for summarization)

3. **Run Analysis**:
   ```bash
   python main.py --collection [1|2|3]
   ```

## Performance Metrics

- **Processing Speed**: ~2-3 seconds per document collection
- **Accuracy**: Semantic relevance validation through manual review
- **Scalability**: Handles 5-15 documents per collection efficiently
- **Memory Usage**: Optimized for standard hardware configurations

## Use Cases

- **Research Literature Review**: Academic paper analysis for specific research domains
- **Technical Documentation**: Feature-specific content extraction from manuals
- **Training Material Curation**: Role-based learning content identification
- **Regulatory Compliance**: Policy-relevant section extraction from legal documents

---

*This project demonstrates advanced semantic analysis capabilities for multi-domain document processing with practical applications in enterprise and research environments.*
