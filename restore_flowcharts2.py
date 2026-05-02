"""
Recovery script v2: inspect oplog v2 diffs to find overwrite point and recover data.
"""
import asyncio
import time
import json
from bson import Timestamp
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb://localhost:27017"
DB_NAME = "audit_dashboard"
COLLECTION = "flowcharts"

async def main():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]

    # Map MongoDB _id to app chart id
    print("--- Mapping MongoDB _id to chart id ---")
    flowcharts = await db[COLLECTION].find({}).to_list(length=100)
    for fc in flowcharts:
        print(f"  MongoDB _id: {fc['_id']}  ->  chart id: {fc.get('id')}  name: {fc.get('name')}")

    # Get oplog entries
    two_hours_ago = int(time.time()) - 7200
    ts_filter = Timestamp(two_hours_ago, 0)

    local_db = client["local"]
    oplog = local_db["oplog.rs"]

    cursor = oplog.find({
        "ns": f"{DB_NAME}.{COLLECTION}",
        "ts": {"$gte": ts_filter},
    }).sort("ts", 1)  # oldest first for replay

    ops = await cursor.to_list(length=5000)
    print(f"\nTotal oplog entries: {len(ops)}")

    # Group by MongoDB _id
    by_id = {}
    for op in ops:
        oid = str(op.get("o2", {}).get("_id", "unknown"))
        by_id.setdefault(oid, []).append(op)

    print(f"Unique document IDs: {list(by_id.keys())}")

    # For each document, inspect the diffs
    for oid, doc_ops in by_id.items():
        print(f"\n=== Document {oid}: {len(doc_ops)} ops ===")

        for i, op in enumerate(doc_ops):
            ts = op.get("ts")
            diff = op.get("o", {}).get("diff", {})

            # Look for significant changes (nodes/edges being replaced)
            summary = []
            if "u" in diff:
                # Top-level field updates
                updated_fields = list(diff["u"].keys())
                summary.append(f"updated: {updated_fields}")

            if "d" in diff:
                summary.append(f"deleted: {list(diff['d'].keys())}")

            # Check for sub-document diffs (s prefix = sub-doc)
            for key in diff:
                if key.startswith("s"):
                    field_name = key[1:]  # e.g., "snodes" -> "nodes"
                    sub_diff = diff[key]
                    if isinstance(sub_diff, dict):
                        sub_summary = []
                        if "u" in sub_diff:
                            sub_summary.append(f"updated {len(sub_diff['u'])} fields")
                        if "d" in sub_diff:
                            sub_summary.append(f"deleted {len(sub_diff['d'])} fields")
                        if "i" in sub_diff:
                            sub_summary.append(f"inserted {len(sub_diff['i'])} items")
                        # Array diffs use numeric keys
                        arr_ops = [k for k in sub_diff if k.startswith("s") or k.startswith("u")]
                        if arr_ops:
                            sub_summary.append(f"array ops: {len(arr_ops)}")
                        summary.append(f"{field_name}: {', '.join(sub_summary) if sub_summary else list(sub_diff.keys())}")

            ts_local = time.strftime('%H:%M:%S', time.localtime(ts.time))
            if summary:
                print(f"  [{i:3d}] {ts_local} | {'; '.join(summary)}")

            # CRITICAL: Look for complete node/edge replacements
            # In v2 diff, a full array replacement shows up differently
            o_doc = op.get("o", {})
            if "$set" in o_doc:
                set_keys = list(o_doc["$set"].keys())
                print(f"  [{i:3d}] {ts_local} | $set: {set_keys}")
                if "nodes" in o_doc["$set"]:
                    nodes = o_doc["$set"]["nodes"]
                    print(f"         FULL NODES REPLACEMENT: {len(nodes)} nodes")
                    for n in nodes:
                        print(f"           {n.get('id')} type={n.get('type')} text={n.get('data',{}).get('text','')[:40]}")

            # Print raw diff for the first few and any that look like overwrites
            if i < 3 or i == len(doc_ops) - 1:
                # Compact print
                diff_str = json.dumps(diff, default=str)
                if len(diff_str) > 500:
                    print(f"         diff (truncated): {diff_str[:500]}...")
                else:
                    print(f"         diff: {diff_str}")

    # Also check: are there ops for the SECOND chart (test)?
    print("\n\n--- Checking for second chart document ops ---")
    for fc in flowcharts:
        oid = str(fc["_id"])
        count = by_id.get(oid, [])
        print(f"  {fc.get('name')} ({fc.get('id')}): MongoDB _id={oid}, ops={len(count)}")

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
