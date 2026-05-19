#!/usr/bin/env python3
"""
Audit and repair the PTalk Neo4j education graph.

Default mode is read-only. Use --apply to write the repair fields/relations:
- normalize lookup fields for title/url
- link LiteratureText/Summary nodes to their Unit through matching LessonGuide urls
- propagate LessonGuide.series into bo_sach for LessonGuide/FullDocument/Section

This script intentionally avoids deleting or merging nodes.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from neo4j import GraphDatabase


DEFAULT_URI = "bolt://171.226.10.121:9100"
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "edu_graph_2026"


def normalize_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@dataclass
class RepairStats:
    label: str
    matched: int = 0
    changed: int = 0


class Neo4jRepair:
    def __init__(self, uri: str, user: str, password: str, apply: bool):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.apply = apply

    def close(self) -> None:
        self.driver.close()

    def scalar(self, cypher: str, **params: Any) -> Any:
        with self.driver.session() as session:
            return session.run(cypher, **params).single()[0]

    def rows(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        with self.driver.session() as session:
            return [dict(row) for row in session.run(cypher, **params)]

    def write(self, cypher: str, **params: Any) -> int:
        if not self.apply:
            return 0
        with self.driver.session() as session:
            result = session.run(cypher, **params)
            summary = result.consume()
            return summary.counters.properties_set + summary.counters.relationships_created

    def print_core_audit(self) -> None:
        print("=== Core Counts ===")
        for label in [
            "Grade", "Subject", "BookSeries", "Unit", "LessonGuide",
            "LiteratureText", "Summary", "KnowledgeObject", "FullDocument",
            "Section", "ContentBlock", "ReadingText", "RecitationSegment",
            "KnowledgeChunk",
        ]:
            count = self.scalar(f"MATCH (n:`{label}`) RETURN count(n)")
            if count:
                print(f"{label}: {count}")

        print("\n=== Broken/Important Coverage ===")
        checks = {
            "orphan_literature": """
                MATCH (lt:LiteratureText)
                WHERE NOT (:Unit)-[:HAS_LITERATURE]->(lt)
                RETURN count(lt)
            """,
            "orphan_summary": """
                MATCH (sm:Summary)
                WHERE NOT (:Unit)-[:HAS_SUMMARY]->(sm)
                RETURN count(sm)
            """,
            "legacy_lessons_with_series": """
                MATCH (lg:LessonGuide)
                WHERE lg.series IS NOT NULL AND (lg.bo_sach IS NULL OR lg.bo_sach = 'LEGACY')
                RETURN count(lg)
            """,
            "legacy_full_documents_with_source_series": """
                MATCH (lg:LessonGuide)-[:EXTRACTED_TO]->(:KnowledgeObject)-[:HAS_FULL_DOCUMENT]->(fd:FullDocument)
                WHERE lg.series IS NOT NULL AND (fd.bo_sach IS NULL OR fd.bo_sach = 'LEGACY')
                RETURN count(fd)
            """,
            "sections_missing_embedding": """
                MATCH (s:Section)
                WHERE s.embedding IS NULL
                RETURN count(s)
            """,
            "knowledge_chunks": """
                MATCH (c:KnowledgeChunk)
                RETURN count(c)
            """,
        }
        for name, cypher in checks.items():
            print(f"{name}: {self.scalar(cypher)}")

    def normalize_lookup_fields(self) -> list[RepairStats]:
        stats: list[RepairStats] = []
        for label in ["Unit", "LessonGuide", "LiteratureText", "Summary", "FullDocument", "ReadingText"]:
            rows = self.rows(
                f"""
                MATCH (n:`{label}`)
                RETURN elementId(n) AS eid, n.title AS title, n.work_name AS work_name,
                       n.url AS url, n.search_title AS search_title, n.search_url AS search_url
                """
            )
            changed = 0
            for row in rows:
                search_title = normalize_text(row.get("title") or row.get("work_name"))
                search_url = normalize_text(row.get("url"))
                if row.get("search_title") != search_title or row.get("search_url") != search_url:
                    changed += 1
                    self.write(
                        """
                        MATCH (n) WHERE elementId(n) = $eid
                        SET n.search_title = $search_title,
                            n.search_url = $search_url
                        """,
                        eid=row["eid"],
                        search_title=search_title,
                        search_url=search_url,
                    )
            stats.append(RepairStats(label=label, matched=len(rows), changed=changed))
        return stats

    def repair_relations_and_books(self) -> dict[str, int]:
        planned = {
            "literature_orphans_to_link": self.scalar(
                """
                MATCH (lt:LiteratureText)
                WHERE NOT (:Unit)-[:HAS_LITERATURE]->(lt)
                RETURN count(lt)
                """
            ),
            "summary_orphans_to_link": self.scalar(
                """
                MATCH (sm:Summary)
                WHERE NOT (:Unit)-[:HAS_SUMMARY]->(sm)
                RETURN count(sm)
                """
            ),
            "lesson_bo_sach_from_series": self.scalar(
                """
                MATCH (lg:LessonGuide)
                WHERE lg.series IS NOT NULL AND (lg.bo_sach IS NULL OR lg.bo_sach = 'LEGACY')
                RETURN count(lg)
                """
            ),
            "full_document_bo_sach_from_source": self.scalar(
                """
                MATCH (lg:LessonGuide)-[:EXTRACTED_TO]->(:KnowledgeObject)-[:HAS_FULL_DOCUMENT]->(fd:FullDocument)
                WHERE lg.series IS NOT NULL AND (fd.bo_sach IS NULL OR fd.bo_sach = 'LEGACY')
                RETURN count(fd)
                """
            ),
        }

        self.write(
            """
            MATCH (lt:LiteratureText)
            MATCH (lg:LessonGuide {url: lt.url})<-[:HAS_LESSON]-(u:Unit)
            MERGE (u)-[:HAS_LITERATURE]->(lt)
            SET lt.bo_sach = coalesce(lt.bo_sach, lt.series),
                lt.subject = coalesce(lt.subject, 'ngu_van')
            """
        )
        self.write(
            """
            MATCH (lt:LiteratureText)
            WHERE NOT (:Unit)-[:HAS_LITERATURE]->(lt)
            MERGE (u:Unit {
                work_name: coalesce(lt.title, lt.url),
                series: coalesce(lt.series, 'LEGACY')
            })
            SET u.title = coalesce(u.title, lt.title),
                u.bo_sach = coalesce(u.bo_sach, lt.series),
                u.source = coalesce(u.source, 'repair_from_literature_text')
            MERGE (u)-[:HAS_LITERATURE]->(lt)
            SET lt.bo_sach = coalesce(lt.bo_sach, lt.series),
                lt.subject = coalesce(lt.subject, 'ngu_van')
            WITH u, lt
            MATCH (b:BookSeries {code: lt.series})
            MERGE (b)-[:HAS_UNIT]->(u)
            """
        )
        self.write(
            """
            MATCH (sm:Summary)
            MATCH (lg:LessonGuide {url: sm.url})<-[:HAS_LESSON]-(u:Unit)
            MERGE (u)-[:HAS_SUMMARY]->(sm)
            SET sm.bo_sach = coalesce(sm.bo_sach, sm.series),
                sm.subject = coalesce(sm.subject, 'ngu_van')
            """
        )
        self.write(
            """
            MATCH (sm:Summary)
            WHERE NOT (:Unit)-[:HAS_SUMMARY]->(sm)
            MERGE (u:Unit {
                work_name: coalesce(sm.title, sm.url),
                series: coalesce(sm.series, 'LEGACY')
            })
            SET u.title = coalesce(u.title, sm.title),
                u.bo_sach = coalesce(u.bo_sach, sm.series),
                u.source = coalesce(u.source, 'repair_from_summary')
            MERGE (u)-[:HAS_SUMMARY]->(sm)
            SET sm.bo_sach = coalesce(sm.bo_sach, sm.series),
                sm.subject = coalesce(sm.subject, 'ngu_van')
            WITH u, sm
            MATCH (b:BookSeries {code: sm.series})
            MERGE (b)-[:HAS_UNIT]->(u)
            """
        )
        self.write(
            """
            MATCH (lg:LessonGuide)
            WHERE lg.series IS NOT NULL AND (lg.bo_sach IS NULL OR lg.bo_sach = 'LEGACY')
            SET lg.bo_sach = lg.series
            """
        )
        self.write(
            """
            MATCH (lg:LessonGuide)-[:EXTRACTED_TO]->(:KnowledgeObject)-[:HAS_FULL_DOCUMENT]->(fd:FullDocument)
            WHERE lg.series IS NOT NULL AND (fd.bo_sach IS NULL OR fd.bo_sach = 'LEGACY')
            SET fd.bo_sach = lg.series
            WITH fd
            MATCH (fd)-[:HAS_SECTION]->(s:Section)
            SET s.bo_sach = fd.bo_sach
            """
        )
        return planned

    def show_nho_rung(self) -> None:
        print("\n=== Nhớ Rừng Candidates ===")
        rows = self.rows(
            """
            MATCH (n)
            WHERE coalesce(n.url, '') CONTAINS 'nho-rung'
               OR coalesce(n.search_title, '') CONTAINS 'nho rung'
               OR coalesce(n.search_url, '') CONTAINS 'nho rung'
            RETURN labels(n) AS labels, n.title AS title, n.work_name AS work_name,
                   n.grade AS grade, coalesce(n.bo_sach, n.series) AS book,
                   n.document_type AS document_type,
                   size(coalesce(n.full_text, n.original_text, n.content, n.text, '')) AS len,
                   n.url AS url
            ORDER BY len DESC
            LIMIT 20
            """
        )
        for row in rows:
            print(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--apply", action="store_true", help="write non-destructive repairs")
    args = parser.parse_args()

    repair = Neo4jRepair(args.uri, args.user, args.password, apply=args.apply)
    try:
        print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        repair.print_core_audit()

        print("\n=== Normalize Lookup Fields ===")
        for stat in repair.normalize_lookup_fields():
            print(f"{stat.label}: scanned={stat.matched}, would_change={stat.changed}")

        print("\n=== Relation/Book Repairs ===")
        for name, count in repair.repair_relations_and_books().items():
            print(f"{name}: would_change={count}")

        repair.show_nho_rung()
    finally:
        repair.close()


if __name__ == "__main__":
    main()
