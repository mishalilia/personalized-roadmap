import pytest
from helpers import FakeLLM
from pydantic import ValidationError

from roadmap import Confidence, Level, LevelAssessment
from roadmap.level import LevelAssessor


def test_level_inference_returns_evidence(questions):
    llm = FakeLLM(
        {
            "level": "intermediate",
            "evidence": ["Three years of backend work in Go"],
            "confidence": "medium",
        }
    )

    assessment = LevelAssessor(llm, questions).assess(
        {"programming": "Three years of Go at a bank"}
    )

    assert assessment.level == Level.INTERMEDIATE
    assert assessment.evidence == ["Three years of backend work in Go"]
    assert assessment.confidence == Confidence.MEDIUM
    assert "Three years of Go at a bank" in llm.prompts[0]


def test_an_assessment_without_evidence_is_rejected():
    with pytest.raises(ValidationError):
        LevelAssessment.model_validate(
            {"level": "beginner", "evidence": [], "confidence": "low"}
        )
