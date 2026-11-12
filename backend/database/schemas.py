from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str
    role: Optional[str] = "admin"
    username: Optional[str] = None
    plan: Optional[str] = None
    can_reboot_network: Optional[bool] = False
    can_manage_cards: Optional[bool] = False
    can_manage_users: Optional[bool] = False
    is_unlimited: Optional[bool] = False
    subscription_expires: Optional[str] = None


class UserProfileResponse(BaseModel):
    username: str
    role: str
    plan: Optional[str] = "monthly"
    can_reboot_network: Optional[bool] = False
    can_manage_cards: Optional[bool] = False
    can_manage_users: Optional[bool] = False
    is_unlimited: Optional[bool] = False
    subscription_expires: Optional[str] = None
    is_active: Optional[bool] = True


class TokenData(BaseModel):
    username: Optional[str] = None

class AdminBase(BaseModel):
    username: str

class AdminCreate(AdminBase):
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class RegistrationCreate(BaseModel):
    username: str
    password: str
    plan: Optional[str] = "monthly"


class RegistrationResponse(BaseModel):
    id: int
    username: str
    plan: Optional[str] = "monthly"
    price: Optional[int] = 20
    paid: bool
    payment_ref: Optional[str] = None
    receipt_image: Optional[str] = None
    processed: bool
    payment_message: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}

class AdminResponse(AdminBase):
    id: int
    is_active: bool
    model_config = {"from_attributes": True}

class CardBatchResponse(BaseModel):
    id: int
    profile: str
    count: int
    created_at: datetime
    pdf_path: Optional[str]
    model_config = {"from_attributes": True}


class ClientResponse(BaseModel):
    id: int
    username: str
    plan: Optional[str] = "monthly"
    can_reboot_network: Optional[bool] = False
    is_active: bool
    subscription_expires: Optional[datetime]
    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    id: int
    username: str
    sender: str
    message: str
    created_at: datetime
    model_config = {"from_attributes": True}


class PlanInfo(BaseModel):
    id: str
    name: str
    price: int
    days: int
    can_reboot_network: bool
    can_disconnect_users: bool
    can_print_cards: bool
    chatbot_tier: str
    daily_chat_limit: Optional[int] = None
    features: List[str]


class ChatQuotaResponse(BaseModel):
    username: str
    plan: str
    plan_name: str
    daily_limit: Optional[int] = None
    used_today: int
    remaining_today: Optional[int] = None
    unlimited: bool


class BotStatusResponse(BaseModel):
    enabled: bool
    name: str
    last_run: Optional[str] = None
    total_auto_approved: int
    mode: str


class OwnerNotificationResponse(BaseModel):
    pending_count: int
    unpaid_count: int
    paid_pending_count: int
    recent_requests: List[RegistrationResponse]
