from scripts.benchmark import run_benchmarks


def test_offline_benchmark_suite():
    results = run_benchmarks()

    assert {result["name"] for result in results} == {
        "bounded-read", "command-safety", "journal-rollback", "context-budget"
    }
    assert all(result["elapsed_ms"] >= 0 for result in results)
