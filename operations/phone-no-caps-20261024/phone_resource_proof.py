#!/usr/bin/env python3
"""Real 3-GiB anonymous RSS and every kernel-allowed CPU proof; no compilation."""
import hashlib
import json
import mmap
import multiprocessing as mp
import os
from pathlib import Path
import resource
import sys
import time

TOTAL_BYTES = 3 * 1024 ** 3
CPU_SECONDS = 15


def proc_sample(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"processor": int(fields[36]), "rss_kib": int(fields[21]) * os.sysconf("SC_PAGE_SIZE") // 1024}


def worker(cpu, size, start, stop, pipe):
    try:
        os.sched_setaffinity(0, {cpu})
        region = mmap.mmap(-1, size, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
        for offset in range(0, size, mmap.PAGESIZE):
            region[offset] = (offset // mmap.PAGESIZE % 251) + 1
        pipe.send({"event": "ready", "pid": os.getpid(), "cpu": cpu, "bytes": size})
        start.wait()
        view = memoryview(region)[:1024 * 1024]
        seen = set()
        rounds = 0
        last = 0.0
        while not stop.is_set():
            hashlib.sha256(view).digest()
            rounds += 1
            now = time.monotonic()
            if now - last >= .20:
                seen.add(proc_sample(os.getpid())["processor"])
                last = now
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result = {"event": "worker", "pid": os.getpid(), "assigned_cpu": cpu,
                  "affinity": sorted(os.sched_getaffinity(0)), "proc_processors": sorted(seen),
                  "allocated_touched_bytes": size, "peak_rss_kib": usage.ru_maxrss,
                  "user_cpu_seconds": usage.ru_utime, "system_cpu_seconds": usage.ru_stime,
                  "sha256_rounds": rounds}
        view.release()
        region.close()
        pipe.send(result)
    except BaseException as exc:
        pipe.send({"event": "error", "cpu": cpu, "error": repr(exc)})
        raise
    finally:
        pipe.close()


def main():
    cpus = sorted(os.sched_getaffinity(0))
    ctx = mp.get_context("fork")
    start, stop = ctx.Event(), ctx.Event()
    processes, pipes, messages = [], [], []
    pages, extra = divmod(TOTAL_BYTES // mmap.PAGESIZE, len(cpus))
    print(json.dumps({"event": "start", "time": time.time(), "allowed_cpus": cpus,
                      "total_bytes": TOTAL_BYTES, "cpu_seconds": CPU_SECONDS,
                      "job_id": os.environ.get("FLEET_JOB_ID"),
                      "python": sys.version, "kernel": os.uname().release}), flush=True)
    for i, cpu in enumerate(cpus):
        recv, send = ctx.Pipe(duplex=False)
        process = ctx.Process(target=worker,
            args=(cpu, (pages + (i < extra)) * mmap.PAGESIZE, start, stop, send))
        process.start()
        send.close()
        processes.append(process)
        pipes.append(recv)
    peak_total = 0
    peak_workers = 0
    ready = set()
    parent_observed = {p.pid: set() for p in processes}
    deadline = time.monotonic() + 100
    running_until = None
    try:
        while True:
            workers_rss = 0
            for process in processes:
                try:
                    sample = proc_sample(process.pid)
                    workers_rss += sample["rss_kib"]
                    if process.pid in ready:
                        parent_observed[process.pid].add(sample["processor"])
                except (FileNotFoundError, ProcessLookupError):
                    pass
            peak_workers = max(peak_workers, workers_rss)
            peak_total = max(peak_total, workers_rss + proc_sample(os.getpid())["rss_kib"])
            for pipe in pipes:
                while pipe.poll():
                    try:
                        message = pipe.recv()
                    except EOFError:
                        break
                    messages.append(message)
                    print(json.dumps(message, sort_keys=True), flush=True)
                    if message["event"] == "ready":
                        ready.add(message["pid"])
                    if message["event"] == "error":
                        raise RuntimeError(message["error"])
            if len(ready) == len(cpus) and running_until is None:
                start.set()
                running_until = time.monotonic() + CPU_SECONDS
            if running_until is not None and time.monotonic() >= running_until:
                stop.set()
            if all(not p.is_alive() for p in processes):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("resource proof exceeded 100 seconds")
            time.sleep(.05)
        for process in processes:
            process.join()
        results = [m for m in messages if m["event"] == "worker"]
        observed = sorted({cpu for result in results for cpu in result["proc_processors"]})
        ok = (len(results) == len(cpus) and observed == cpus and
              peak_total >= TOTAL_BYTES // 1024 and
              all(p.exitcode == 0 for p in processes) and
              all(r["sha256_rounds"] > 0 and r["user_cpu_seconds"] > 0 for r in results))
        print(json.dumps({"event": "summary", "allowed_cpus": cpus, "actual_cpus_used": observed,
              "parent_proc_processor_observations": {str(pid): sorted(values) for pid, values in parent_observed.items()},
              "peak_aggregate_rss_kib": peak_total, "peak_worker_rss_kib": peak_workers,
              "allocated_touched_bytes": TOTAL_BYTES, "worker_exitcodes": [p.exitcode for p in processes],
              "exit_status": 0 if ok else 1, "passed": ok}, sort_keys=True), flush=True)
        return 0 if ok else 1
    finally:
        stop.set()
        start.set()
        for process in processes:
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)


if __name__ == "__main__":
    sys.exit(main())
