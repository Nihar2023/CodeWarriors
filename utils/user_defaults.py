"""Ensure user records include profile, onboarding, and assessment fields."""

from __future__ import annotations

from typing import Any


PROFILE_TEMPLATE = {
    "age": None,
    "year_of_college": None,
    "college_name": None,
    "learning_goals": "",
}


def ensure_user_defaults(user: dict[str, Any]) -> dict[str, Any]:
    """Mutate and return user with required keys for new features."""
    if "profile" not in user or not isinstance(user.get("profile"), dict):
        user["profile"] = {**PROFILE_TEMPLATE}
    else:
        for k, v in PROFILE_TEMPLATE.items():
            user["profile"].setdefault(k, v)
    user["profile"].setdefault("onboarding_complete", False)

    user.setdefault("entry_quiz_completed", False)
    user.setdefault("skill_level", None)  # beginner | intermediate | advanced
    return user


def merge_profile_update(user: dict[str, Any], **fields) -> None:
    ensure_user_defaults(user)
    for key, val in fields.items():
        if key == "full_name" and val is not None:
            user["full_name"] = str(val).strip()
        elif key == "college_name" and val is not None:
            user["profile"]["college_name"] = str(val).strip()
        elif key == "learning_goals" and val is not None:
            user["profile"]["learning_goals"] = str(val).strip()
        elif key in {"age", "year_of_college", "onboarding_complete"} and val is not None:
            user["profile"][key] = val
