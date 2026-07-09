"""Skill + ReviewerDecision Pydantic schema 测试(spec §3.5)。"""
from pydantic import ValidationError
import pytest

from codeweave.skills.schemas import Skill, ReviewerDecision


def test_skill_minimal():
    s = Skill(name="test", description="x", when_to_use="when x", priority=100, body="")
    assert s.name == "test"
    assert s.priority == 100


def test_skill_requires_name():
    with pytest.raises(ValidationError):
        Skill(name="", description="x", when_to_use="when x", priority=100, body="")


def test_skill_priority_default():
    s = Skill(name="t", description="d", when_to_use="w", body="")
    assert s.priority == 0


def test_reviewer_decision_accept_true():
    r = ReviewerDecision(accept=True, score=8, feedback="good", risk_flags=["no_tests"])
    assert r.accept is True
    assert r.score == 8


def test_reviewer_decision_score_out_of_range():
    with pytest.raises(ValidationError):
        ReviewerDecision(accept=True, score=11, feedback="x")


def test_reviewer_decision_feedback_required():
    with pytest.raises(ValidationError):
        ReviewerDecision(accept=False, score=5, feedback="")


def test_reviewer_decision_default_risk_flags():
    r = ReviewerDecision(accept=False, score=0, feedback="reject")
    assert r.risk_flags == []
