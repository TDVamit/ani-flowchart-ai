"""
Restore Ievo chart from oplog op[83] which has 152 nodes (the last good state before overwrite).
"""
import asyncio
import time
import json
from bson import Timestamp, ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb://localhost:27017"
DB_NAME = "audit_dashboard"
COLLECTION = "flowcharts"
IEVO_OID = ObjectId("69d738e7125e9402cf937fc1")

async def main():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]

    two_hours_ago = int(time.time()) - 7200
    ts_filter = Timestamp(two_hours_ago, 0)
    local_db = client["local"]
    oplog = local_db["oplog.rs"]

    cursor = oplog.find({
        "ns": f"{DB_NAME}.{COLLECTION}",
        "ts": {"$gte": ts_filter},
    }).sort("ts", 1)

    ops = await cursor.to_list(length=5000)

    # Find op[83] (16:41:46) — the last save with full Ievo data (152 nodes)
    # It's the third op that changed nodes
    node_change_ops = []
    for i, op in enumerate(ops):
        diff = op.get("o", {}).get("diff", {})
        u_fields = diff.get("u", {})
        if "nodes" in u_fields:
            node_change_ops.append((i, op))

    print(f"Found {len(node_change_ops)} ops that changed nodes")
    for idx, (i, op) in enumerate(node_change_ops):
        nodes = op["o"]["diff"]["u"]["nodes"]
        ts = op.get("ts")
        ts_local = time.strftime('%H:%M:%S', time.localtime(ts.time))
        print(f"  [{idx}] op[{i}] at {ts_local}: {len(nodes)} nodes")

    # Use the op with 152 nodes (index 1, which is op[83])
    best_op = None
    for i, op in node_change_ops:
        nodes = op["o"]["diff"]["u"]["nodes"]
        if len(nodes) == 152:
            best_op = op
            break

    if not best_op:
        # Fall back to largest node set
        best_op = max(node_change_ops, key=lambda x: len(x[1]["o"]["diff"]["u"]["nodes"]))[1]

    restore_nodes = best_op["o"]["diff"]["u"]["nodes"]
    print(f"\nWill restore {len(restore_nodes)} nodes")

    # Also get edges — find the last op that had edges before the overwrite
    restore_edges = None
    for i, op in enumerate(ops):
        diff = op.get("o", {}).get("diff", {})
        u_fields = diff.get("u", {})
        if "edges" in u_fields:
            edges = u_fields["edges"]
            if len(edges) > 3:  # skip the overwritten version (test has 2 edges)
                restore_edges = edges
                ts = op.get("ts")
                ts_local = time.strftime('%H:%M:%S', time.localtime(ts.time))
                print(f"Found edges from {ts_local}: {len(edges)} edges")

    if not restore_edges:
        # The edges might not have been in the oplog if they weren't changed
        # Check the overwrite op for the edges that REPLACED original
        # We need to get the original edges from somewhere else
        # Let's check if op[88] has the original edges or test's edges
        for i, op in node_change_ops:
            diff = op["o"]["diff"]["u"]
            if "edges" in diff:
                edges = diff["edges"]
                print(f"  Op[{i}] also has {len(edges)} edges")
                if len(edges) > 3:
                    restore_edges = edges

    # Backup before restore
    current = await db[COLLECTION].find_one({"_id": IEVO_OID})
    with open("ievo_pre_restore_backup.json", "w") as f:
        backup = {k: v for k, v in current.items() if k != "_id"}
        backup["_id"] = str(current["_id"])
        json.dump(backup, f, indent=2, default=str)
    print("Pre-restore backup saved to ievo_pre_restore_backup.json")

    # Do the restore
    update = {"$set": {"nodes": restore_nodes}}
    if restore_edges:
        update["$set"]["edges"] = restore_edges
    else:
        print("WARNING: No original edges found in oplog. Edges will remain as-is.")

    result = await db[COLLECTION].update_one({"_id": IEVO_OID}, update)
    print(f"\nRestore result: matched={result.matched_count}, modified={result.modified_count}")

    # Verify
    restored = await db[COLLECTION].find_one({"_id": IEVO_OID})
    print(f"Verified: {len(restored.get('nodes', []))} nodes, {len(restored.get('edges', []))} edges")

    # Save restored data
    with open("ievo_restored.json", "w") as f:
        data = {k: v for k, v in restored.items() if k != "_id"}
        data["_id"] = str(restored["_id"])
        json.dump(data, f, indent=2, default=str)
    print("Restored data saved to ievo_restored.json")

    client.close()
    print("\nDone! Ievo chart restored.")

if __name__ == "__main__":
    asyncio.run(main())
