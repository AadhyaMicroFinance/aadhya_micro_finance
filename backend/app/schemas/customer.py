"""
Customer schemas — onboarding fields.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class CustomerCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, pattern=r"^(MALE|FEMALE|OTHER)$")
    mobile_number: str = Field(..., min_length=5, max_length=20)
    alternate_mobile: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)
    pan_number: Optional[str] = Field(None, max_length=10)
    aadhar_number: Optional[str] = Field(None, max_length=12)
    occupation: Optional[str] = Field(None, max_length=100)
    nominee_name: Optional[str] = Field(None, max_length=255)
    nominee_phone: Optional[str] = Field(None, max_length=20)
    nominee_relation: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, pattern=r"^(MALE|FEMALE|OTHER)$")
    mobile_number: Optional[str] = Field(None, min_length=5, max_length=20)
    alternate_mobile: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)
    pan_number: Optional[str] = Field(None, max_length=10)
    aadhar_number: Optional[str] = Field(None, max_length=12)
    occupation: Optional[str] = Field(None, max_length=100)
    nominee_name: Optional[str] = Field(None, max_length=255)
    nominee_phone: Optional[str] = Field(None, max_length=20)
    nominee_relation: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(ACTIVE|INACTIVE|BLOCKED)$")


class CustomerResponse(BaseModel):
    id: str
    customer_code: str
    full_name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    mobile_number: str
    alternate_mobile: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    pan_number: Optional[str] = None
    aadhar_number: Optional[str] = None
    occupation: Optional[str] = None
    nominee_name: Optional[str] = None
    nominee_phone: Optional[str] = None
    nominee_relation: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
