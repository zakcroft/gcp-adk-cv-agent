from api.jobs import JobStore


def test_create_returns_running_job_with_unique_id():
    store = JobStore()
    a = store.create()
    b = store.create()
    assert a.status == "running"
    assert a.cv is None and a.error is None
    assert a.id != b.id
    assert store.get(a.id) is a


def test_get_unknown_id_returns_none():
    assert JobStore().get("nope") is None


def test_mark_done_sets_cv_and_status():
    store = JobStore()
    job = store.create()
    store.mark_done(job.id, "IMPROVED CV TEXT")
    assert store.get(job.id).status == "done"
    assert store.get(job.id).cv == "IMPROVED CV TEXT"


def test_mark_failed_sets_error_and_status():
    store = JobStore()
    job = store.create()
    store.mark_failed(job.id, "please upload a CV")
    assert store.get(job.id).status == "failed"
    assert store.get(job.id).error == "please upload a CV"
