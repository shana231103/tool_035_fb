# File: backend/app/domain/value_objects/explanation.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ExplanationText:
    content: str

    MAX_LENGTH: int = 500

    @classmethod
    def _normalize_newlines(cls, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @classmethod
    def create_standard_dmca(cls, violation_type: str = "reproduction") -> "ExplanationText":
        vt = (violation_type or "").strip().lower()
        if vt in ["video", "reel"]:
            infringement_clause = (
                "The reported content re-uploads and republishes my original copyrighted video "
                "without authorization, permission, or license."
            )
        elif vt in ["photo", "image"]:
            infringement_clause = (
                "The reported content reproduces and displays my original copyrighted photograph/artwork "
                "without authorization, permission, or license."
            )
        else:
            infringement_clause = (
                "The reported content reproduces and/or republishes my copyrighted work "
                "without my authorization, permission, or license."
            )

        template = (
            "I am the copyright owner of the original work identified in this report. "
            "The original work was created by me and is verified through the original source URL provided above. "
            f"{infringement_clause} "
            "The unauthorized use interferes with my exclusive rights. "
            "I respectfully request that Meta review the reported material and take appropriate action under its copyright policies."
        )
        normalized = cls._normalize_newlines(template).strip()
        if len(normalized) > cls.MAX_LENGTH:
            raise ValueError(f"Standard template exceeds {cls.MAX_LENGTH} characters.")
        return cls(content=normalized)

    @classmethod
    def custom(cls, custom_text: str) -> "ExplanationText":
        text = cls._normalize_newlines(custom_text or "").strip()
        if not text:
            return cls.create_standard_dmca()
        if len(text) > cls.MAX_LENGTH:
            raise ValueError(f"Explanation text must not exceed {cls.MAX_LENGTH} characters (got {len(text)}).")
        return cls(content=text)
