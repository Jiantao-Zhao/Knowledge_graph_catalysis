
import os
import json
import logging
import pdfplumber
from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import DECIMER if available, else use mock for dev
try:
    from DECIMER import predict_SMILES
    DECIMER_AVAILABLE = True
except ImportError:
    logger.warning("DECIMER not found. Using mock implementation.")
    DECIMER_AVAILABLE = False
    def predict_SMILES(path):
        return "MOCK_SMILES_STRING"

import re

class UniversalLiteratureExtractor:
    def __init__(self, pdf_dir: str, output_dir: str):
        self.pdf_dir = Path(pdf_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_base_dir = self.output_dir / "extracted_images"
        self.images_base_dir.mkdir(exist_ok=True)
        self.json_dir = self.output_dir / "json_knowledge_graphs"
        self.json_dir.mkdir(exist_ok=True)
        
    def process_all_pdfs(self):
        """Iterates through all PDFs in the directory."""
        pdf_files = list(self.pdf_dir.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDFs in {self.pdf_dir}")
        
        for pdf_path in pdf_files[:5]:
            try:
                self.process_single_pdf(pdf_path)
            except Exception as e:
                logger.error(f"Failed to process {pdf_path.name}: {e}")

    def process_single_pdf(self, pdf_path: Path):
        logger.info(f"Processing: {pdf_path.name}")
        
        # Create a specific image directory for this PDF to avoid collisions
        safe_name = pdf_path.stem.replace(" ", "_").replace(".", "_")
        pdf_img_dir = self.images_base_dir / safe_name
        pdf_img_dir.mkdir(exist_ok=True)
        
        extracted_images = []
        full_text = ""
        
        with pdfplumber.open(pdf_path) as pdf:
            # Process only first 5 pages for prototype speed
            for i, page in enumerate(pdf.pages):
                if i >= 5: 
                    break
                
                # Extract Text
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
                
                # Extract Images
                extracted_images.extend(self.extract_images_from_page(page, i + 1, pdf_img_dir, safe_name))

        # Extract Text Entities (Peptides, Conditions)
        text_entities = self.extract_text_entities(full_text)

        # Generate Knowledge Graph JSON
        kg_data = self.synthesize_knowledge_graph(pdf_path, extracted_images, text_entities)
        
        # Save JSON
        json_path = self.json_dir / f"{safe_name}.json"
        with open(json_path, 'w') as f:
            json.dump(kg_data, f, indent=2)
            
        logger.info(f"Saved KG to {json_path}")

    def extract_text_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Uses Regex to find chemical entities in the text.
        """
        entities = {
            "peptides": [],
            "conditions": [],
            "chemicals": [],
            "reaction_types": []
        }
        
        # 1. Peptide Sequences
        # Pattern A: 3-letter codes (e.g. Phe-Phe)
        aa_codes = "Ala|Arg|Asn|Asp|Cys|Gln|Glu|Gly|His|Ile|Leu|Lys|Met|Phe|Pro|Ser|Thr|Trp|Tyr|Val"
        peptide_pattern_3 = re.compile(rf"\b((?:{aa_codes})-(?:{aa_codes})(?:-(?:{aa_codes}))*)\b", re.IGNORECASE)
        entities["peptides"].extend(list(set(peptide_pattern_3.findall(text))))
        
        # Pattern B: Short sequences with hyphens (e.g. L-V-F-F)
        short_seq_pattern = re.compile(r"\b([L|D]-[A-Z]-[A-Z]-[A-Z]-[A-Z]*)\b")
        entities["peptides"].extend(list(set(short_seq_pattern.findall(text))))
        
        # Pattern C: Acetylated/Amidated sequences (e.g. Ac-HLVFFAE, H-Phe-OH)
        # Matches Ac- followed by 2-15 uppercase letters
        ac_pattern = re.compile(r"\bAc-[A-Z]{2,15}\b") 
        entities["peptides"].extend(list(set(ac_pattern.findall(text))))
        
        # 2. Reaction Conditions (Temp, Time, pH)
        temp_pattern = re.compile(r"\b(\d+\s*°C)\b")
        time_pattern = re.compile(r"\b(\d+\s*(?:h|min|days))\b")
        ph_pattern = re.compile(r"\bpH\s*=?\s*\d+(?:\.\d+)?\b", re.IGNORECASE)
        
        entities["conditions"].extend(list(set(temp_pattern.findall(text))))
        entities["conditions"].extend(list(set(time_pattern.findall(text))))
        entities["conditions"].extend(list(set(ph_pattern.findall(text))))
        
        # 3. Specific Chemicals (Hemin, etc.)
        chemical_keywords = ["Hemin", "Protoporphyrin", "Thioflavin", "Congo Red", "Benzaldehyde", "Aniline", "Sodium dithionite"]
        for chem in chemical_keywords:
            if chem.lower() in text.lower():
                entities["chemicals"].append(chem)

        # 4. Reaction Types (Concept Mining)
        reaction_keywords = [
            "cyclopropanation", "hydrolysis", "aldol", "michael addition", 
            "esterification", "oxidation", "reduction", "epoxidation", 
            "friedel-crafts", "carbene transfer"
        ]
        found_reactions = []
        for rxn in reaction_keywords:
            if re.search(r"\b" + re.escape(rxn) + r"\b", text, re.IGNORECASE):
                found_reactions.append(rxn.title())
        entities["reaction_types"] = list(set(found_reactions))
                
        return entities

    def extract_images_from_page(self, page, page_num, save_dir, doc_id) -> List[Dict]:
        results = []
        for j, img in enumerate(page.images):
            # Filter: Check size. 
            # Heuristic: Ignore very small images (icons, bullets) or very thin ones (lines)
            w = img['width']
            h = img['height']
            if w < 100 or h < 100:
                continue
            if w/h > 10 or h/w > 10: # Ignore lines
                continue
                
            img_id = f"{doc_id}_p{page_num}_i{j+1}"
            img_filename = f"{img_id}.png"
            img_path = save_dir / img_filename
            
            # Robust extraction
            try:
                bbox = (img['x0'], img['top'], img['x1'], img['bottom'])
                cropped_page = page.crop(bbox)
                im = cropped_page.to_image(resolution=300)
                im.save(img_path)
                
                # Predict SMILES
                smiles = predict_SMILES(str(img_path))
                
                results.append({
                    "image_id": img_id,
                    "page": page_num,
                    "file_path": str(img_path),
                    "predicted_smiles": smiles,
                    "bbox": bbox
                })
            except Exception as e:
                logger.warning(f"Could not extract image {img_id}: {e}")
                
        return results

    def synthesize_knowledge_graph(self, pdf_path: Path, extracted_images: List[Dict], text_entities: Dict) -> Dict:
        """
        Combines Image and Text data.
        """
        return {
            "source_file": pdf_path.name,
            "metadata": {
                "title": "Extracted from filename", # Placeholder
                "doi": "Unknown" 
            },
            "extracted_visual_entities": extracted_images,
            "extracted_text_entities": text_entities,
            "llm_extraction_prompt_template": "Analyze the following chemical structures found in images: {smiles_list} along with the text from the paper. Identify the reaction components (substrate, product, catalyst) and conditions."
        }


def main():
    # Relative paths for standalone project
    base_dir = Path(__file__).parent.parent
    pdf_input_dir = base_dir / "examples"
    output_dir = base_dir / "output"
    
    print(f"Input Directory: {pdf_input_dir}")
    print(f"Output Directory: {output_dir}")
    
    extractor = UniversalLiteratureExtractor(str(pdf_input_dir), str(output_dir))
    extractor.process_all_pdfs()

if __name__ == "__main__":
    main()
