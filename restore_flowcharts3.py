"""
Recovery v3: dump full diffs for the node-changing ops to find original Ievo data.
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

    two_hours_ago = int(time.time()) - 7200
    ts_filter = Timestamp(two_hours_ago, 0)
    local_db = client["local"]
    oplog = local_db["oplog.rs"]

    cursor = oplog.find({
        "ns": f"{DB_NAME}.{COLLECTION}",
        "ts": {"$gte": ts_filter},
    }).sort("ts", 1)

    ops = await cursor.to_list(length=5000)

    # Print FULL content for ops that changed nodes or edges
    print("=== Ops that changed nodes/edges (full dump) ===\n")
    for i, op in enumerate(ops):
        diff = op.get("o", {}).get("diff", {})
        u_fields = diff.get("u", {})
        if "nodes" in u_fields or "edges" in u_fields:
            ts = op.get("ts")
            ts_local = time.strftime('%H:%M:%S', time.localtime(ts.time))
            print(f"\n--- Op [{i}] at {ts_local} ---")

            if "nodes" in u_fields:
                nodes = u_fields["nodes"]
                print(f"NODES ({len(nodes)} total):")
                print(json.dumps(nodes, indent=2, default=str))

            if "edges" in u_fields:
                edges = u_fields["edges"]
                print(f"\nEDGES ({len(edges)} total):")
                print(json.dumps(edges, indent=2, default=str))

    # Also check: what was the FIRST op's state?
    # The ops before index 80 only updated `updated_at`, meaning nodes were unchanged.
    # So the node data from op[80] is what REPLACED the original Ievo data.
    # The original data is what was in the DB BEFORE op[80].

    # Let's also print ALL ops that are NOT just updated_at
    print("\n\n=== All non-trivial ops ===")
    for i, op in enumerate(ops):
        diff = op.get("o", {}).get("diff", {})
        u_fields = diff.get("u", {})
        has_non_trivial = False
        for key in u_fields:
            if key != "updated_at":
                has_non_trivial = True
        # Also check sub-diffs
        for key in diff:
            if key.startswith("s"):
                has_non_trivial = True
        if has_non_trivial:
            ts = op.get("ts")
            ts_local = time.strftime('%H:%M:%S', time.localtime(ts.time))
            print(f"\nOp [{i}] at {ts_local}:")
            print(json.dumps(op.get("o", {}), indent=2, default=str))

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
