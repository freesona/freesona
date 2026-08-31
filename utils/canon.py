#!/usr/bin/env python3

# utils/canon.py: Canon Framework — Modular, immutable character definition.


# The Canon Framework replaces the monolithic persona prompt with

# structured, authored components that explain WHY a character behaves

# as they do, not merely WHAT they do.


# Components:

#   - Core Identity: Who the character fundamentally is (name, origin, nature)

#   - Core Beliefs: Foundational convictions that drive decisions

#   - Motivations: What the character wants and why

#   - Behavioral Rules: Explicit constraints on behavior (do/don't)

#   - World Assumptions: What the character takes for granted about their world

#   - Canon Explanations: The "why" behind rules, beliefs, and behaviors


# All components are IMMUTABLE, AUTHORED (never learned), and VERSIONED.

# This enforces the Canonical Truth Invariant: only Canon and PKB define truth.



from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import aiosqlite

from utils.config import load_config

logger = logging.getLogger("FreesonaBot")





# ---------------------------------------------------------------------------

# Config

# ---------------------------------------------------------------------------





def _get_canon_file_path() -> str:

    """Get the canon database file path (reads env

    each call for testability)."""

    return os.getenv("CANON_FILE_PATH", "./canon.db")





def _get_canon_version() -> str:

    """Get the current canon version from config."""

    return load_config().get("canon_version", "1.0.0")





# Module-level constant (evaluated at import for backward compat)

CANON_FILE_PATH = _get_canon_file_path()





# ---------------------------------------------------------------------------

# Canon Component Types

# ---------------------------------------------------------------------------





class CanonComponentType(Enum):

    """Types of canon components. Order reflects assembly

    priority within Canon."""



    CORE_IDENTITY = "core_identity"

    CORE_BELIEFS = "core_beliefs"

    MOTIVATIONS = "motivations"

    BEHAVIORAL_RULES = "behavioral_rules"

    WORLD_ASSUMPTIONS = "world_assumptions"

    CANON_EXPLANATIONS = "canon_explanations"





# Assembly order within canon block (lower = earlier in prompt)

COMPONENT_ASSEMBLY_ORDER = [

    CanonComponentType.CORE_IDENTITY,

    CanonComponentType.CORE_BELIEFS,

    CanonComponentType.MOTIVATIONS,

    CanonComponentType.BEHAVIORAL_RULES,

    CanonComponentType.WORLD_ASSUMPTIONS,

    CanonComponentType.CANON_EXPLANATIONS,

]





COMPONENT_LABELS = {

    CanonComponentType.CORE_IDENTITY: "Core Identity",

    CanonComponentType.CORE_BELIEFS: "Core Beliefs",

    CanonComponentType.MOTIVATIONS: "Motivations",

    CanonComponentType.BEHAVIORAL_RULES: "Behavioral Rules",

    CanonComponentType.WORLD_ASSUMPTIONS: "World Assumptions",

    CanonComponentType.CANON_EXPLANATIONS: "Canon Explanations",

}





COMPONENT_XML_TAGS = {

    CanonComponentType.CORE_IDENTITY: "core_identity",

    CanonComponentType.CORE_BELIEFS: "core_beliefs",

    CanonComponentType.MOTIVATIONS: "motivations",

    CanonComponentType.BEHAVIORAL_RULES: "behavioral_rules",

    CanonComponentType.WORLD_ASSUMPTIONS: "world_assumptions",

    CanonComponentType.CANON_EXPLANATIONS: "canon_explanations",

}





# ---------------------------------------------------------------------------

# Canon Component Data Class

# ---------------------------------------------------------------------------





@dataclass

class CanonComponent:

    """A single authored canon component."""



    component_id: str

    persona_id: str

    component_type: CanonComponentType

    content: str

    explanation: str = (

        ""  # The "why" — required for behavioral_rules, optional for others

    )

    version: str = "1.0.0"

    author: str = "system"

    timestamp: str = field(

        default_factory=lambda: datetime.now(timezone.utc).isoformat()

    )

    metadata: dict[str, Any] = field(default_factory=dict)



    def to_dict(self) -> dict[str, Any]:

        return {

            "component_id": self.component_id,

            "persona_id": self.persona_id,

            "component_type": self.component_type.value,

            "content": self.content,

            "explanation": self.explanation,

            "version": self.version,

            "author": self.author,

            "timestamp": self.timestamp,

            "metadata": self.metadata,

        }



    @classmethod

    def from_row(cls, row: aiosqlite.Row) -> CanonComponent:

        return cls(

            component_id=row["component_id"],

            persona_id=row["persona_id"],

            component_type=CanonComponentType(row["component_type"]),

            content=row["content"],

            explanation=row["explanation"] or "",

            version=row["version"],

            author=row["author"],

            timestamp=row["timestamp"],

            metadata=json.loads(row["metadata"] or "{}"),

        )



    def format_for_prompt(self) -> str:

        """Format this component for inclusion in the system prompt."""

        tag = COMPONENT_XML_TAGS[self.component_type]

        lines = [

            f"<{tag}>",

            self.content.strip(),

            *(

                [f"\n<!-- Why: {self.explanation.strip()} -->"]

                if self.explanation

                else []

            ),

            f"</{tag}>",

        ]

        return "\n".join(lines)





# ---------------------------------------------------------------------------

# Canon Snapshot (for versioning/rollback)

# ---------------------------------------------------------------------------





@dataclass

class CanonSnapshot:

    """A complete snapshot of a persona's canon at a point in time."""



    snapshot_id: str

    persona_id: str

    version: str

    components: list[CanonComponent]

    timestamp: str

    author: str

    description: str = ""



    def to_dict(self) -> dict[str, Any]:

        return {

            "snapshot_id": self.snapshot_id,

            "persona_id": self.persona_id,

            "version": self.version,

            "components": [c.to_dict() for c in self.components],

            "timestamp": self.timestamp,

            "author": self.author,

            "description": self.description,

        }





# ---------------------------------------------------------------------------

# Database Initialization

# ---------------------------------------------------------------------------





async def init_db():

    """Initialize the canon database with tables and indexes."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        # Canon components table

        await db.execute("""

            CREATE TABLE IF NOT EXISTS canon_components (

                component_id    TEXT PRIMARY KEY,

                persona_id      TEXT NOT NULL,

                component_type  TEXT NOT NULL,

                content         TEXT NOT NULL,

                explanation     TEXT DEFAULT '',

                version         TEXT NOT NULL,

                author          TEXT NOT NULL,

                timestamp       TEXT NOT NULL,

                metadata        TEXT DEFAULT '{}'

            )

        """)

        await db.execute("""

            CREATE INDEX IF NOT EXISTS idx_canon_persona_type

            ON canon_components (persona_id, component_type)

        """)



        # Canon snapshots table (for versioning/rollback)

        await db.execute("""

            CREATE TABLE IF NOT EXISTS canon_snapshots (

                snapshot_id   TEXT PRIMARY KEY,

                persona_id    TEXT NOT NULL,

                version       TEXT NOT NULL,

                components    TEXT NOT NULL,  -- JSON array of component dicts

                timestamp     TEXT NOT NULL,

                author        TEXT NOT NULL,

                description   TEXT DEFAULT ''

            )

        """)

        await db.execute("""

            CREATE INDEX IF NOT EXISTS idx_canon_snapshots_persona

            ON canon_snapshots (persona_id, timestamp DESC)

        """)



        await db.commit()





# ---------------------------------------------------------------------------

# Canon Storage Operations

# ---------------------------------------------------------------------------





async def store_component(component: CanonComponent) -> None:

    """Store a new canon component."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        await db.execute(

            """

            INSERT INTO canon_components (

                component_id, persona_id, component_type, content,

                explanation, version, author, timestamp, metadata

            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

        """,

            (

                component.component_id,

                component.persona_id,

                component.component_type.value,

                component.content,

                component.explanation,

                component.version,

                component.author,

                component.timestamp,

                json.dumps(component.metadata),

            ),

        )

        await db.commit()





async def update_component(component: CanonComponent) -> None:

    """Update an existing canon component."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        await db.execute(

            """

            UPDATE canon_components

            SET content = ?, explanation = ?, version = ?, author = ?,

                timestamp = ?, metadata = ?

            WHERE component_id = ?

        """,

            (

                component.content,

                component.explanation,

                component.version,

                component.author,

                component.timestamp,

                json.dumps(component.metadata),

                component.component_id,

            ),

        )

        await db.commit()





async def delete_component(component_id: str) -> None:

    """Delete a canon component by ID."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        await db.execute(

            "DELETE FROM canon_components WHERE component_id = ?",

            (component_id,),

        )

        await db.commit()





async def get_components(persona_id: str) -> list[CanonComponent]:

    """Retrieve all canon components for a persona,

    ordered by assembly priority."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(

            """

            SELECT * FROM canon_components

            WHERE persona_id = ?

            ORDER BY

                CASE component_type

                    WHEN 'core_identity' THEN 1

                    WHEN 'core_beliefs' THEN 2

                    WHEN 'motivations' THEN 3

                    WHEN 'behavioral_rules' THEN 4

                    WHEN 'world_assumptions' THEN 5

                    WHEN 'canon_explanations' THEN 6

                    ELSE 99

                END

        """,

            (persona_id,),

        ) as cursor:

            rows = await cursor.fetchall()

            return [CanonComponent.from_row(row) for row in rows]





async def get_component(component_id: str) -> CanonComponent | None:

    """Retrieve a single canon component by ID."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(

            "SELECT * FROM canon_components WHERE component_id = ?",

            (component_id,),

        ) as cursor:

            row = await cursor.fetchone()

            return CanonComponent.from_row(row) if row else None





async def get_components_by_type(

    persona_id: str, component_type: CanonComponentType

) -> list[CanonComponent]:

    """Retrieve canon components of a specific type for a persona."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(

            """

            SELECT * FROM canon_components

            WHERE persona_id = ? AND component_type = ?

        """,

            (persona_id, component_type.value),

        ) as cursor:

            rows = await cursor.fetchall()

            return [CanonComponent.from_row(row) for row in rows]





# ---------------------------------------------------------------------------

# Snapshot Operations (Versioning)

# ---------------------------------------------------------------------------





async def create_snapshot(

    persona_id: str, version: str, author: str, description: str = ""

) -> CanonSnapshot:

    """Create a versioned snapshot of the current canon for a persona."""

    components = await get_components(persona_id)



    snapshot = CanonSnapshot(

        snapshot_id=str(uuid.uuid4()),

        persona_id=persona_id,

        version=version,

        components=components,

        timestamp=datetime.now(timezone.utc).isoformat(),

        author=author,

        description=description,

    )



    async with aiosqlite.connect(_get_canon_file_path()) as db:

        await db.execute(

            """

            INSERT INTO canon_snapshots (

                snapshot_id, persona_id, version, components,

                timestamp, author, description

            ) VALUES (?, ?, ?, ?, ?, ?, ?)

        """,

            (

                snapshot.snapshot_id,

                snapshot.persona_id,

                snapshot.version,

                json.dumps([c.to_dict() for c in snapshot.components]),

                snapshot.timestamp,

                snapshot.author,

                snapshot.description,

            ),

        )

        await db.commit()



    return snapshot





async def get_snapshots(persona_id: str, limit: int = 10) -> list[CanonSnapshot]:

    """Get recent snapshots for a persona."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(

            """

            SELECT * FROM canon_snapshots

            WHERE persona_id = ?

            ORDER BY timestamp DESC

            LIMIT ?

        """,

            (persona_id, limit),

        ) as cursor:

            rows = await cursor.fetchall()

            snapshots = []

            for row in rows:

                components = [

                    CanonComponent(

                        component_id=c["component_id"],

                        persona_id=c["persona_id"],

                        component_type=CanonComponentType(c["component_type"]),

                        content=c["content"],

                        explanation=c.get("explanation", ""),

                        version=c["version"],

                        author=c["author"],

                        timestamp=c["timestamp"],

                        metadata=c.get("metadata", {}),

                    )

                    for c in json.loads(row["components"])

                ]

                snapshots.append(

                    CanonSnapshot(

                        snapshot_id=row["snapshot_id"],

                        persona_id=row["persona_id"],

                        version=row["version"],

                        components=components,

                        timestamp=row["timestamp"],

                        author=row["author"],

                        description=row["description"] or "",

                    )

                )

            return snapshots





async def restore_snapshot(snapshot_id: str) -> bool:

    """Restore canon from a snapshot. Returns True if successful."""

    async with aiosqlite.connect(_get_canon_file_path()) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(

            "SELECT * FROM canon_snapshots WHERE snapshot_id = ?",

            (snapshot_id,),

        ) as cursor:

            row = await cursor.fetchone()

            if not row:

                return False



            # Delete current components for this persona

            await db.execute(

                "DELETE FROM canon_components WHERE persona_id = ?",

                (row["persona_id"],),

            )



            # Restore components from snapshot

            components = json.loads(row["components"])

            for c in components:

                await db.execute(

                    """

                    INSERT INTO canon_components (

                        component_id, persona_id, component_type, content,

                        explanation, version, author, timestamp, metadata

                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

                """,

                    (

                        c["component_id"],

                        c["persona_id"],

                        c["component_type"],

                        c["content"],

                        c.get("explanation", ""),

                        c["version"],

                        c["author"],

                        c["timestamp"],

                        json.dumps(c.get("metadata", {})),

                    ),

                )

            await db.commit()

            return True





# ---------------------------------------------------------------------------

# Context Assembly for PromptBuilder

# ---------------------------------------------------------------------------





async def build_canon_context(persona_id: str) -> str:

    """

    Build the canon context block for PromptBuilder.



    Returns formatted string with all canon components assembled

    in priority order. Each component includes its explanation

    (the "why") as an XML comment.

    """

    if not persona_id or not persona_id.strip():

        return ""



    components = await get_components(persona_id)



    if not components:

        return ""



    lines = ["\n[Canon Definition]"]



    for component in components:

        lines.append(component.format_for_prompt())



    return "\n".join(lines)





# ---------------------------------------------------------------------------

# Default Canon Creation (for new personas)

# ---------------------------------------------------------------------------



DEFAULT_CANON_TEMPLATES: dict[CanonComponentType, dict[str, str]] = {

    CanonComponentType.CORE_IDENTITY: {

        "content": "",

        "explanation": (

            "The fundamental identity of the character — name, origin, "

            "essential nature. This is who they are at the deepest level, "

            "unchanging across situations."

        ),

    },

    CanonComponentType.CORE_BELIEFS: {

        "content": "",

        "explanation": (

            "Foundational convictions that the character holds as true. "

            "These are not opinions — they are the axioms from which the "

            "character reasons."

        ),

    },

    CanonComponentType.MOTIVATIONS: {

        "content": "",

        "explanation": (

            "What the character wants and WHY they want it. Motivation "

            "explains the driving force behind actions, not just the "

            "actions themselves."

        ),

    },

    CanonComponentType.BEHAVIORAL_RULES: {

        "content": "",

        "explanation": (

            "Explicit behavioral constraints with reasoning. Format: "

            "'Rule: [what]. Reason: [why].' The explanation is mandatory "

            "for behavioral rules — it prevents canon drift by making the "

            "rationale auditable."

        ),

    },

    CanonComponentType.WORLD_ASSUMPTIONS: {

        "content": "",

        "explanation": (

            "What the character takes for granted about how their world "

            "works. These are not beliefs the character chose — they are "

            "the character's lived reality."

        ),

    },

    CanonComponentType.CANON_EXPLANATIONS: {

        "content": "",

        "explanation": (

            "Deep-dive explanations for key aspects of the character that "

            "don't fit in other categories. E.g., 'Why Chisato refuses "

            "lethal force: [detailed philosophical/personal history].' "

            "This is the 'author's notes' layer."

        ),

    },

}





async def ensure_default_canon(persona_id: str, author: str = "system") -> None:

    """Create empty default canon components for a new

    persona if none exist."""

    existing = await get_components(persona_id)

    if existing:

        return



    for comp_type in COMPONENT_ASSEMBLY_ORDER:

        template = DEFAULT_CANON_TEMPLATES[comp_type]

        component = CanonComponent(

            component_id=str(uuid.uuid4()),

            persona_id=persona_id,

            component_type=comp_type,

            content=template["content"],

            explanation=template["explanation"],

            version=_get_canon_version(),

            author=author,

        )

        await store_component(component)



    # Create initial snapshot

    await create_snapshot(

        persona_id, _get_canon_version(), author, "Initial canon creation"

    )





# ---------------------------------------------------------------------------

# Canon Validation (Canonical Truth Invariant Enforcement)

# ---------------------------------------------------------------------------





class CanonValidationError(Exception):

    """Raised when canon content violates architectural invariants."""





def validate_canon_component(component: CanonComponent) -> list[str]:

    """

    Validate a canon component for architectural compliance.



    Returns list of warnings (non-fatal) and raises

    CanonValidationError for violations.

    """

    warnings = []



    # Enforce explanation requirement for behavioral rules

    if component.component_type == CanonComponentType.BEHAVIORAL_RULES and (

        not component.explanation or not component.explanation.strip()

    ):

        raise CanonValidationError(

            f"BEHAVIORAL_RULES component {component.component_id} "

            "MUST have an explanation. The 'why' is required to "

            "prevent canon drift."

        )



    # Warn if explanation missing for other types (encouraged but not required)

    if component.component_type != CanonComponentType.BEHAVIORAL_RULES and (

        not component.explanation or not component.explanation.strip()

    ):

        warnings.append(

            f"Component {component.component_id} "

            f"({component.component_type.value}) "

            "should include an explanation (the 'why')."

        )



    # Check for canonical truth violation patterns (heuristic)

    content_lower = component.content.lower()

    prohibited_patterns = [

        "we promised",

        "we agreed",

        "we decided",

        "we experienced",

        "the user",

        "the user said",

        "the user likes",

        "the user dislikes",

        "conversation",

        "chat history",

        "recently",

        "last time",

        "in this server",

        "in this channel",

        "guild",

        "discord",

    ]

    for pattern in prohibited_patterns:

        if pattern in content_lower:

            warnings.append(

                f"Component {component.component_id} may violate "

                f"Canonical Truth Invariant: contains '{pattern}' — "

                "this sounds like Character Memory, User Memory, "

                "Conversation History, or Guild Context, not Canon."

            )



    return warnings





# ---------------------------------------------------------------------------

# Canon Export/Import (for portability)

# ---------------------------------------------------------------------------





async def export_canon(persona_id: str) -> dict[str, Any]:

    """Export complete canon for a persona as a portable dictionary."""

    components = await get_components(persona_id)

    snapshots = await get_snapshots(persona_id, limit=5)

    return {

        "persona_id": persona_id,

        "version": _get_canon_version(),

        "exported_at": datetime.now(timezone.utc).isoformat(),

        "components": [c.to_dict() for c in components],

        "snapshots": [s.to_dict() for s in snapshots],

    }





async def import_canon(

    data: dict[str, Any], target_persona_id: str, author: str = "import"

) -> int:

    """Import canon from exported data to a target persona.

    Returns count of components imported."""

    if not target_persona_id:

        raise ValueError("Target persona_id is required for import")



    count = 0

    for comp_data in data.get("components", []):

        # Generate new component ID to avoid conflicts, use target persona_id

        component = CanonComponent(

            component_id=str(uuid.uuid4()),

            persona_id=target_persona_id,

            component_type=CanonComponentType(comp_data["component_type"]),

            content=comp_data["content"],

            explanation=comp_data.get("explanation", ""),

            version=comp_data["version"],

            author=comp_data["author"],

            timestamp=comp_data["timestamp"],

            metadata=comp_data.get("metadata", {}),

        )

        # Validate before import

        validate_canon_component(component)

        await store_component(component)

        count += 1



    # Create import snapshot

    await create_snapshot(

        target_persona_id,

        _get_canon_version(),

        author,

        f"Imported {count} components",

    )



    return count





__all__ = [

    "COMPONENT_ASSEMBLY_ORDER",

    "COMPONENT_LABELS",

    "COMPONENT_XML_TAGS",

    "DEFAULT_CANON_TEMPLATES",

    "CanonComponent",

    "CanonComponentType",

    "CanonSnapshot",

    "CanonValidationError",

    "build_canon_context",

    "create_snapshot",

    "delete_component",

    "ensure_default_canon",

    "export_canon",

    "get_component",

    "get_components",

    "get_components_by_type",

    "get_snapshots",

    "import_canon",

    "init_db",

    "restore_snapshot",

    "store_component",

    "update_component",

    "validate_canon_component",

]

