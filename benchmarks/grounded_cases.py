"""Fresh transfer pair, fixed before testing the grounded adapter on a live model.

This is an authored synthetic holdout, not an independently collected benchmark.
The old hard-evaluation dataset remains unchanged, including its known extra flaw.
"""
import copy
import json
from pathlib import Path

from .hard_cases import SCOPE, defect, draft


def build_cases():
    references = [SCOPE,
        "For each SKU, available stock starts nonnegative and must never become negative. Simultaneous successful reservations must not allocate more units than are available. All writers use this service; no out-of-band stock modifications occur during the scenarios.",
        "Cancelling an active reservation must restore its quantity exactly once. Repeating cancellation, including after a lost HTTP response, must not increase stock again. Cancellation of an already cancelled reservation returns the existing cancelled state.",
        "The PostgreSQL database runs at READ COMMITTED. A transaction groups its writes atomically but does not automatically serialize application reads with a later update. An UPDATE locks the affected row and rechecks its WHERE predicate on the latest committed row after waiting for a concurrent updater.",
        "Each reservation contains one SKU and a fixed positive integer quantity. This service only reserves and cancels; payment, shipment, expiration, and multi-SKU orders are outside scope. Indefinite reservations until explicit cancellation are an accepted tradeoff. Authenticated tenants can only create, read, or cancel their own reservations. Resource IDs are opaque but are not authorization credentials.",
        "A successful POST replayed with the same tenant-scoped Idempotency-Key and payload returns its original response. A different payload under a successfully used key returns 409. Rejected requests need not be remembered. Database state and idempotency records are durable. No external service call is part of reservation or cancellation."
    ]
    common_start = "POST /reservations authenticates the tenant, validates an existing SKU and integer quantity from 1 through 100, and requires Idempotency-Key. Requests are capped at 8 KiB. GET and DELETE look up both reservation ID and authenticated tenant ID; an absent or differently owned ID returns 404. Each reservation stores tenant, SKU, immutable quantity, and active or cancelled state."
    allocate = "In a creation transaction, read available from stock for the requested SKU using an ordinary SELECT. If available is less than quantity, roll back and return 409. Otherwise issue UPDATE stock SET available=available-:quantity WHERE sku=:sku, insert the active reservation and idempotency receipt, and commit. The table has no nonnegative CHECK constraint. The separate read is the admission check."
    cancel = "In a cancellation transaction, fetch the tenant-owned reservation using an ordinary SELECT. For every found reservation, execute UPDATE stock SET available=available+:quantity WHERE sku=:sku and UPDATE reservations SET state='cancelled' WHERE id=:id AND tenant_id=:tenant, then commit and return the cancelled state. The reservation's immutable stored quantity supplies the stock increment."
    idempotency = "The creation transaction inserts a receipt with a unique (tenant_id,key), payload digest, and original HTTP response. A uniqueness conflict rolls back the entire transaction, including its stock change; a fresh transaction reads the winning receipt and replays it or returns 409 for a changed digest. An existing receipt is checked before stock admission. After a stock-admission failure, roll back and recheck the receipt in a fresh transaction before returning 409, so a concurrent same-key winner is replayed. A lost creation response is retried with the same key. Receipts and reservations remain for this service's lifetime; accepted scale makes that storage tradeoff affordable."
    recovery = "All responses are sent after database commit. A precommit process crash rolls back the whole transaction; after commit the stored records survive restart. Clients may retry cancellation by reservation ID after timeouts. Transaction deadlocks or database outages yield a retriable 503; callers retry at most three times with jitter, then surface the failure. The server does not automatically retry a transaction after returning a response."
    monitoring = "Operations logs record request ID, tenant ID, status, and latency without payloads or credentials. Counters track reservations created, cancellation requests, 409s, 503s, and current available stock. Normal HTTPS and existing authentication middleware validate identities. One database and one process are sufficient for the explicitly accepted availability target."
    bad = [common_start, allocate, cancel, idempotency, recovery, monitoring]
    good = copy.deepcopy(bad)
    good[1] = "In a creation transaction, issue UPDATE stock SET available=available-:quantity WHERE sku=:sku AND available>=:quantity RETURNING available. Zero updated rows means rollback and 409; otherwise insert the active reservation and idempotency receipt and commit. The UPDATE checks and decrements the latest row under the same row lock. Stock has a nonnegative CHECK constraint as additional defense."
    good[2] = "In a cancellation transaction, execute UPDATE reservations SET state='cancelled' WHERE id=:id AND tenant_id=:tenant AND state='active' RETURNING sku,quantity. Only when a row is returned, increment that SKU's stock by the returned immutable quantity in the same transaction. If no row is returned, read the tenant-owned reservation: return its already cancelled state or 404 when absent. Commit before responding. Concurrent cancels therefore only restore stock for the single active-to-cancelled transition."
    expected = [
        defect("over-allocation", references[1], "Stock=1. T1 and T2 each read 1 for distinct one-unit requests. T1 decrements to 0 and commits; T2's unguarded update decrements to -1 and commits another reservation.",
               [r"concurr|simult|race|both|two|t1", r"stock|availab|reserv|unit", r"negativ|oversell|over.alloc|exceed|guard|conditional|atomic"], [allocate]),
        defect("repeat-cancellation", references[2], "Cancel a one-unit reservation and commit its stock increment, lose the response, then repeat DELETE. The cancelled row is found and its quantity is added again.",
               [r"cancel|delet", r"repeat|retry|retri|twice|again|duplicate", r"stock|increment|restor|quantity|credit"], [cancel]),
    ]
    cases = []
    for identifier, paragraphs, labels in (("transfer-28", good, []), ("transfer-73", bad, expected)):
        design = draft("Inventory reservations", "Reserve and cancel a tenant's inventory allocation safely.",
                       ["Keep allocations within available inventory", "Restore a cancelled allocation exactly once"], paragraphs,
                       ["Race distinct keys against a SKU with one unit and verify at most one success and nonnegative stock.",
                        "Cancel concurrently and after losing a committed response; stock must increase once.",
                        "Retry a successful creation key and a changed payload, crash before and after commits, and attempt another tenant's reservation ID."])
        design["alternatives"] = [
            "The selected database-backed synchronous API commits stock and reservation state together using existing transactions.",
            "A separate inventory queue adds asynchronous states and operational work without being required at this load.",
            "Application process locks cannot survive restarts or coordinate a later second process; database transactions provide the existing durable boundary.",
        ]
        design["risks"] = [
            "A process or database outage delays service; recovery within ten minutes is accepted.",
            "Concurrency and lost responses require the targeted allocation, cancellation, and replay tests listed below.",
            "Indefinite reservations and lifetime receipt storage are accepted within the stated small internal service scope.",
        ]
        cases.append({"id": identifier, "family": "inventory", "task": {
            "title": design["title"], "brief": design["problem"], "references": references},
            "draft": design, "expected": labels})
    return cases


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "examples/grounded-transfer.json"
    destination.write_text(json.dumps(build_cases(), indent=2) + "\n", encoding="utf-8")
    print(destination)
