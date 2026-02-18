
import networkx as nx
import logging
import statistics

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class KGQualityEvaluator:
    def __init__(self, graph_path):
        self.graph = nx.read_graphml(graph_path)
        self.nodes = self.graph.nodes(data=True)
        self.edges = self.graph.edges(data=True)
        
    def evaluate(self):
        logger.info("=== Knowledge Graph Quality Assessment Report ===")
        logger.info(f"Total Nodes: {self.graph.number_of_nodes()}")
        logger.info(f"Total Edges: {self.graph.number_of_edges()}")
        
        # 1. Reaction Contextualization Score (RCS)
        rcs_score = self._calculate_rcs()
        
        # 2. Chemical Resolution Score (CRS)
        crs_score = self._calculate_crs()
        
        # 3. Knowledge Density (KD)
        kd_score = self._calculate_kd()
        
        # Final Weighted Score
        # RCS (40%) + CRS (40%) + KD (Normalized to 0-1, say max 20 nodes/paper is 1.0) * 20%
        # KD implies effort. Let's stick to RCS and CRS for "Quality".
        
        final_quality = (rcs_score * 0.5) + (crs_score * 0.5)
        
        logger.info("-" * 40)
        logger.info(f"1. Reaction Context Completeness (RCS): {rcs_score:.2%} (Target: >80%)")
        logger.info(f"2. Chemical Specificity Rate (CRS):     {crs_score:.2%} (Target: >50%)")
        logger.info(f"3. Knowledge Density (KD):              {kd_score:.1f} nodes/paper")
        logger.info("-" * 40)
        logger.info(f"FINAL OBJECTIVE QUALITY SCORE: {final_quality:.2%}")
        logger.info("=" * 40)

    def _calculate_rcs(self):
        """Calculates how 'complete' each reaction node is."""
        reactions = [n for n, d in self.nodes if d.get('type') == 'Reaction']
        if not reactions: return 0.0
        
        scores = []
        for r_node in reactions:
            neighbors = self.graph.neighbors(r_node)
            has_catalyst = False
            has_condition = False
            has_participant = False
            
            # Since edges are directed (Paper -> Reaction), participants might be linked differently.
            # In our builder: 
            # Paper -> Reaction (REPORTS)
            # Molecule -> Reaction (PARTICIPANT_IN)
            # Peptide -> Reaction (CATALYZES)
            # Reaction -> Condition (HAS_CONDITION)
            
            # So we need to look at Predecessors and Successors
            all_connected = list(self.graph.predecessors(r_node)) + list(self.graph.successors(r_node))
            
            for neighbor in all_connected:
                n_type = self.graph.nodes[neighbor].get('type')
                if n_type in ['Peptide', 'Chemical']: has_catalyst = True
                if n_type == 'Condition': has_condition = True
                if n_type == 'Molecule': has_participant = True
            
            # Scoring logic for this reaction
            # Catalyst is King (0.4), Condition (0.3), Molecule (0.3)
            score = (0.4 if has_catalyst else 0) + (0.3 if has_condition else 0) + (0.3 if has_participant else 0)
            scores.append(score)
            
        return statistics.mean(scores) if scores else 0.0

    def _calculate_crs(self):
        """Calculates the specificity of chemical nodes."""
        # Molecules (Image) and Peptides (Text)
        molecules = [n for n, d in self.nodes if d.get('type') == 'Molecule']
        peptides = [n for n, d in self.nodes if d.get('type') == 'Peptide']
        
        total_chem_nodes = len(molecules) + len(peptides)
        if total_chem_nodes == 0: return 0.0
        
        valid_molecules = 0
        for m in molecules:
            # Check if reactivity_class is specific (not Unknown)
            r_class = self.graph.nodes[m].get('reactivity_class', 'Unknown')
            if r_class and r_class != 'Unknown':
                valid_molecules += 1
                
        valid_peptides = 0
        for p in peptides:
            # Check if it looks like a specific sequence (Ac-...)
            label = self.graph.nodes[p].get('label', '')
            if label.startswith('Ac-') or len(label) > 10: # Rough heuristic for "Specific Sequence"
                valid_peptides += 1
                
        return (valid_molecules + valid_peptides) / total_chem_nodes

    def _calculate_kd(self):
        """Nodes per paper."""
        papers = [n for n, d in self.nodes if d.get('type') == 'Paper']
        if not papers: return 0.0
        
        total_info_nodes = self.graph.number_of_nodes() - len(papers)
        return total_info_nodes / len(papers)

if __name__ == "__main__":
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    graph_path = os.path.join(base_dir, "output", "global_knowledge_graph.graphml")
    
    print(f"Evaluating Graph: {graph_path}")
    evaluator = KGQualityEvaluator(graph_path)
    evaluator.evaluate()
