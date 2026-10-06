# File: backend/app/infrastructure/automation/otp_dom_contract.py
from dataclasses import dataclass
from app.infrastructure.automation.form_selectors import FormContractError


@dataclass(frozen=True)
class OtpDomContract:
    """Explicit evidence profile. The default deliberately has no live certification."""
    version: str = "uncertified"
    certified: bool = False
    test_only: bool = False
    region: str = ""
    revision_attribute: str = ""
    code_label: str = ""
    request_label: str = ""
    resend_label: str = ""
    verify_label: str = ""
    sent_text: str = ""
    verifying_text: str = ""
    verified_text: str = ""
    rejected_text: str = ""
    mode: str = "explicit_button"
    evidence_reference: tuple[str, ...] = ()

    def assert_usable(self, *, allow_test: bool = False) -> None:
        if self.mode == "meta_auto_fill":
            observed = type(self).meta_report()
            if self != observed:
                raise FormContractError("Meta email verification evidence profile is unsupported.")
            return
        if self.mode != "explicit_button":
            raise FormContractError("Email verification mode is unsupported.")
        required = (self.region, self.revision_attribute, self.code_label,
                    self.request_label, self.verify_label, self.sent_text,
                    self.verified_text, self.rejected_text)
        if not all(required) or (not self.certified and not (self.test_only and allow_test)):
            raise FormContractError("Email verification DOM evidence is not certified.")
        if self.test_only and not allow_test:
            raise FormContractError("Synthetic email verification evidence is test-only.")

    @classmethod
    def synthetic(cls):
        return cls(version="synthetic-test-v1", test_only=True, region="#email-otp",
            revision_attribute="data-revision", code_label="Mailbox verification code",
            request_label="Send mailbox code", resend_label="Send another mailbox code",
            verify_label="Confirm mailbox code", sent_text="Mailbox code sent",
            verifying_text="Checking mailbox code", verified_text="Mailbox confirmed",
            rejected_text="Mailbox code rejected")

    @classmethod
    def meta_report(cls):
        """Observed display contract; runtime structure must still prove each transition."""
        return cls(version="meta-report-dom-v1", mode="meta_auto_fill", region="body",
            code_label="Verification code", request_label="Request code", sent_text="Code sent",
            rejected_text="The code you entered is incorrect. Please try again.",
            evidence_reference=("docs/pic/page4.2.png", "docs/pic/page4.optmail.png",
                "docs/pic/page4.otpmail.wrong.png", "docs/pic/page4.otpmail.right.png"))
