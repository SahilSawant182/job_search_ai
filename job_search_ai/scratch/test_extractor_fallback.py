import unittest
from unittest.mock import patch
from job_search_ai.services.knowledge.extraction.career_llm_extractor import CareerLLMExtractor
from job_search_ai.services.ai.vector_index import SearchResult

class TestExtractorFallback(unittest.TestCase):
    @patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_ollama")
    @patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed")
    @patch("job_search_ai.services.ai.vector_index.VectorIndex.search")
    def test_qdrant_fallback_activation(self, mock_search, mock_embed, mock_call_ollama):
        # 1. Simulate LLM failure (returns empty or invalid JSON)
        mock_call_ollama.return_value = "invalid response"
        
        # 2. Mock embedding service to return dummy vector
        mock_embed.return_value = [0.1] * 768
        
        # 3. Mock VectorIndex.search to return mock SearchResult
        mock_search.return_value = [
            SearchResult(
                id="CK-00001",
                score=0.85,
                payload={
                    "career_name": "Aerospace Engineer",
                    "required_skills": ["Aerodynamics", "Propulsion"],
                    "preferred_skills": ["CAD"],
                    "degree": ["B.Tech"],
                    "branch": ["Aerospace"],
                    "years": [3, 4],
                    "future_demand": "Very High"
                }
            )
        ]
        
        # Run extractor with focus that is not in the predefined map
        result = CareerLLMExtractor.extract(search_text="Some text", career_focus="Aerodynamics")
        
        # Verify vector fallback was used
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["career_name"], "Aerospace Engineer")
        self.assertEqual(result[0]["future_demand"], "Very High")
        self.assertEqual(result[0]["confidence"], 80)
        
        print("Qdrant fallback test passed successfully!")

    @patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_ollama")
    def test_predefined_fallback_activation(self, mock_call_ollama):
        # Simulate LLM failure
        mock_call_ollama.return_value = "invalid response"
        
        # Run extractor with predefined focus
        result = CareerLLMExtractor.extract(search_text="Some text", career_focus="Entrepreneurship")
        
        # Verify predefined fallback was used
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["career_name"], "Entrepreneur")
        self.assertEqual(result[0]["future_demand"], "High")
        self.assertEqual(result[0]["confidence"], 90)
        
        print("Predefined fallback test passed successfully!")

if __name__ == "__main__":
    unittest.main()
