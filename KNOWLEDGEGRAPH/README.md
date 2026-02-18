# Knowledge Graph Extraction System

This is a standalone project for extracting chemical knowledge graphs from scientific PDFs. It combines Visual Structure Recognition (DECIMER) with Text Entity Mining (Regex) to build a hybrid knowledge graph.

## Project Structure

- `scripts/`: Core Python scripts.
    - `extraction_pipeline.py`: Extracts images and text entities from PDFs -> JSON.
    - `knowledge_graph_builder.py`: Converts JSONs -> GraphML (NetworkX) with chemical logic.
    - `kg_quality_evaluator.py`: Calculates objective quality metrics (RCS, CRS) for the graph.
- `examples/`: Contains a sample PDF.
- `output/`: Generated data will appear here.

## Setup

1.  **Create Environment** (Python 3.9+ recommended):
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

## Usage

### 1. Run Extraction
Extracts raw data (images + text) from PDFs in the `examples/` folder.
```bash
# Note: You may need to edit the input/output paths in the script or run as is
python scripts/extraction_pipeline.py
```
*By default, the script in this package is configured to read from `examples/` and output to `output/`.* 
**(Note: I will update the paths in the scripts in the next step to ensure they point to these relative directories)**

### 2. Build Graph
Merges extracted JSONs into a Knowledge Graph.
```bash
python scripts/knowledge_graph_builder.py
```

### 3. Evaluate Quality
Scores the graph based on completeness and chemical accuracy.
```bash
python scripts/kg_quality_evaluator.py
```

## Output
- `output/global_knowledge_graph.graphml`: The final graph file. Open with **Gephi** or **Cytoscape**.
