import re
from typing import List, Dict, Any
from constants.canonical_skill_map import canonical_skill_map
from constants.tech_capitalization import tech_capitalization_map


class RequirementsParser:
    def __init__(self, canonical_skill_map: Dict[str, str] = None, tech_capitalization_map: Dict[str, str] = None) -> None:
        self.canonical_skill_map = canonical_skill_map or {}
        self.tech_capitalization_map = tech_capitalization_map


    
    def normalize_skill(self, skill: str) -> str:
        skill_normalized = skill.strip().lower()
        skill_normalized = re.sub(r'\(([^)]+)\)', r'\1', skill_normalized)

        # if " " in skill_normalized:
        #     parts = skill_normalized.split(" ")
        #     return [self.normalize_skill(part) for part in parts]

        if "/" in skill_normalized:
            parts = skill_normalized.split("/")
            return [self.normalize_skill(part) for part in parts]

        if skill_normalized in self.canonical_skill_map.keys():
            skill_normalized = self.canonical_skill_map[skill_normalized]

        if skill_normalized in self.tech_capitalization_map.keys():
            skill_normalized = self.tech_capitalization_map[skill_normalized]

        skill_normalized = re.sub(r"[^\w\s\+\#]", "", skill_normalized)

        return skill_normalized
    
    def clean_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        raw_skills = data.get("skills", [])     # data.get() because it can still return something when the key doesn't exist

        if not isinstance(raw_skills, list):
            raw_skills = [raw_skills]
        
        cleaned_skills = set()

        for skill in raw_skills:
            if not isinstance(skill, str):
                continue

            normalized_skill = self.normalize_skill(skill)
            self.clean_extracted_data_recursion(normalized_skill, cleaned_skills)

        return {
            **data,
            "skills": sorted(cleaned_skills)
        }

    def clean_extracted_data_recursion(self, skills: list | str, cleaned_skills_set: set) -> set:
        if isinstance(skills, str):
            cleaned_skills_set.add(skills)
        elif isinstance(skills, list):
            for skill in skills:
                self.clean_extracted_data_recursion(skill, cleaned_skills_set)

        return cleaned_skills_set


        


if __name__ == "__main__":
    data = {'skills': ['C/C++ (Linux)', 'Python', 'Golang']}
    requirements_parser = RequirementsParser(canonical_skill_map=canonical_skill_map, tech_capitalization_map=tech_capitalization_map)

    cleaned = requirements_parser.clean_extracted_data(data=data)
    print(cleaned)
