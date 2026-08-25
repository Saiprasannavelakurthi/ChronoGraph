from enum import Enum
from typing import List, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class EntityType(str, Enum):
    PERSON = "PERSON"
    USER = "USER"
    TEAM = "TEAM"
    ORGANIZATION = "ORGANIZATION"
    PROJECT = "PROJECT"
    REPOSITORY = "REPOSITORY"
    ISSUE = "ISSUE"
    TASK = "TASK"
    COMMIT = "COMMIT"
    PULL_REQUEST = "PULL_REQUEST"
    CHANNEL = "CHANNEL"
    MESSAGE = "MESSAGE"
    DOCUMENT = "DOCUMENT"
    SYSTEM = "SYSTEM"
    SERVICE = "SERVICE"
    OTHER = "OTHER"

    @classmethod
    def _missing_(cls, value: object) -> "EntityType":
        # Handle case-insensitive mapping or fallback to OTHER for unknown entity types
        if isinstance(value, str):
            val_upper = value.strip().upper()
            for member in cls:
                if member.value == val_upper:
                    return member
        return cls.OTHER


class RelationshipType(str, Enum):
    WORKED_ON = "WORKED_ON"
    CREATED = "CREATED"
    ASSIGNED_TO = "ASSIGNED_TO"
    ASSIGNED = "ASSIGNED"
    AUTHORED = "AUTHORED"
    MENTIONED = "MENTIONED"
    REVIEWED = "REVIEWED"
    COMMITTED = "COMMITTED"
    OPENED = "OPENED"
    CLOSED = "CLOSED"
    MERGED = "MERGED"
    PART_OF = "PART_OF"
    BELONGS_TO = "BELONGS_TO"
    DEPENDS_ON = "DEPENDS_ON"
    RELATED_TO = "RELATED_TO"
    PARTICIPATED_IN = "PARTICIPATED_IN"
    OTHER = "OTHER"

    @classmethod
    def _missing_(cls, value: object) -> "RelationshipType":
        if isinstance(value, str):
            val_upper = value.strip().upper().replace(" ", "_")
            for member in cls:
                if member.value == val_upper:
                    return member
        return cls.OTHER


class Entity(BaseModel):
    id: str = Field(..., description="Unique slug or normalized identifier for the entity")
    name: str = Field(..., description="Original or primary name of the entity")
    type: Union[EntityType, str] = Field(..., description="Category or entity type")

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v):
        if isinstance(v, str):
            try:
                return EntityType(v)
            except ValueError:
                return EntityType.OTHER
        return v


class Relationship(BaseModel):
    source: str = Field(..., description="Source entity name or ID")
    relation: Union[RelationshipType, str] = Field(..., description="Relationship type between source and target")
    target: str = Field(..., description="Target entity name or ID")

    @field_validator("relation", mode="before")
    @classmethod
    def validate_relation(cls, v):
        if isinstance(v, str):
            try:
                return RelationshipType(v)
            except ValueError:
                return RelationshipType.OTHER
        return v


class GraphTriple(BaseModel):
    subject: str = Field(..., description="Subject entity name or ID")
    predicate: str = Field(..., description="Predicate relationship type")
    object: str = Field(..., description="Object entity name or ID")

    @field_validator("predicate", mode="before")
    @classmethod
    def validate_predicate(cls, v):
        if isinstance(v, str):
            clean_p = v.strip().upper().replace(" ", "_")
            try:
                rel_enum = RelationshipType(clean_p)
                return rel_enum.value
            except ValueError:
                return RelationshipType.OTHER.value
        return str(v)


class GraphExtractionResult(BaseModel):
    entities: List[Entity] = Field(default_factory=list, description="Extracted entities")
    relationships: List[Relationship] = Field(default_factory=list, description="Extracted relationships")
    triples: List[GraphTriple] = Field(default_factory=list, description="Extracted graph triples")

    @model_validator(mode="after")
    def ensure_triples_populated(self) -> "GraphExtractionResult":
        """
        If triples array is empty but relationships exist, automatically generate
        corresponding graph triples (subject = source, predicate = relation, object = target).
        """
        if not self.triples and self.relationships:
            generated_triples = []
            for rel in self.relationships:
                rel_str = rel.relation.value if isinstance(rel.relation, Enum) else str(rel.relation)
                generated_triples.append(
                    GraphTriple(
                        subject=rel.source,
                        predicate=rel_str,
                        object=rel.target
                    )
                )
            self.triples = generated_triples
        return self
