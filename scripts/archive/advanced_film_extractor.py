#!/usr/bin/env python3
"""
Advanced Film Governance Data Extractor
Specialized patterns for Israeli cinema entities, relationships, and conflicts
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict
from enum import Enum

class EntityType(Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    FILM = "film"
    FUND = "fund"
    EVENT = "event"

@dataclass
class Entity:
    id: str
    name: str
    name_en: str = ""
    entity_type: str = EntityType.PERSON.value
    metadata: dict = None
    sources: list = None
    years: list = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.sources is None:
            self.sources = []
        if self.years is None:
            self.years = []

@dataclass
class Relationship:
    source_id: str
    target_id: str
    relationship_type: str  # "works_at", "funded_by", "evaluates", etc.
    confidence: float = 0.8
    evidence: list = None
    
    def __post_init__(self):
        if self.evidence is None:
            self.evidence = []

class FilmGovernanceExtractor:
    def __init__(self):
        self.entities = {}  # id -> Entity
        self.relationships = []
        self.conflicts = defaultdict(list)
        
        # Domain-specific patterns
        self.fund_names = {
            'rabinovich': ['קרן רבינוביץ', 'רבינוביץ'],
            'gesher': ['קרן גשר', 'גשר'],
            'cinema_fund': ['קרן הקולנוע', 'קרן קולנוע'],
            'arava': ['סרטים בערבה', 'ערבה'],
            'south': ['קרן קולנוע נגב', 'קרן דרום'],
        }
        
        self.role_patterns = {
            'ceo': r'מנכ"ל|מנהל כללי',
            'director': r'מנהל|דירקטור',
            'chairman': r'יושב ראש|נשיא',
            'founder': r'מייסד',
            'producer': r'מופקד|תעיר|יצרן',
            'screenwriter': r'תסריטאי',
            'filmmaker': r'במאי',
            'lecturer': r'לקטור',
            'evaluator': r'מעריך|שופט',
            'council_member': r'חבר מועצה|חברת מועצה',
            'minister': r'שר|שרה',
        }
        
        self.conflict_patterns = {
            'dual_role': r'(\w+).*(?:משחק|כתב|הפיק|ערך).*קיבל תמיכה|מימון',
            'evaluator_beneficiary': r'(לקטור|מעריך).*(קיבל|קבל|מימון|תמיכה)',
            'fund_concentration': r'(\d+)%|(\d+,\d+)',
        }

    def add_entity(self, entity: Entity):
        """Add or update entity"""
        self.entities[entity.id] = entity

    def add_relationship(self, rel: Relationship):
        """Add relationship"""
        self.relationships.append(rel)

    def extract_people_from_text(self, text: str, source_url: str = ""):
        """Extract Hebrew names from text"""
        # Hebrew name pattern: 2-4 Hebrew words
        pattern = r'[א-ת]+(?:\s+[א-ת]+){1,3}'
        matches = re.findall(pattern, text)
        
        people = []
        for match in matches:
            # Filter out common non-name words
            words = match.split()
            if len(words) >= 2 and all(len(w) > 1 for w in words):
                entity_id = match.lower().replace(' ', '_')
                person = Entity(
                    id=entity_id,
                    name=match,
                    entity_type=EntityType.PERSON.value,
                    sources=[source_url] if source_url else []
                )
                people.append(person)
        
        return people

    def extract_funds(self, text: str, source_url: str = ""):
        """Extract funding organization mentions"""
        funds = []
        for fund_id, aliases in self.fund_names.items():
            for alias in aliases:
                if alias in text:
                    entity_id = f"fund_{fund_id}"
                    fund = Entity(
                        id=entity_id,
                        name=alias,
                        entity_type=EntityType.FUND.value,
                        sources=[source_url] if source_url else []
                    )
                    funds.append(fund)
                    break
        
        return funds

    def extract_films(self, text: str, source_url: str = ""):
        """Extract film titles (Hebrew words in quotes or after סרט)"""
        # Pattern: "Hebrew text" or סרט "Hebrew text"
        pattern = r'["\']([א-ת\s]+?)["\']|סרט\s+([א-ת\s]+?)(?:\s*\(|$|\n)'
        matches = re.findall(pattern, text)
        
        films = []
        for match in matches:
            title = match[0] or match[1]
            title = title.strip()
            if title and len(title) > 3:
                entity_id = f"film_{title.lower().replace(' ', '_')}"
                film = Entity(
                    id=entity_id,
                    name=title,
                    entity_type=EntityType.FILM.value,
                    sources=[source_url] if source_url else []
                )
                films.append(film)
        
        return films

    def extract_roles(self, text: str, person_name: str):
        """Extract roles for a specific person"""
        roles = []
        for role, pattern in self.role_patterns.items():
            # Look for role pattern near person's name
            if re.search(pattern, text, re.IGNORECASE):
                roles.append(role)
        return roles

    def extract_years(self, text: str):
        """Extract years mentioned"""
        pattern = r'\b(19\d{2}|20\d{2})\b'
        return list(set(re.findall(pattern, text)))

    def detect_conflicts(self):
        """Identify conflict-of-interest patterns"""
        
        # Pattern 1: Person in multiple funds
        person_orgs = defaultdict(set)
        for rel in self.relationships:
            if rel.relationship_type in ['works_at', 'manages', 'leads']:
                person_orgs[rel.source_id].add(rel.target_id)
        
        for person_id, org_ids in person_orgs.items():
            if len(org_ids) > 1:
                self.conflicts['multiple_fund_roles'].append({
                    'person': person_id,
                    'organizations': list(org_ids)
                })
        
        # Pattern 2: Evaluator + beneficiary
        evaluators = set()
        beneficiaries = set()
        
        for rel in self.relationships:
            if rel.relationship_type == 'evaluates':
                evaluators.add(rel.source_id)
            elif rel.relationship_type in ['received_funding', 'beneficiary']:
                beneficiaries.add(rel.source_id)
        
        overlap = evaluators & beneficiaries
        for person_id in overlap:
            self.conflicts['evaluator_and_beneficiary'].append({
                'person': person_id
            })

    def export_to_json(self, output_path: Path):
        """Export all data as structured JSON"""
        entities_list = [asdict(e) for e in self.entities.values()]
        relationships_list = [asdict(r) for r in self.relationships]
        
        output = {
            "metadata": {
                "total_entities": len(self.entities),
                "total_relationships": len(self.relationships),
                "conflict_types": dict(self.conflicts)
            },
            "entities": entities_list,
            "relationships": relationships_list,
            "conflicts": dict(self.conflicts)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

# Usage example
if __name__ == "__main__":
    extractor = FilmGovernanceExtractor()
    
    # Sample text
    sample_text = """
    משה אדרי הוא מפיק סרטים בעל קשרים עמוקים עם קרן רבינוביץ.
    גיורא עיני מנכ"ל קרן רבינוביץ מאז 1995.
    יואב אברמוביץ עובד כלקטור בקרן רבינוביץ.
    הסרט "אני לא מאמין אני רובוט" (2015) קיבל מימון מקרן הקולנוע.
    """
    
    people = extractor.extract_people_from_text(sample_text)
    funds = extractor.extract_funds(sample_text)
    films = extractor.extract_films(sample_text)
    
    print(f"Found {len(people)} people, {len(funds)} funds, {len(films)} films")
