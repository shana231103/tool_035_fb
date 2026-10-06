# File: backend/app/infrastructure/automation/form_selectors.py
class MetaFormSelectors:
    """English labels observed live 2026-10-03; OTP/receipt still require live verification."""
    FORM_URL = "https://help.meta.com/requests/1523801815366035/"
    COPYRIGHT = "Copyright Original works of authorship, such as films, music or books"
    PLATFORM = "Facebook"
    JURISDICTION = "Where are you asserting rights?"
    OWNER_ROLE = "Yes"
    REPRESENTATIVE_ROLE = "No, but I'm authorised to represent the rights owner"
    OWNER_NAME = "What is the name of the rights owner?"
    TARGET = "Provide the URLs/IDs leading directly to the content that you're reporting"
    ORIGINAL = "Provide an example of your copyrighted work that you believe has been infringed"
    EXPLANATION = "Describe how you believe that this content infringes your intellectual property rights"
    SENDER = "Your full name"
    EMAIL = "Email"
    CONFIRM_EMAIL = "Confirm email address"
    SIGNATURE = "Electronic signature"
    COURT_ORDER = "(Optional) If you have a court order deeming the content unlawful, attach it"
    # Explicit adapter contract, not certified against the live post-request DOM.
    CODE = "Verification code"
    VERIFY = "Verify"
    RESEND = "Resend code"
    VERIFIED = "Email verified"
    INVALID_CODE = "Invalid code"
    RECEIPT = "Your report has been submitted"
    RECEIPT_THANK_YOU = "Thank you."
    RECEIPT_REVIEW_MSG = "The relevant teams will review your request as soon as possible."
    RECEIPT_NEW_REQUEST = "New request"


class FormContractError(ValueError):
    """Unexpected page/control or validation failure, safe to display without field values."""

    def __init__(self, message="", *, stage=None, reason=None):
        super().__init__(message)
        self.stage, self.reason = stage, reason
