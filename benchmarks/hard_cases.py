"""Synthetic state-transition cases; labels never enter model requests."""
import copy
import json
from pathlib import Path


SCOPE = (
    "Review only whether the stated design meets its explicit requirements under the stated failure model. "
    "This is an internal service for 100 customers and 1000 operations/day. One API process and one database "
    "are deliberate choices; a ten-minute infrastructure outage is acceptable. Ordinary HTTPS libraries "
    "validate certificates. Authentication, parameter binding, input limits, and secret redaction are already "
    "implemented. Do not invent multi-region, enterprise scaling, glossary, or extra-alternative requirements. "
    "A major finding needs a concrete allowed execution that violates a stated requirement. "
    "Suggestions that do not establish such an execution are nits. A correct design may receive zero findings."
)


def draft(title, problem, goals, paragraphs, tests):
    return {
        "title": title, "problem": problem, "goals": goals,
        "design": "\n\n".join(paragraphs),
        "alternatives": [
            "The selected database-backed design reuses existing transactions and recovery procedures.",
            "A managed streaming platform would add operational integration without being required at this load.",
            "Synchronous processing would couple client latency to background work and does not fit the existing API contract.",
        ],
        "risks": [
            "A process or database outage delays service; recovery within ten minutes is accepted.",
            "State-transition ordering and expiry boundaries require targeted concurrency and crash tests.",
            "Do not infer protections beyond the mechanisms explicitly described in the design.",
        ],
        "acceptance_tests": tests,
        "open_questions": [],
    }


def defect(identifier, requirement, witness, concepts, anchors):
    return {"id": identifier, "requirement": requirement, "counterexample": witness,
            "concepts": concepts, "anchors": anchors}


def build_cases():
    result = []
    # All IDs are opaque. Neither variant labels nor these IDs reach reviewers.
    feed_refs = [SCOPE,
        "Every feed response, including cached responses, must contain only events belonging to the authenticated tenant.",
        "A polling client must eventually see every event that commits for its tenant while it is polling; it keeps polling within the seven-day retention window. Clients resume strictly after the returned cursor.",
        "Database contract: nextval allocates increasing IDs at INSERT time and is not transactional. Transactions using different connections may commit in a different order. READ COMMITTED readers see only committed rows at statement start."
    ]
    feed = [
        "A bearer token determines tenant_id. GET /feed accepts after and limit (1..100). Event bodies are immutable; event_id is unique within a tenant. Data and cache entries contain no authorization tokens.",
        "Writers allocate seq=nextval() and insert (tenant_id,event_id,seq,body) in their transaction. They may spend several seconds preparing other work before committing. The reader queries committed rows WHERE tenant_id=:tenant AND seq>:after ORDER BY seq LIMIT :limit, and returns the largest seq in that page as next_cursor; an empty page preserves after.",
        "Successful pages are cached for 30 seconds in one shared process cache under (after,limit). A cache hit returns the saved response unchanged after authenticating the caller. A cache miss executes the tenant-filtered query above and stores its serialized response. All customers begin at after=0.",
        "Rate limits are per tenant and checked before cache access. A missing or invalid token receives 401; malformed cursors receive 400. Cache expiry affects freshness only. The polling API promises no snapshot across pages, but must not permanently omit committed events.",
        "Rows are retained seven days. Clients polling less often than that must restart a full sync. Recovery restarts the process with an empty cache. Indexes cover (tenant_id,seq); the expected data volume fits this ordinary database."
    ]
    feed_good = copy.deepcopy(feed)
    feed_good[1] = "Writers insert events and a durable pending-publication row in one transaction. A single publisher reads committed pending rows, locks a counter row, assigns each event a feed_seq, marks the pending rows published, and commits those changes together. It holds the counter lock through commit, so a later feed_seq cannot become visible before an earlier assigned one. The API queries only published rows WHERE tenant_id=:tenant AND feed_seq>:after ORDER BY feed_seq LIMIT :limit. It returns the largest feed_seq in the page, or preserves after for an empty page. Uncommitted events have no feed_seq yet."
    feed_good[2] = "Successful pages are cached for 30 seconds in one shared process cache under (tenant_id,after,limit), using tenant_id derived from the authenticated token. A cache hit returns the saved response unchanged. A miss executes the tenant-filtered query and stores its response under that same tenant-specific key. All customers begin at after=0."
    feed_expected = [
        defect("tenant-cache", feed_refs[1], "Tenant A fills cache key (0,100); tenant B requests the same page and receives A's cached body without a database query.",
               [r"cache", r"tenant|customer", r"key|partition|isolat|leak|disclos|other|cross"],
               ["Successful pages are cached", "cache hit returns"]),
        defect("commit-cursor", feed_refs[2], "T1 allocates seq 41 and pauses; T2 allocates 42 and commits. Poll advances cursor to 42. T1 commits 41, which future seq>42 queries permanently omit.",
               [r"commit|transaction", r"cursor|seq|sequence|id", r"skip|miss|loss|lost|never|omit|invisib"],
               ["Writers allocate seq", "returns the largest seq", "Clients resume"]),
    ]
    for identifier, paragraphs, expected in (("case-17",feed,feed_expected),("case-82",feed_good,[])):
        design = draft("Incremental event feed", "Expose a resumable customer event feed.",
                       ["Isolate tenant data on every response", "Eventually expose committed retained events"], paragraphs,
                       ["Check tenant isolation on cache hits and misses.", "Poll during overlapping writer transactions and compare with all committed events.", "Restart publisher/API processes at each transaction boundary; no retained event may be permanently omitted."])
        result.append({"id":identifier,"family":"feed","task":{"title":design['title'],"brief":design['problem'],"references":feed_refs},"draft":design,"expected":expected})

    worker_refs = [SCOPE,
        "Once a lease has transferred to a new worker, the former worker must not change the job's published result or enqueue a completion notice.",
        "Every completed job must eventually produce at least one completion callback, including a process crash immediately after its database commit. Callback receivers deduplicate by job_id. Transport retries are bounded; a terminal failure is recorded after five attempts within 24 hours.",
        "Workers may pause indefinitely and resume after their 30-second lease expires. Each acquisition increments a monotone epoch. Job creation is already idempotent. Artifact PUTs create immutable uniquely named versions, and only the result pointer on the job row publishes an artifact. An unreferenced version is later garbage-collected."
    ]
    worker = [
        "POST /exports returns 202 and a customer-scoped job_id. API authorization checks tenant ownership for status and result reads. Input size is capped at 64 KiB. The database durably holds job state, current epoch, lease expiry, and result_uri.",
        "A worker atomically claims a pending or expired job, increments epoch, and records its owner and 30-second expiry. It renews every ten seconds while running. After reading the input it writes a new immutable artifact version under a unique object name.",
        "After upload, the worker commits UPDATE jobs SET status='completed', result_uri=:uploaded_uri WHERE job_id=:id. Completion does not otherwise consult lease state. The lease exists to select a worker when a job is taken; each artifact version is immutable, so writes never overwrite each other's bytes.",
        "After committing completed, that same process adds (job_id, callback_url) to its in-memory sender queue. The sender delivers a signed completion callback with bounded backoff. On restart the recovery scan selects pending, running-with-expired-lease, and callback_failed jobs; completed jobs are already terminal and are skipped.",
        "Retry bookkeeping is persisted after the sender starts an attempt. Receivers deduplicate job_id. Callback secrets and destinations have existing validation and rotation support. Orphan artifact versions expire after seven days. No claim is made that temporary compute or storage is allocated exactly once."
    ]
    worker_good = copy.deepcopy(worker)
    worker_good[2] = "After upload, a completion transaction conditionally updates the job only WHERE job_id=:id AND epoch=:acquired_epoch AND owner=:worker AND status='running' AND lease_expires_at>database_now(). Zero updated rows means this worker discards its unpublished result. The transaction also inserts a unique completion notice for job_id in a durable outbox only if the update succeeds, and commits both together. Artifact versions are immutable."
    worker_good[3] = "A separate sender scans the durable outbox for pending or expired-leased notices, delivers the signed callback, and durably records acknowledgement. A crash after remote acknowledgement can cause a duplicate attempt, which the receiver deduplicates by job_id. Completed jobs need no rescan: their committed outbox rows survive every process restart. Attempt count and next_attempt_at are durable, with at most five attempts over 24 hours and a recorded terminal failure."
    worker_expected = [
        defect("stale-worker", worker_refs[1], "W1 pauses past expiry. W2 acquires a higher epoch and publishes B. W1 resumes and its job_id-only UPDATE publishes A over B.",
               [r"lease|epoch|fenc|stale|old worker", r"updat|overwrit|publish|complet|result", r"check|validat|token|compar|conditional|match|race|stale|guard"],
               ["After upload, the worker commits", "Completion does not otherwise"]),
        defect("lost-notice", worker_refs[2], "Completion commits, then the process crashes before enqueueing the in-memory notice. Recovery skips completed jobs, so no callback is ever attempted.",
               [r"crash|fail|restart", r"callback|notif|outbox|notice|queue", r"loss|lost|miss|never|atomic|transaction|durab|gap"],
               ["After committing completed", "completed jobs are already terminal"]),
    ]
    for identifier, paragraphs, expected in (("case-43",worker,worker_expected),("case-26",worker_good,[])):
        design=draft("Asynchronous export publication", "Publish durable export results and send completion callbacks.",
                     ["Only the current lease holder may publish a result", "Recover completion notification after process crashes"], paragraphs,
                     ["Pause an old worker across a lease transfer and observe publication state.", "Crash around the database commit and queue operation; every completed job must retain a delivery path.", "Verify duplicate callback acknowledgements and bounded delivery attempts."])
        result.append({"id":identifier,"family":"worker","task":{"title":design['title'],"brief":design['problem'],"references":worker_refs},"draft":design,"expected":expected})

    expiry_refs=[SCOPE,
        "A client may retry the identical submission with the same tenant-scoped Idempotency-Key for 72 hours after first acceptance. All such retries must return the original event_id without creating another delivery. A changed payload under that key receives 409.",
        "Delivery may be retried up to 24 hours after enqueue. Retries must use the event's assigned key version. Secret rotation must not prevent an otherwise eligible retry from being signed. Receivers retain verification keys for 25 hours after rotation. Server clocks have a maximum five-minute skew.",
        "The signing operation requires the secret bytes, not merely their hash. The assigned key_version is stored on each event at enqueue. Secret rotation can happen immediately after enqueue. Database and key-store operations are durable; callbacks are customer-owned public HTTPS destinations."
    ]
    expiry=[
        "POST /events authenticates the tenant and requires Idempotency-Key. One database transaction creates the event, durable delivery job, and receipt indexed by (tenant_id,key). A unique constraint resolves concurrent submissions. Each receipt stores a payload digest and original response; equal digests replay that response and different digests return 409.",
        "Receipts expire 24 hours after first acceptance and are removed by a cleanup task. Events and delivery jobs are retained seven days. When a key is absent from the receipt table the API accepts the request as new; it never searches the event table by a past submission key. Replaying a receipt does not refresh its expiration.",
        "Rotation creates a fresh random HMAC secret and switches the current key_version for future events. Each existing event keeps its assigned version. The sender loads that version's secret at every attempt and signs the original raw payload, including the version identifier in the header. The receiver chooses the corresponding verification key.",
        "Retired secret bytes are erased 30 minutes after rotation. An audit record retains only key_version and a one-way digest. If the sender cannot load the assigned secret, the job becomes signing_failed; it cannot substitute a new version. Retry scheduling otherwise permits timeouts, 429, and 5xx for up to five attempts within 24 hours of enqueue.",
        "Delivery jobs and attempts survive restart. The receiver deduplicates event_id. Server clocks stay within five minutes of one another. Receipts and secret versions are tenant-scoped, access-controlled, and never placed in logs. Polling status does not expose secret material."
    ]
    expiry_good=copy.deepcopy(expiry)
    expiry_good[1]="Receipts expire 73 hours after first acceptance and are removed by cleanup only after that deadline. This covers the 72-hour retry contract and maximum clock skew. Events and delivery jobs are retained seven days. When a key is absent after expiry the API accepts the request as new. Replaying a receipt does not refresh expiration; payload comparison and response replay remain atomic."
    expiry_good[3]="Retired secret bytes remain encrypted and available for 25 hours after rotation, covering the latest pre-rotation enqueue, its 24-hour retry window, and the maximum clock skew. They are erased after that deadline; an audit record then retains only key_version and a digest. Eligible retries load the event's assigned secret. No retry is scheduled after the 24-hour enqueue deadline; at most five attempts occur with bounded backoff."
    expiry_expected=[
        defect("receipt-window",expiry_refs[1],"At hour 30 the receipt has expired, while the 72-hour retry contract remains active. The identical key creates a second event despite the original event still being retained.",
               [r"receipt|idempot|duplicat|dedup",r"24|72|retai|expir|ttl|window",r"new event|second|duplicat|contract|72|retry|retri"],
               ["Receipts expire 24 hours", "key is absent from the receipt"]),
        defect("signing-window",expiry_refs[2],"Enqueue under K1 at t=0 and rotate at t=1 minute. Retry at hour 1 is still eligible, but K1's bytes have been erased; the audit digest cannot sign the payload.",
               [r"key|secret|version",r"retai|delet|expir|eras|purge|30",r"retry|retri|24|hour|sign"],
               ["Retired secret bytes are erased", "sender cannot load the assigned"]),
    ]
    for identifier,paragraphs,expected in (("case-65",expiry,expiry_expected),("case-91",expiry_good,[])):
        design=draft("Event submission and key lifecycle", "Preserve idempotent submissions and signed retries across rotation.",
                     ["Honor the documented submission retry window", "Keep all eligible delivery retries signable"],paragraphs,
                     ["Retry identical and changed payloads just before and after receipt cleanup boundaries.", "Rotate immediately after enqueue and retry late in the delivery window.", "Repeat boundary cases at both extremes of the stated clock skew."])
        result.append({"id":identifier,"family":"expiry","task":{"title":design['title'],"brief":design['problem'],"references":expiry_refs},"draft":design,"expected":expected})
    # Allow any exact excerpt from the affected paragraph, not only its opening
    # words. Causal-concept checks still reject a generic comment on that text.
    for case in result:
        paragraphs = case['draft']['design'].split('\n\n')
        for expected in case['expected']:
            expected['anchors'] = list(dict.fromkeys(
                [paragraph for paragraph in paragraphs
                 if any(anchor.lower() in paragraph.lower() for anchor in expected['anchors'])]
                + expected['anchors']))
    # Interleave corrected and defective designs; keep the order fixed before calls.
    order=("case-26","case-17","case-91","case-43","case-82","case-65")
    return [next(case for case in result if case['id']==identifier) for identifier in order]


def counterexamples():
    """Executable minimal witnesses under the explicitly declared toy semantics."""
    cache={(0,100):"tenant-A"}
    isolated_cache={("A",0,100):"tenant-A"}
    cursor=42  # T2 committed first; T1's allocated 41 commits after the poll.
    old_seq_visible=41>cursor
    published_later_seq=43  # Fixed protocol assigns only after visibility.
    acquired_epoch,current_epoch=1,2
    current_result="B"
    stale_result="A"
    unsafe_result=stale_result
    safe_result=stale_result if acquired_epoch==current_epoch else current_result
    completed=True
    process_queue=[]  # Crash immediately after commit, before enqueue.
    durable_outbox=["job-1"]  # Fixed protocol commits this with completed.
    return {
        "tenant-cache":{"broken":cache.get((0,100))=="tenant-A","fixed":isolated_cache.get(("B",0,100)) is None},
        "commit-cursor":{"broken":not old_seq_visible,"fixed":published_later_seq>cursor},
        "stale-worker":{"broken":unsafe_result!="B","fixed":safe_result=="B"},
        "lost-notice":{"broken":completed and not process_queue,"fixed":completed and bool(durable_outbox)},
        "receipt-window":{"broken":24<30<72,"fixed":30<73},
        "signing-window":{"broken":0.5<1<24,"fixed":1<25},
    }


if __name__ == "__main__":
    destination=Path(__file__).resolve().parents[1]/"examples/hard-evaluation.json"
    destination.write_text(json.dumps(build_cases(),indent=2)+"\n",encoding="utf-8")
    print(destination)
