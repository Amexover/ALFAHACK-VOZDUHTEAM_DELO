from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.enums import BorrowingMode, LegalForm, ProductId

ProfileKey = Literal["industry", "months_operating", "monthly_revenue", "monthly_debt_payments", "purpose_details"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfilePatch(Strict):
    industry: str | None = Field(None, max_length=200)
    months_operating: int | None = Field(None, ge=0, le=1200)
    monthly_revenue: int | None = Field(None, ge=0, le=10**12)
    monthly_debt_payments: int | None = Field(None, ge=0, le=10**12)
    purpose_details: str | None = Field(None, max_length=2000)


class LoginIn(Strict):
    login: str
    password: str


class CompanyIn(Strict):
    legal_form: LegalForm
    name: str = Field(max_length=200)
    registration_number: str = Field(max_length=30)


class QuoteIn(Strict):
    company_id: int
    borrowing_mode: BorrowingMode
    term_months: int
    amount: int | None = None
    existing_loan_id: int | None = None


class DraftCreateIn(Strict):
    borrowing_mode: BorrowingMode


class DraftPatchIn(Strict):
    amount: int | None = None
    term_months: int | None = None
    product_id: ProductId | None = None
    existing_loan_id: int | None = None
    business_profile: ProfilePatch | None = None
    current_step: str | None = Field(None, max_length=50)


class SubmitIn(Strict):
    confirm_data: bool = False


class ClientAnswerIn(Strict):
    answer_text: str = Field(max_length=4000)
    fields: ProfilePatch = Field(default_factory=ProfilePatch)


class RequestInfoIn(Strict):
    message: str = Field(min_length=1, max_length=4000)
    requested_fields: list[ProfileKey] = Field(default_factory=list)


class ApproveIn(Strict):
    comment: str | None = Field(None, max_length=2000)


class CounterOfferIn(Strict):
    amount: int
    term_months: int
    rate: Decimal = Field(ge=Decimal("1"), le=Decimal("60"), decimal_places=1)
    comment: str = Field(min_length=1, max_length=2000)


class RejectIn(Strict):
    reason_code: str
    comment: str | None = Field(None, max_length=2000)


class BureauToggleIn(Strict):
    available: bool
