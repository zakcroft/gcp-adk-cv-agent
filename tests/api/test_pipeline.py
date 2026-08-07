from api.pipeline import classify


def test_presenter_output_is_a_cv():
    r = classify("cv_presenter_agent", "John Smith\nSenior Engineer\n...")
    assert r.cv == "John Smith\nSenior Engineer\n..."
    assert r.error is None


def test_root_agent_output_is_a_refusal():
    r = classify("cv_agent_app", "Please upload your CV and the job description.")
    assert r.cv is None
    assert r.error == "Please upload your CV and the job description."
