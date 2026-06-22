# Operations — Backup & Restore (Neo4j edu)

> Nguồn: [project_state/2026-06-22-canonical.md](../project_state/2026-06-22-canonical.md) §Release gate ("Backup Neo4j verified") + [RUNBOOK.md](../RUNBOOK.md).
> 🔒 Creds Neo4j tham chiếu `.env` / `server.txt`, KHÔNG chép vào doc. Backtest/data state là phần của agent khác — đây chỉ là quy trình vận hành backup.

## Đối tượng backup

- **Neo4j edu** (container `edu_neo4j`, `bolt://localhost:7688` trên server) — chứa toàn bộ KnowledgeChunk / Concept / LiteraryWork / LiteratureText / `:Lesson` + edges (COVERS, ABOUT_WORK, VERBATIM_OF, PREREQ).
- **Code** `rag_server.py` được backup riêng bằng `.bak_<ngày>` (xem [rollback.md](rollback.md)) — không thuộc file này.

## Khi nào backup

- **Bắt buộc trước mỗi release/ingest** (gate: "Backup Neo4j verified").
- Trước bất kỳ thay đổi data diện rộng (migration schema, build campaign).

## A. Backup — `neo4j-admin dump` → Drive

```bash
# Trên server. DB thường offline khi dump (neo4j-admin dump cổ điển cần stop DB).
# Quy trình tổng quát (điều chỉnh theo phiên bản neo4j trong container):
#   1) (nếu cần) stop DB trong container edu_neo4j
#   2) neo4j-admin database dump neo4j --to-path=/backups
#      hoặc: neo4j-admin dump --database=neo4j --to=/backups/edu_<ngày>.dump
#   3) start lại DB
#   4) Đẩy file dump lên Google Drive (lưu ngoài server để chống mất ổ)
```

Xác minh dump:
- File `.dump` tồn tại, size hợp lý (không 0 byte).
- Ghi **ngày + git SHA release tương ứng** cạnh file trên Drive (truy vết được dump nào ứng release nào).

> ⚠️ Dump cổ điển cần DB **offline** → trùng cửa sổ low-traffic. Nếu container đang phục vụ truy vấn live, lên lịch + báo trước (giống restart prod).

## B. Restore — từ dump

```bash
# Trên server (DB phải offline khi load):
#   1) stop DB trong container
#   2) neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
#      hoặc: neo4j-admin load --from=/backups/edu_<ngày>.dump --database=neo4j --force
#   3) start lại DB
#   4) verify count cơ bản:
#      MATCH (k:KnowledgeChunk) WHERE k.production_ready=true RETURN count(k);   // kỳ vọng ~15K
#      MATCH (l:Lesson) RETURN count(l);
#      MATCH ()-[r:COVERS]->() RETURN count(r);
```

## C. Backup nhẹ thay thế (khi không thể offline DB)

- **Actor-tagged reversible** là lớp bảo vệ thứ hai: mọi node companion thêm vào đều có `<actor>` tag → có thể gỡ đúng phần đó bằng `MATCH (n) WHERE n.<actor>='...' DETACH DELETE n` mà không cần restore toàn DB (xem [rollback.md](rollback.md) §B).
- Export Cypher của subgraph cụ thể (`apoc.export.cypher.*` nếu APOC có) cho phần data nhỏ.

## Checklist nhanh trước release

```
[ ] Dump Neo4j mới tạo (size > 0, ngày đúng)
[ ] Dump đã đẩy lên Drive (ngoài server)
[ ] Ghi git SHA + run-id backtest cạnh dump
[ ] Đã test lệnh restore (ít nhất biết cú pháp cho phiên bản hiện tại)
```

---
Liên quan: [release-checklist.md](release-checklist.md) · [rollback.md](rollback.md) · [canary-prod-ports.md](canary-prod-ports.md) · [RUNBOOK.md](../RUNBOOK.md)
