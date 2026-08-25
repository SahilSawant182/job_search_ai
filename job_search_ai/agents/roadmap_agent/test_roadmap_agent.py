from __future__ import annotations

import unittest
import time
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from job_search_ai.agents.roadmap_agent.agent import RoadmapAgent
from job_search_ai.agents.roadmap_agent.schemas import RoadmapProfile, RoadmapMilestone
from job_search_ai.agents.roadmap_agent.validator import validate_roadmap


class TestRoadmapAgent(IntegrationTestCase):
    """
    Test suite for RoadmapAgent and Roadmap Validator.
    """

    def setUp(self):
        super().setUp()
        self.agent = RoadmapAgent()
        
        # Define mock skill gap reports for testing
        self.gap_ai_engineer = {
            "career": "AI Engineer",
            "matched_skills": ["Python", "Git", "SQL"],
            "missing_foundation": [],
            "missing_core_domain": ["Machine Learning", "Deep Learning", "PyTorch"],
            "missing_industry": ["AWS"],
            "missing_emerging": [],
            "readiness_score": 30.0
        }

        self.gap_frontend = {
            "career": "Frontend Developer",
            "matched_skills": ["HTML", "CSS", "JavaScript", "Git", "React"],
            "missing_foundation": [],
            "missing_core_domain": ["Redux State Management"],
            "missing_industry": ["Next.js Framework"],
            "missing_emerging": ["WebAssembly"],
            "readiness_score": 62.5
        }

        self.gap_devops = {
            "career": "DevOps Engineer",
            "matched_skills": ["Linux", "Git", "Docker", "Kubernetes", "CI/CD"],
            "missing_foundation": [],
            "missing_core_domain": ["Jenkins", "Ansible"],
            "missing_industry": ["Prometheus", "Terraform"],
            "missing_emerging": [],
            "readiness_score": 50.0
        }

        self.gap_almost_ready = {
            "career": "Data Engineer",
            "matched_skills": ["SQL", "Python", "ETL", "Spark", "Airflow"],
            "missing_foundation": [],
            "missing_core_domain": [],
            "missing_industry": ["Snowflake"],
            "missing_emerging": [],
            "readiness_score": 90.0
        }

        self.gap_no_gap = {
            "career": "Frontend Developer",
            "matched_skills": ["HTML", "CSS", "JavaScript"],
            "missing_foundation": [],
            "missing_core_domain": [],
            "missing_industry": [],
            "missing_emerging": [],
            "readiness_score": 100.0
        }

    def test_validator_success_ai_engineer(self):
        """Test A: Valid AI Engineer roadmap validates successfully."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="Machine Learning Foundations",
                    type="Learn",
                    skill="Machine Learning",
                    skill_tier="Core Domain",
                    duration_days=14,
                    objective="Understand supervised and unsupervised learning.",
                    project="Build a house-price prediction model",
                    completion_criteria=["Build a working model."],
                    learning_outcomes=["Understand ML."],
                    supporting_skills=[]
                ),
                RoadmapMilestone(
                    sequence=2,
                    title="Deep Learning Fundamentals",
                    type="Learn",
                    skill="Deep Learning",
                    skill_tier="Core Domain",
                    duration_days=21,
                    objective="Understand neural networks and model training.",
                    project="Build an image classification model",
                    completion_criteria=["Build an image classifier."],
                    learning_outcomes=["Understand DL."],
                    supporting_skills=[]
                ),
                RoadmapMilestone(
                    sequence=3,
                    title="PyTorch Framework",
                    type="Build",
                    skill="PyTorch",
                    skill_tier="Core Domain",
                    duration_days=14,
                    objective="Deploy model architectures using PyTorch.",
                    project="Train a custom PyTorch convolutional network",
                    completion_criteria=["Train CNN in PyTorch."],
                    learning_outcomes=["PyTorch proficiency."],
                    supporting_skills=[]
                ),
                RoadmapMilestone(
                    sequence=4,
                    title="AWS Cloud Deployment",
                    type="Apply",
                    skill="AWS",
                    skill_tier="Industry",
                    duration_days=10,
                    objective="Deploy ML models on AWS SageMaker.",
                    project="Expose API endpoint for PyTorch model on AWS",
                    completion_criteria=["Deploy model endpoint."],
                    learning_outcomes=["AWS deployment."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertTrue(is_valid, f"Validation failed: {err}")
        self.assertIsNone(err)

    def test_validator_fails_on_career_mismatch(self):
        """Rule 2: Career mismatch rejected."""
        roadmap = RoadmapProfile(career="Web Developer", readiness_score=30.0)
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("Career mismatch", err)

    def test_validator_fails_on_matched_skill(self):
        """Rule 4: Matched skills rejected."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="Python Programming",
                    type="Learn",
                    skill="Python",  # Python is in matched_skills
                    skill_tier="Core Domain",
                    duration_days=10,
                    objective="Learn basic programming.",
                    project="Simple scripts",
                    completion_criteria=["Complete scripts."],
                    learning_outcomes=["Learn Python."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("already matched skill", err)

    def test_validator_fails_on_skill_not_in_gap(self):
        """Rule 3: Skills not in gap report rejected."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="Rust Programming",
                    type="Learn",
                    skill="Rust",  # Rust is not in missing/matched skills
                    skill_tier="Core Domain",
                    duration_days=10,
                    objective="Learn Rust.",
                    project="CLI app",
                    completion_criteria=["Complete Rust project."],
                    learning_outcomes=["Learn Rust."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("not in gap report", err)

    def test_validator_fails_on_duplicate_skills(self):
        """Rule 5: Duplicate skills rejected."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="ML Part 1",
                    type="Learn",
                    skill="Machine Learning",
                    skill_tier="Core Domain",
                    duration_days=14,
                    objective="ML math.",
                    project="Regression model",
                    completion_criteria=["Complete ML Part 1."],
                    learning_outcomes=["Learn ML Math."],
                    supporting_skills=[]
                ),
                RoadmapMilestone(
                    sequence=2,
                    title="ML Part 2",
                    type="Learn",
                    skill="Machine Learning",  # Duplicate skill
                    skill_tier="Core Domain",
                    duration_days=14,
                    objective="ML deep dive.",
                    project="Classification model",
                    completion_criteria=["Complete ML Part 2."],
                    learning_outcomes=["Learn ML Deep Dive."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("Duplicate target skill", err)

    def test_validator_fails_on_tier_mismatch(self):
        """Rule 6: Tier mismatch rejected."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="Machine Learning Foundations",
                    type="Learn",
                    skill="Machine Learning",
                    skill_tier="Foundation",  # Machine Learning is Core Domain in gap report
                    duration_days=14,
                    objective="Learn ML.",
                    project="House price model",
                    completion_criteria=["Complete model."],
                    learning_outcomes=["Learn ML."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("Tier mismatch", err)

    def test_validator_fails_on_sequence_mismatch(self):
        """Rule 9: Non-consecutive or duplicate sequence rejected."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=2,  # Missing sequence 1
                    title="ML Foundations",
                    type="Learn",
                    skill="Machine Learning",
                    skill_tier="Core Domain",
                    duration_days=14,
                    objective="Learn ML.",
                    project="House price model",
                    completion_criteria=["Complete model."],
                    learning_outcomes=["Learn ML."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("Non-consecutive sequence", err)

    def test_validator_fails_on_negative_duration(self):
        """Rule 7: Negative or zero duration rejected."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="ML Foundations",
                    type="Learn",
                    skill="Machine Learning",
                    skill_tier="Core Domain",
                    duration_days=0,  # Invalid duration
                    objective="Learn ML.",
                    project="House price model",
                    completion_criteria=["Complete model."],
                    learning_outcomes=["Learn ML."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("invalid duration", err)

    def test_validator_fails_on_invalid_type(self):
        """Rule 8: Unknown/invalid milestone types rejected."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="ML Foundations",
                    type="ReadABook",  # Invalid type
                    skill="Machine Learning",
                    skill_tier="Core Domain",
                    duration_days=14,
                    objective="Learn ML.",
                    project="House price model",
                    completion_criteria=["Complete model."],
                    learning_outcomes=["Learn ML."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("invalid type", err)

    def test_validator_fails_on_empty_objective_or_project(self):
        """Rule 10: Empty details rejected."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="ML Foundations",
                    type="Learn",
                    skill="Machine Learning",
                    skill_tier="Core Domain",
                    duration_days=14,
                    objective="",  # Empty
                    project="House price model",
                    completion_criteria=["Complete model."],
                    learning_outcomes=["Learn ML."],
                    supporting_skills=[]
                )
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("empty objective", err)

    def test_validator_fails_on_missing_core_domain_coverage(self):
        """Rule 10 Coverage: Missing core domain skill must have its own milestone."""
        roadmap = RoadmapProfile(
            career="AI Engineer",
            readiness_score=30.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1,
                    title="Machine Learning Foundations",
                    type="Learn",
                    skill="Machine Learning",
                    skill_tier="Core Domain",
                    duration_days=14,
                    objective="Learn ML.",
                    project="House price model",
                    completion_criteria=["Complete model."],
                    learning_outcomes=["Learn ML."],
                    supporting_skills=[]
                )
                # Deep Learning and PyTorch (Core Domain) are omitted!
            ]
        )
        is_valid, err = validate_roadmap(roadmap, "AI Engineer", self.gap_ai_engineer)
        self.assertFalse(is_valid)
        self.assertIn("Missing Core Domain skills not covered", err)

    def test_no_skill_gap(self):
        """Test E: Returns empty roadmap with helpful message if no skill gap exists."""
        result = self.agent.run(
            student="no_gap_student@example.com",
            career="Frontend Developer",
            skill_gap_report=self.gap_no_gap
        )
        self.assertEqual(result.validation_status, "Valid")
        self.assertEqual(len(result.roadmap.milestones), 0)
        self.assertEqual(
            result.roadmap.message,
            "Student already meets the currently defined skill requirements."
        )

    @patch("job_search_ai.agents.roadmap_agent.llm_service.LLMService.call_agent")
    def test_agent_run_mock_success_ai_engineer(self, mock_call):
        """Test A Integration: Run agent with mock LLM response for AI Engineer."""
        mock_response = """
        {
          "career": "AI Engineer",
          "readiness_score": 30.0,
          "milestones": [
            {
              "sequence": 1,
              "title": "Machine Learning Foundations",
              "type": "Learn",
              "skill": "Machine Learning",
              "skill_tier": "Core Domain",
              "duration_days": 14,
              "objective": "Understand supervised and unsupervised learning.",
              "project": "Build a house-price prediction model",
              "completion_criteria": ["Model built"],
              "learning_outcomes": ["ML learned"],
              "supporting_skills": []
            },
            {
              "sequence": 2,
              "title": "Deep Learning Fundamentals",
              "type": "Learn",
              "skill": "Deep Learning",
              "skill_tier": "Core Domain",
              "duration_days": 21,
              "objective": "Understand neural networks.",
              "project": "Build an image classification model",
              "completion_criteria": ["Classifier built"],
              "learning_outcomes": ["DL learned"],
              "supporting_skills": []
            },
            {
              "sequence": 3,
              "title": "PyTorch Framework",
              "type": "Build",
              "skill": "PyTorch",
              "skill_tier": "Core Domain",
              "duration_days": 14,
              "objective": "Understand PyTorch neural network training.",
              "project": "Train a custom CNN model",
              "completion_criteria": ["CNN trained"],
              "learning_outcomes": ["PyTorch learned"],
              "supporting_skills": []
            },
            {
              "sequence": 4,
              "title": "AWS Cloud Deployment",
              "type": "Apply",
              "skill": "AWS",
              "skill_tier": "Industry",
              "duration_days": 10,
              "objective": "Deploy ML models on AWS.",
              "project": "Deploy PyTorch model to AWS SageMaker",
              "completion_criteria": ["SageMaker deployed"],
              "learning_outcomes": ["AWS learned"],
              "supporting_skills": []
            }
          ]
        }
        """
        mock_call.return_value = mock_response

        result = self.agent.run(
            student="demo@example.com",
            career="AI Engineer",
            skill_gap_report=self.gap_ai_engineer
        )
        self.assertEqual(result.validation_status, "Valid")
        self.assertIsNone(result.error_message)
        self.assertEqual(len(result.roadmap.milestones), 4)

        m1 = result.roadmap.milestones[0]
        self.assertEqual(m1.skill, "Machine Learning")
        self.assertEqual(m1.duration_days, 14)
        self.assertEqual(m1.skill_tier, "Core Domain")

    @patch("job_search_ai.agents.roadmap_agent.llm_service.LLMService.call_agent")
    def test_agent_run_mock_success_frontend(self, mock_call):
        """Test B Integration: Run agent with mock LLM response for Frontend Developer."""
        mock_response = """
        {
          "career": "Frontend Developer",
          "readiness_score": 62.5,
          "milestones": [
            {
              "sequence": 1,
              "title": "Redux State Management",
              "type": "Learn",
              "skill": "Redux State Management",
              "skill_tier": "Core Domain",
              "duration_days": 10,
              "objective": "Manage complex React state.",
              "project": "Build an e-commerce cart using Redux Toolkit",
              "completion_criteria": ["Cart completed"],
              "learning_outcomes": ["Redux learned"],
              "supporting_skills": []
            },
            {
              "sequence": 2,
              "title": "Next.js Framework",
              "type": "Build",
              "skill": "Next.js Framework",
              "skill_tier": "Industry",
              "duration_days": 15,
              "objective": "Learn SSR and SSG.",
              "project": "Build a static blog site using Next.js App Router",
              "completion_criteria": ["Blog deployed"],
              "learning_outcomes": ["Next.js learned"],
              "supporting_skills": []
            },
            {
              "sequence": 3,
              "title": "WebAssembly Performance",
              "type": "Connect",
              "skill": "WebAssembly",
              "skill_tier": "Emerging",
              "duration_days": 7,
              "objective": "Run compiled Rust code in the browser.",
              "project": "Build an image filters processor using WebAssembly",
              "completion_criteria": ["WASM running"],
              "learning_outcomes": ["WASM learned"],
              "supporting_skills": []
            }
          ]
        }
        """
        mock_call.return_value = mock_response

        result = self.agent.run(
            student="demo@example.com",
            career="Frontend Developer",
            skill_gap_report=self.gap_frontend
        )
        self.assertEqual(result.validation_status, "Valid")
        self.assertEqual(len(result.roadmap.milestones), 3)

    @patch("job_search_ai.agents.roadmap_agent.llm_service.LLMService.call_agent")
    def test_agent_run_mock_success_devops(self, mock_call):
        """Test C Integration: Run agent with mock LLM response for DevOps Engineer."""
        mock_response = """
        {
          "career": "DevOps Engineer",
          "readiness_score": 50.0,
          "milestones": [
            {
              "sequence": 1,
              "title": "Jenkins CI/CD",
              "type": "Learn",
              "skill": "Jenkins",
              "skill_tier": "Core Domain",
              "duration_days": 14,
              "objective": "Configure Jenkins pipelines.",
              "project": "Write a declarative Jenkinsfile for automated testing",
              "completion_criteria": ["Jenkinsfile runs"],
              "learning_outcomes": ["Jenkins learned"],
              "supporting_skills": []
            },
            {
              "sequence": 2,
              "title": "Ansible Automation",
              "type": "Learn",
              "skill": "Ansible",
              "skill_tier": "Core Domain",
              "duration_days": 12,
              "objective": "Implement configuration management.",
              "project": "Write Ansible playbooks to provision and secure a web server",
              "completion_criteria": ["Ansible playbooks run"],
              "learning_outcomes": ["Ansible learned"],
              "supporting_skills": []
            },
            {
              "sequence": 3,
              "title": "Prometheus Monitoring",
              "type": "Build",
              "skill": "Prometheus",
              "skill_tier": "Industry",
              "duration_days": 10,
              "objective": "Gather node and application metrics.",
              "project": "Expose custom app metrics and configure alert rules",
              "completion_criteria": ["Metrics visible"],
              "learning_outcomes": ["Prometheus learned"],
              "supporting_skills": []
            },
            {
              "sequence": 4,
              "title": "Terraform IaC",
              "type": "Build",
              "skill": "Terraform",
              "skill_tier": "Industry",
              "duration_days": 14,
              "objective": "Provision cloud infrastructure via Terraform.",
              "project": "Define VPC and EC2 instances in code",
              "completion_criteria": ["Terraform applied"],
              "learning_outcomes": ["Terraform learned"],
              "supporting_skills": []
            }
          ]
        }
        """
        mock_call.return_value = mock_response

        result = self.agent.run(
            student="demo@example.com",
            career="DevOps Engineer",
            skill_gap_report=self.gap_devops
        )
        self.assertEqual(result.validation_status, "Valid")
        self.assertEqual(len(result.roadmap.milestones), 4)

    @patch("job_search_ai.agents.roadmap_agent.llm_service.LLMService.call_agent")
    def test_agent_run_mock_success_almost_ready(self, mock_call):
        """Test D Integration: Run agent with mock LLM response for Almost-Ready Student."""
        mock_response = """
        {
          "career": "Data Engineer",
          "readiness_score": 90.0,
          "milestones": [
            {
              "sequence": 1,
              "title": "Snowflake Data Warehouse",
              "type": "Learn",
              "skill": "Snowflake",
              "skill_tier": "Industry",
              "duration_days": 7,
              "objective": "Understand Snowflake cloud storage and compute.",
              "project": "Set up a warehouse and write analytical queries in Snowflake",
              "completion_criteria": ["Queries run"],
              "learning_outcomes": ["Snowflake learned"],
              "supporting_skills": []
            }
          ]
        }
        """
        mock_call.return_value = mock_response

        result = self.agent.run(
            student="demo@example.com",
            career="Data Engineer",
            skill_gap_report=self.gap_almost_ready
        )
        self.assertEqual(result.validation_status, "Valid")
        self.assertEqual(len(result.roadmap.milestones), 1)

    @patch("job_search_ai.agents.roadmap_agent.llm_service.LLMService.call_agent")
    def test_agent_run_llm_failure_invalid_json(self, mock_call):
        """LLM failure: malformed JSON text rejected by parser, falling back to rule-based generation."""
        mock_call.return_value = "This is not json at all."
        result = self.agent.run(
            student="demo@example.com",
            career="AI Engineer",
            skill_gap_report=self.gap_ai_engineer
        )
        self.assertEqual(result.validation_status, "Valid")
        self.assertEqual(result.metrics["generation_mode"], "Rules-based")
        self.assertTrue(len(result.roadmap.milestones) > 0)


class TestRoadmapAgentRegression(IntegrationTestCase):
    """
    Automated regression test suite for RoadmapAgent.
    Performs real roadmap generation and validation for key career paths.
    """

    def test_live_roadmap_generation_regression(self):
        """
        Verify that RoadmapAgent produces 100% schema-compliant and valid roadmaps
        for a set of benchmark careers, running through the self-healing and validation pipeline.
        """
        student_email = "demo_student@example.com"
        careers = [
            "AI Engineer",
            "Frontend Developer",
            "DevOps Engineer for Web Applications",
            "Data Scientist",
            "Frappe Developer"
        ]

        agent = RoadmapAgent()
        
        # Ensure tested careers exist in Career Knowledge so SkillGapService exists validation doesn't throw
        for career in careers:
            if not frappe.db.exists("Career Knowledge", {"career_name": career}):
                skills_list = [
                    {"skill_name": "Git", "skill_type": "Required"},
                    {"skill_name": "Python", "skill_type": "Required"}
                ]
                if career == "Frontend Developer":
                    skills_list = [
                        {"skill_name": "Git", "skill_type": "Required"},
                        {"skill_name": "JavaScript", "skill_type": "Required"}
                    ]
                ck = frappe.get_doc({
                    "doctype": "Career Knowledge",
                    "career_name": career,
                    "active": 1,
                    "skills": skills_list
                })
                ck.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Ensure we have a student record or create a temporary one for the test
        if not frappe.db.exists("Student", student_email):
            # Find a college
            college = frappe.db.get_value("College", {}, "name")
            if not college:
                col = frappe.get_doc({"doctype": "College", "college_name": "Test College"})
                col.insert(ignore_permissions=True)
                college = col.name
            
            student = frappe.get_doc({
                "doctype": "Student",
                "first_name": "Demo",
                "last_name": "Student",
                "email_id": student_email,
                "college": college
            })
            student.insert(ignore_permissions=True)
            frappe.db.commit()

        for career in careers:
            # Reconnect db before LLM call to prevent timeouts
            try:
                frappe.db.connect()
            except Exception:
                pass

            t_start = time.time()
            result = agent.run(student_email, career)
            duration = time.time() - t_start

            # Enforce assertions on result
            self.assertEqual(
                result.validation_status, 
                "Valid", 
                f"Career '{career}' roadmap validation failed with error: {result.error_message}. Raw response: {result.raw_response}"
            )
            self.assertIsNone(result.error_message, f"Expected no error message, got: {result.error_message}")
            self.assertIsNotNone(result.roadmap, "Expected roadmap to be generated")
            self.assertEqual(result.roadmap.career, career, f"Expected career to match '{career}', got '{result.roadmap.career}'")

            # Validate individual milestones
            for m in result.roadmap.milestones:
                self.assertTrue(m.sequence > 0, f"Milestone sequence must be positive, got {m.sequence}")
                self.assertIsNotNone(m.title, "Milestone title cannot be empty")
                self.assertIn(m.type, ["Learn", "Build", "Assess", "Apply", "Connect"], f"Invalid milestone type: {m.type}")
                self.assertIsNotNone(m.skill, "Milestone skill cannot be empty")
                self.assertIn(m.skill_tier, ["Foundation", "Core Domain", "Industry", "Emerging"], f"Invalid skill tier: {m.skill_tier}")
                self.assertTrue(m.duration_days > 0, f"Milestone duration must be positive, got {m.duration_days}")
                self.assertTrue(len(m.objective.strip()) > 0, "Milestone objective cannot be empty")
                self.assertTrue(len(m.project.strip()) > 0, "Milestone project cannot be empty")
                self.assertTrue(isinstance(m.completion_criteria, list) and len(m.completion_criteria) > 0, "Milestone completion criteria cannot be empty")
                self.assertTrue(isinstance(m.learning_outcomes, list) and len(m.learning_outcomes) > 0, "Milestone learning outcomes cannot be empty")
                self.assertTrue(isinstance(m.supporting_skills, list), "Milestone supporting skills must be a list")


class TestRoadmapTemplateCaching(IntegrationTestCase):
    """
    Automated regression test suite for Roadmap Template caching and data isolation.
    """
    def setUp(self):
        super().setUp()
        frappe.db.delete("Roadmap Template", {"career_path": "AI Engineer"})
        frappe.db.delete("Student Path Enrollment")
        frappe.db.commit()

    def test_roadmap_isolation_and_caching(self):
        # 1. Create two test students with different skills
        student_a = "student_a@example.com"
        student_b = "student_b@example.com"
        career_path = "AI Engineer"

        # Ensure college exists
        college = frappe.db.get_value("College", {}, "name") or "Test College"
        if not frappe.db.exists("College", college):
            frappe.get_doc({"doctype": "College", "college_name": college}).insert(ignore_permissions=True)

        # Create student A
        if not frappe.db.exists("Student", student_a):
            s_a = frappe.get_doc({
                "doctype": "Student",
                "first_name": "Student",
                "last_name": "A",
                "email_id": student_a,
                "college": college
            })
            s_a.insert(ignore_permissions=True)
        
        # Create student B
        if not frappe.db.exists("Student", student_b):
            s_b = frappe.get_doc({
                "doctype": "Student",
                "first_name": "Student",
                "last_name": "B",
                "email_id": student_b,
                "college": college
            })
            s_b.insert(ignore_permissions=True)

        # Ensure Skills exist in database
        for s in ["Machine Learning", "Deep Learning", "PyTorch", "AWS"]:
            if not frappe.db.exists("Skill", s):
                frappe.get_doc({"doctype": "Skill", "skill_name": s}).insert(ignore_permissions=True)

        # Add different verified skills to Student A and Student B
        frappe.db.delete("Student Skill", {"student": ["in", [student_a, student_b]]})
        
        doc_a = frappe.get_doc({
            "doctype": "Student Skill",
            "student": student_a,
            "skill": "Machine Learning",
            "current_level": "Intermediate",
            "status": "Verified",
            "ai_verified": 1
        }).insert(ignore_permissions=True)
        frappe.db.set_value("Student Skill", doc_a.name, "status", "Verified")

        doc_b = frappe.get_doc({
            "doctype": "Student Skill",
            "student": student_b,
            "skill": "Deep Learning",
            "current_level": "Intermediate",
            "status": "Verified",
            "ai_verified": 1
        }).insert(ignore_permissions=True)
        frappe.db.set_value("Student Skill", doc_b.name, "status", "Verified")

        # Ensure Career Path exists and has prerequisites
        if not frappe.db.exists("Career Path", career_path):
            cp = frappe.get_doc({
                "doctype": "Career Path",
                "path_name": career_path,
                "target_role": career_path,
                "difficulty_level": "Moderate",
                "estimated_duration_months": 6
            })
            cp.append("prerequisite_skills", {"prerequisite_skills": "Machine Learning", "level": "Intermediate"})
            cp.append("prerequisite_skills", {"prerequisite_skills": "Deep Learning", "level": "Intermediate"})
            cp.append("path_milestone", {"milestone_title": "Master PyTorch", "milestone_type": "Learn", "skill": "PyTorch", "required_skill_level": "Intermediate", "duration_days": 14})
            cp.append("path_milestone", {"milestone_title": "Master AWS", "milestone_type": "Learn", "skill": "AWS", "required_skill_level": "Intermediate", "duration_days": 10})
            cp.insert(ignore_permissions=True)

        frappe.db.commit()

        # Mock the agent run to return a generic template
        # containing milestones for ALL career path skills: Machine Learning, Deep Learning, PyTorch, AWS.
        mock_generic_roadmap = RoadmapProfile(
            career=career_path,
            readiness_score=0.0,
            milestones=[
                RoadmapMilestone(
                    sequence=1, title="Master ML", type="Learn", skill="Machine Learning",
                    skill_tier="Foundation", duration_days=10, objective="ML Obj", project="ML Proj",
                    points=["point1"], completion_criteria=["crit1"], learning_outcomes=["out1"], supporting_skills=[]
                ),
                RoadmapMilestone(
                    sequence=2, title="Master DL", type="Learn", skill="Deep Learning",
                    skill_tier="Core Domain", duration_days=14, objective="DL Obj", project="DL Proj",
                    points=["point2"], completion_criteria=["crit2"], learning_outcomes=["out2"], supporting_skills=[]
                ),
                RoadmapMilestone(
                    sequence=3, title="Master PyTorch", type="Build", skill="PyTorch",
                    skill_tier="Core Domain", duration_days=14, objective="PyTorch Obj", project="PyTorch Proj",
                    points=["point3"], completion_criteria=["crit3"], learning_outcomes=["out3"], supporting_skills=[]
                ),
                RoadmapMilestone(
                    sequence=4, title="Master AWS", type="Apply", skill="AWS",
                    skill_tier="Industry", duration_days=10, objective="AWS Obj", project="AWS Proj",
                    points=["point4"], completion_criteria=["crit4"], learning_outcomes=["out4"], supporting_skills=[]
                )
            ]
        )

        with patch("job_search_ai.agents.roadmap_agent.agent.RoadmapAgent.run") as mock_run, \
             patch("nexedu.path_finder.api.path_enrollment.build_roadmap_template_from_career_path") as mock_seed:
            from job_search_ai.agents.roadmap_agent.schemas import RoadmapResult
            mock_run.return_value = RoadmapResult(
                roadmap=mock_generic_roadmap,
                validation_status="Valid",
                metrics={"generation_mode": "AI"}
            )

            # 2. Enroll Student A
            # This is a cache MISS, so it should call RoadmapAgent.run(student="Generic", career=career_path)
            from nexedu.path_finder.api.path_enrollment import enroll_student
            res_a = enroll_student(student=student_a, career_path=career_path, path_generation_mode="AI")
            self.assertEqual(res_a["status"], "success")

            # Check that the background task is enqueued (the enrollment status is "Generating")
            enroll_a = frappe.get_doc("Student Path Enrollment", res_a["enrollment"])
            self.assertEqual(enroll_a.status, "Generating")

            # Run the background generation task manually
            from job_search_ai.tasks import generate_personalized_roadmap
            generate_personalized_roadmap(enroll_a.name)

            # Reload enrollment A
            enroll_a.reload()
            self.assertEqual(enroll_a.status, "Active")
            
            # Since Student A has "Machine Learning" verified, the personalized roadmap
            # must auto-skip/complete "Machine Learning" and leave the next one as "In Progress".
            ml_progress = [m for m in enroll_a.milestone_progress if m.skill == "Machine Learning"]
            self.assertEqual(len(ml_progress), 1)
            self.assertEqual(ml_progress[0].status, "Completed")
            self.assertEqual(ml_progress[0].is_auto_skipped, 1)

            dl_progress = [m for m in enroll_a.milestone_progress if m.skill == "Deep Learning"]
            self.assertEqual(len(dl_progress), 1)
            self.assertEqual(dl_progress[0].status, "In Progress")
            self.assertEqual(dl_progress[0].is_auto_skipped, 0)

            # Check that the Roadmap Template was successfully cached
            self.assertTrue(frappe.db.exists("Roadmap Template", career_path))

            # 3. Enroll Student B
            # This is a cache HIT, so it should personalize and activate IMMEDIATELY (sync flow)
            res_b = enroll_student(student=student_b, career_path=career_path, path_generation_mode="AI")
            self.assertEqual(res_b["status"], "success")

            enroll_b = frappe.get_doc("Student Path Enrollment", res_b["enrollment"])
            self.assertEqual(enroll_b.status, "Active")  # Should be active immediately!

            # Since Student B has "Deep Learning" verified, the personalized roadmap
            # must auto-skip/complete "Deep Learning" and set the first one ("Machine Learning") to "In Progress".
            ml_progress_b = [m for m in enroll_b.milestone_progress if m.skill == "Machine Learning"]
            self.assertEqual(len(ml_progress_b), 1)
            self.assertEqual(ml_progress_b[0].status, "In Progress")
            self.assertEqual(ml_progress_b[0].is_auto_skipped, 0)

            dl_progress_b = [m for m in enroll_b.milestone_progress if m.skill == "Deep Learning"]
            self.assertEqual(len(dl_progress_b), 1)
            self.assertEqual(dl_progress_b[0].status, "Completed")
            self.assertEqual(dl_progress_b[0].is_auto_skipped, 1)
