"""
Emergency script to restore flowcharts from MongoDB oplog.
Finds all changes to the flowcharts collection and attempts recovery.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from bson import Timestamp
from motor.motor_asyncio import AsyncIOMotorClient
import json
import time

MONGODB_URL = "mongodb://localhost:27017"
DB_NAME = "audit_dashboard"
COLLECTION = "flowcharts"

async def main():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]

    # Use BSON Timestamp (seconds since epoch, increment=0) for oplog queries
    two_hours_ago_epoch = int(time.time()) - 7200
    ts_filter = Timestamp(two_hours_ago_epoch, 0)
    print(f"Looking for oplog entries since epoch {two_hours_ago_epoch} (BSON Timestamp)")
    print(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} local")

    try:
        local_db = client["local"]
        oplog = local_db["oplog.rs"]

        count = await oplog.estimated_document_count()
        print(f"Oplog accessible! {count} entries total")

        # First: find ALL recent oplog entries to see what namespaces exist
        print("\n--- Scanning recent oplog namespaces ---")
        sample = oplog.find({"ts": {"$gte": ts_filter}}).sort("ts", -1)
        all_ops = await sample.to_list(length=5000)
        print(f"Total oplog entries in window: {len(all_ops)}")

        # Show unique namespaces
        namespaces = {}
        for op in all_ops:
            ns = op.get("ns", "")
            namespaces[ns] = namespaces.get(ns, 0) + 1
        print("Namespaces found:")
        for ns, cnt in sorted(namespaces.items(), key=lambda x: -x[1]):
            print(f"  {ns}: {cnt} ops")

        # Now search for flowchart-related ops with various namespace patterns
        flowchart_ops = []
        for op in all_ops:
            ns = op.get("ns", "")
            if "flowchart" in ns.lower() or COLLECTION in ns:
                flowchart_ops.append(op)

        print(f"\nFlowchart-related oplog entries: {len(flowchart_ops)}")

        for op in flowchart_ops:
            op_type = op.get("op")
            ns = op.get("ns")
            ts = op.get("ts")
            doc_id = None
            if op.get("o2"):
                doc_id = op["o2"].get("_id")
            elif op.get("o"):
                doc_id = op["o"].get("_id")

            print(f"\n  op={op_type} ns={ns} ts={ts} id={doc_id}")

            # For update ops, show what was changed
            if op_type == "u":
                update_doc = op.get("o", {})
                if "$set" in update_doc:
                    set_keys = list(update_doc["$set"].keys())
                    print(f"    $set keys: {set_keys}")
                    # If nodes were set, show count
                    if "nodes" in update_doc["$set"]:
                        nodes = update_doc["$set"]["nodes"]
                        print(f"    nodes count: {len(nodes) if isinstance(nodes, list) else 'N/A'}")
                        # Show node IDs
                        if isinstance(nodes, list):
                            for n in nodes[:5]:
                                print(f"      node: id={n.get('id')} type={n.get('type')}")
                elif "$v" in update_doc:
                    # v2 update format
                    diff = update_doc.get("diff", update_doc)
                    print(f"    update doc keys: {list(update_doc.keys())}")
                else:
                    # Full replacement
                    keys = list(update_doc.keys())
                    print(f"    replacement doc keys: {keys}")
                    if "nodes" in update_doc:
                        nodes = update_doc["nodes"]
                        print(f"    nodes count: {len(nodes) if isinstance(nodes, list) else 'N/A'}")

            # For insert ops, show the document
            if op_type == "i":
                doc = op.get("o", {})
                keys = list(doc.keys())
                print(f"    insert doc keys: {keys}")
                if "nodes" in doc:
                    nodes = doc["nodes"]
                    print(f"    nodes count: {len(nodes) if isinstance(nodes, list) else 'N/A'}")

        # Try to find the PREVIOUS state of the overwritten chart
        print("\n\n--- Attempting to find pre-overwrite data ---")
        # Look for the chart that was overwritten (Ievo - chart-1775692687361)
        target_id = "chart-1775692687361"
        prev_states = []
        for op in flowchart_ops:
            doc_id = None
            if op.get("o2"):
                doc_id = op["o2"].get("_id")
            elif op.get("o"):
                doc_id = op["o"].get("_id")

            if doc_id == target_id or str(doc_id) == target_id:
                prev_states.append(op)

        if not prev_states:
            # Also check by matching the filter doc
            for op in flowchart_ops:
                o2 = op.get("o2", {})
                o = op.get("o", {})
                if o2.get("id") == target_id or o.get("id") == target_id:
                    prev_states.append(op)

        print(f"Found {len(prev_states)} ops for chart {target_id}")

        # Look for the EARLIEST state to find original data
        if prev_states:
            earliest = prev_states[-1]  # sorted newest first, so last = earliest
            print(f"Earliest op: type={earliest.get('op')} ts={earliest.get('ts')}")
            update_doc = earliest.get("o", {})
            if "$set" in update_doc and "nodes" in update_doc["$set"]:
                original_nodes = update_doc["$set"]["nodes"]
                print(f"Found potential original nodes: {len(original_nodes)} nodes")
                # Save to file for restoration
                with open("original_ievo_nodes.json", "w") as f:
                    json.dump(original_nodes, f, indent=2, default=str)
                print("Saved to original_ievo_nodes.json")

                if "edges" in update_doc["$set"]:
                    original_edges = update_doc["$set"]["edges"]
                    with open("original_ievo_edges.json", "w") as f:
                        json.dump(original_edges, f, indent=2, default=str)
                    print(f"Saved {len(original_edges)} edges to original_ievo_edges.json")

    except Exception as e:
        print(f"Oplog error: {e}")
        import traceback
        traceback.print_exc()

    # --- Current state for reference ---
    print("\n\n--- Current flowcharts in database ---")
    flowcharts = await db[COLLECTION].find({}).to_list(length=100)
    print(f"Total flowcharts: {len(flowcharts)}")
    for fc in flowcharts:
        node_count = len(fc.get("nodes", []))
        edge_count = len(fc.get("edges", []))
        print(f"  ID: {fc.get('id', fc.get('_id'))}  Name: {fc.get('name', 'unnamed')}  Nodes: {node_count}  Edges: {edge_count}")

    client.close()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
