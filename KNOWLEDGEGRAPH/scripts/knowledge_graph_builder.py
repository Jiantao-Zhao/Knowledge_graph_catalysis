import json
import logging
import networkx as nx
from pathlib import Path
from typing import Dict, List, Any
from rdkit import Chem

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UniversalGraphRAGBuilder:
    def __init__(self):
        self.graph = nx.MultiDiGraph() # Use MultiDiGraph to allow multiple relations
        
    def canonicalize(self, smiles: str) -> str:
        """Canonicalize SMILES to ensure same molecules from different papers merge."""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                return Chem.MolToSmiles(mol, isomericSmiles=True)
        except:
            pass
        return smiles

    def classify_molecule_reactivity(self, smiles: str) -> List[str]:
        """
        Identifies functional groups and their IMMEDIATE electronic environment using SMARTS.
        Returns a list of 'Reactivity Tags' (e.g., 'Alpha-Diazo-Ester', 'Aryl-Amine').
        """
        tags = []
        try:
            mol = Chem.MolFromSmiles(smiles)
            if not mol: return []
            
            # SMARTS Definitions with Neighborhood Context
            patterns = {
                # 1. Diazo Contexts
                "Alpha-Diazo-Ester": "[N-]=[N+]=C-C(=O)O", # Diazo adjacent to Ester Carbonyl - CARBENE PRECURSOR
                "Alpha-Diazo-Ketone": "[N-]=[N+]=C-C(=O)[#6]", # Diazo adjacent to Ketone
                "Aryl-Diazo": "[N-]=[N+]=N-c", # Diazo on Aromatic ring (Azide actually, usually written N=[N+]=[N-] but RDKit normalizes)
                "Diazo-Group": "[N-]=[N+]=C", # Generic Diazo (fallback)

                # 2. Olefin Contexts
                "Styrene-Like": "C=C-c", # Double bond conjugated with aromatic ring - CYCLOPROPANATION SUBSTRATE
                "Michael-Acceptor": "C=C-C(=O)", # Double bond conjugated with carbonyl
                "Isolated-Alkene": "C=C", # Generic

                # 3. Amine Contexts
                "Aryl-Amine": "Nc", # Aniline derivative
                "Alkyl-Amine": "NC", # Aliphatic amine
                "Amide": "NC(=O)", # Peptide bond or other amide

                # 4. Ring Contexts
                "Epoxide/Aziridine/Cyclopropane": "C1CC1", # 3-membered ring (Strain!)
                "Heme-Like-Core": "n1ccc2c1" # Rough pattern for porphyrin/pyrrole fragments
            }
            
            for label, smarts in patterns.items():
                pattern = Chem.MolFromSmarts(smarts)
                if pattern and mol.HasSubstructMatch(pattern):
                    tags.append(label)
                    
        except:
            pass
        return tags

    def process_batch(self, json_dir: str, output_path: str):
        """Processes all JSON extractions and merges them into one global graph."""
        json_paths = list(Path(json_dir).glob("*.json"))
        logger.info(f"Merging {len(json_paths)} papers into global knowledge graph...")
        
        for path in json_paths:
            self._add_paper_to_graph(path)
            
        self._export_graph(output_path)

    def _add_paper_to_graph(self, json_path: Path):
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        paper_id = data.get("source_file", json_path.stem)
        self.graph.add_node(paper_id, type="Paper", label=paper_id)
        
        # --- Process Text Entities for Reaction Labeling ---
        text_data = data.get("extracted_text_entities", {})
        
        # Determine Reaction Label
        rxn_types = text_data.get("reaction_types", [])
        if rxn_types:
            rxn_label = " / ".join(rxn_types[:2]) # e.g. "Cyclopropanation"
        else:
            rxn_label = "Catalytic Process"
            
        reaction_id = f"Reaction_{paper_id}"
        if not self.graph.has_node(reaction_id):
             self.graph.add_node(reaction_id, type="Reaction", label=rxn_label)
        else:
             if rxn_label != "Catalytic Process":
                 self.graph.nodes[reaction_id]['label'] = rxn_label
        
        self.graph.add_edge(paper_id, reaction_id, relation="REPORTS")
        
        # --- Process Visual Entities (Images) ---
        for entity in data.get("extracted_visual_entities", []):
            raw_smiles = entity.get("predicted_smiles", "")
            if len(raw_smiles) < 10: continue
            
            # Canonicalize for merging
            can_smiles = self.canonicalize(raw_smiles.split('.')[0]) # Take first fragment
            
            # --- NEW: Classify Reactivity ---
            reactivity_tags = self.classify_molecule_reactivity(can_smiles)
            reactivity_label = " | ".join(reactivity_tags) if reactivity_tags else "Unknown"
            
            # Use SMILES as the unique ID for Molecule nodes! 
            mol_id = f"MOL_{can_smiles}" 
            
            if not self.graph.has_node(mol_id):
                # Add the Reactivity Class to the node attributes
                self.graph.add_node(mol_id, type="Molecule", smiles=can_smiles, label=can_smiles[:20]+"...", reactivity_class=reactivity_label)
            
            # Link to the reaction in THIS paper
            self.graph.add_edge(mol_id, reaction_id, relation="PARTICIPANT_IN")

        # --- Process Text Entities (Nodes) ---
        
        # 1. Peptides
        for pep in text_data.get("peptides", []):
            pep_id = f"PEP_{pep}"
            if not self.graph.has_node(pep_id):
                self.graph.add_node(pep_id, type="Peptide", label=pep)
            self.graph.add_edge(pep_id, reaction_id, relation="CATALYZES")
            
        # 2. Conditions
        for cond in text_data.get("conditions", []):
            cond_id = f"COND_{cond}"
            if not self.graph.has_node(cond_id):
                self.graph.add_node(cond_id, type="Condition", label=cond)
            self.graph.add_edge(reaction_id, cond_id, relation="HAS_CONDITION")
            
        # 3. Chemicals (Named)
        for chem in text_data.get("chemicals", []):
            chem_id = f"CHEM_{chem}"
            if not self.graph.has_node(chem_id):
                self.graph.add_node(chem_id, type="Chemical", label=chem)
            self.graph.add_edge(chem_id, reaction_id, relation="INVOLVED_IN")

    def _export_graph(self, output_base: str):
        nx.write_graphml(self.graph, f"{output_base}.graphml")
        logger.info(f"Global Knowledge Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")
        logger.info(f"Saved to {output_base}.graphml")

def main():
    # Relative paths for standalone project
    base_dir = Path(__file__).parent.parent
    json_input_dir = base_dir / "output/json_knowledge_graphs"
    output_base = base_dir / "output/global_knowledge_graph"
    
    print(f"Reading JSONs from: {json_input_dir}")
    
    builder = UniversalGraphRAGBuilder()
    builder.process_batch(str(json_input_dir), str(output_base))

if __name__ == "__main__":
    main()