# Architecture & Design Decisions

This document outlines key technical decisions, trade-offs, and design rationale behind `queuectl`.

---

## 1. Why SQLite?

### Rationale:
- **Zero Infrastructure Overhead**: Runs out-of-the-box locally without external daemon processes (e.g., Redis, RabbitMQ, or Postgres).
- **ACID Transactions**: Provides full transactional integrity across multiple CLI invocations and process boundaries.
- **WAL Mode (`PRAGMA journal_mode = WAL;`)**: Write-Ahead Logging allows background workers to write while CLI commands concurrently read database state without lock contention.
- **Busy Timeout (`PRAGMA busy_timeout = 5000;`)**: Prevents `sqlite3.OperationalError: database is locked` errors under multi-worker concurrency.

---

## 2. Why Atomic Update for Job Claims?

### Rationale:
In a multi-process worker pool, two worker processes polling the database simultaneously must **never** claim the same job.

### Mechanics:
```sql
BEGIN IMMEDIATE;

SELECT * FROM jobs
WHERE state = 'pending'
  AND (next_retry_time IS NULL OR next_retry_time <= ?)
ORDER BY created_at ASC
LIMIT 1;

UPDATE jobs
SET state = 'processing', worker_id = ?, heartbeat = ?, updated_at = ?
WHERE id = ? AND state = 'pending';
```

### Why it is Atomic:
1. SQLite's `BEGIN IMMEDIATE` acquires a reserved write lock on the database file before reading.
2. The `UPDATE ... WHERE id = ? AND state = 'pending'` query ensures optimistic conditional verification. If another worker managed to update the row first, the update affects 0 rows, preventing duplicate execution.

---

## 3. How Crash Recovery Works

### Mechanics:
1. **Worker Heartbeat**: Each worker executing a job spawns a lightweight daemon thread that updates `jobs.heartbeat` timestamp every 5 seconds.
2. **Detection Threshold**: If a worker process dies unexpectedly (e.g., `kill -9`, power failure, or OOM), its heartbeat thread halts instantly.
3. **Recovery Scan**: A dedicated recovery loop checks for jobs where `state = 'processing'` and `heartbeat < NOW - 30 seconds`.
4. **Reclamation**: Stale jobs are returned to `pending` state with incremented `attempts` (or moved to `dead` if max retries exceeded).
5. **Worst-Case Bound**: Recovery runs every 10s with a 30s threshold, guaranteeing job recovery in under 60 seconds.

---

## 4. Why PID Files for Worker Control?

### Rationale:
CLI applications run as short-lived, transient processes. When a user runs `queuectl worker start --count 3`, the spawned worker processes detach into the background.

### Mechanics:
- When starting workers, `WorkerPoolManager` records child process IDs into `~/.queuectl/workers.pid`.
- When `queuectl worker stop` is executed in another terminal window, it reads the PIDs from `workers.pid`, sends `SIGTERM` signals for graceful shutdown, and cleans up the file.

---

## 5. Why Retry Resets Attempts to Zero in DLQ?

### Rationale:
When a job lands in the Dead Letter Queue (`state = 'dead'`), it indicates that all automated retry attempts failed.

When an engineer explicitly issues `queuectl dlq retry JOB_ID`:
- The engineer has presumably fixed the root cause (e.g., corrected an invalid shell script, updated environment permissions, or deployed a code fix).
- Resetting `attempts` to 0 gives the fixed job a fresh retry budget (`0` to `max_retries`) under standard backoff rules, rather than instantly failing back to DLQ on a single glitch.

---

## 6. How Priorities Can Be Added Later

### Design Extension:
To support priority-based job scheduling:
1. **Schema Migration**: Add an `priority INTEGER DEFAULT 0` column to the `jobs` table (e.g., `HIGH = 10`, `NORMAL = 0`, `LOW = -10`).
2. **Order Clause Update**: Update atomic claim SQL query:
   ```sql
   SELECT * FROM jobs
   WHERE state = 'pending'
     AND (next_retry_time IS NULL OR next_retry_time <= ?)
   ORDER BY priority DESC, created_at ASC
   LIMIT 1;
   ```
3. **Index Optimization**: Create index `idx_jobs_priority (state, priority DESC, next_retry_time, created_at)` for $\mathcal{O}(\log N)$ claim performance.
