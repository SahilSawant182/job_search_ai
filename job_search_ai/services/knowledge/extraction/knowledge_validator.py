# -*- coding: utf-8 -*-

class KnowledgeValidator:
    """
    Computes a Quality Score (0-100) for extracted career intelligence facts.
    Rejects any record with a score below 50.
    """

    @staticmethod
    def validate(facts: dict, source_reliability: int) -> dict:
        """
        Validate career facts and compute a Quality Score.
        Returns:
            dict: {
                "is_valid": bool,
                "quality_score": int,
                "reasons": list[str]
            }
        """
        score = 0
        reasons = []

        # 1. Source Reliability (Max 20 points)
        source_points = int(source_reliability * 0.2)
        score += source_points
        if source_points < 10:
            reasons.append(f"Low source reliability score: {source_reliability}")

        # 2. Fact Completeness (Max 30 points)
        completeness_points = 0
        critical_fields = ["career_name", "industry", "category", "demand", "stage", "summary"]
        for field in critical_fields:
            if facts.get(field):
                completeness_points += 5
            else:
                reasons.append(f"Missing critical field: {field}")
        score += completeness_points

        # 3. Summary Quality (Max 15 points)
        summary = facts.get("summary", "")
        summary_points = 0
        if summary and 10 <= len(summary) <= 300:
            summary_points += 10
            # Check for generic boilerplate
            junk_words = ["cookie", "click here", "read more", "advertisement"]
            if not any(jw in summary.lower() for jw in junk_words):
                summary_points += 5
            else:
                reasons.append("Summary contains web boilerplate")
        else:
            reasons.append(f"Summary length invalid: {len(summary)} (must be 10-300 chars)")
        score += summary_points

        # 4. Skill Count (Max 20 points)
        skills = facts.get("skills", [])
        skill_points = 0
        n_skills = len(skills)
        if n_skills > 10:
            skill_points = 20
        elif n_skills >= 6:
            skill_points = 15
        elif n_skills >= 3:
            skill_points = 10
        elif n_skills >= 1:
            skill_points = 5
        else:
            reasons.append("No skills extracted")
        score += skill_points

        # 5. Company Count (Max 15 points)
        companies = facts.get("companies", [])
        company_points = 0
        n_companies = len(companies)
        if n_companies > 3:
            company_points = 15
        elif n_companies >= 2:
            company_points = 10
        elif n_companies >= 1:
            company_points = 5
        else:
            reasons.append("No hiring companies extracted")
        score += company_points

        is_valid = score >= 50

        return {
            "is_valid": is_valid,
            "quality_score": score,
            "reasons": reasons
        }
