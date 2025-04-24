import unittest
from data_pipeline.llm_processor.requirements_parser import RequirementsParser


class TestRequirementsParser(unittest.TestCase):

    def setUp(self) -> None:
        self.canonical_skill_map = {
            "js": "JavaScript",
            "py": "Python",
        }
        self.tech_capitalization_map = {
            "python": "Python",
            "javascript": "JavaScript",
            "c++": "C++",
            "c#": "C#"
        }

        self.requirements_parser = RequirementsParser(canonical_skill_map=self.canonical_skill_map, tech_capitalization_map=self.tech_capitalization_map)

    
    def test_normalize_skill_basic(self) -> None:
        self.assertEqual(self.requirements_parser.normalize_skill("  Python  "), "Python")

    def test_normalize_skill_with_canonical_mapping(self) -> None:
        self.assertEqual(self.requirements_parser.normalize_skill("js"), "JavaScript")

    def test_normalize_skill_with_slash(self) -> None:
        self.assertEqual(self.requirements_parser.normalize_skill("C#/C++"), ["C#", "C++"])

    def test_normalize_skill_with_special_chars(self) -> None:
        self.assertEqual(self.requirements_parser.normalize_skill("Python!!"), "Python")


    def test_clean_extracted_data_basic(self) -> None:
        raw_data = {
            "skills": ["Python", "js", "C++/C#", "Docker", "py"]
        }
        result = self.requirements_parser.clean_extracted_data(raw_data)
        expected = {
            "skills": sorted(["Python", "JavaScript", "C++", "C#", "Docker"])
        }

        self.assertEqual(result, expected)

    def test_clean_extracted_data_non_string_entries(self) -> None:
        raw_data = {
            "skills": ["Python", 42, None, "js"]
        }
        result = self.requirements_parser.clean_extracted_data(raw_data)
        expected = {
            "skills": sorted(["Python", "JavaScript"])
        }

        self.assertEqual(result, expected)

    def test_clean_extracted_data_missing_skills_key(self) -> None:
        raw_data = {
            "job_title": "Software Engineer"
        }
        result = self.requirements_parser.clean_extracted_data(raw_data)
        expected = {
            "job_title": "Software Engineer"
        }

        self.assertEqual(result, expected)

    def test_clean_extracted_data_skills_not_list(self) -> None:
        raw_data = {
            "skills": "Python"
        }
        result = self.requirements_parser.clean_extracted_data(raw_data)
        expected = {
            "skills": ["Python"]
        }

        self.assertEqual(result, expected)

if __name__ == "__main__":
    unittest.main()
