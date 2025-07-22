from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class ServiceCategory:
    id: str
    title: str
    created_at: datetime

@dataclass
class Service:
    id: str
    title: str
    description: str
    price: str
    icon: str
    category_id: str
    images: Optional[List[str]] = None
    created_at: Optional[datetime] = None

@dataclass
class Appointment:
    client_name: str
    appointment_time: datetime
    service_id: str
    id: Optional[str] = None
    client_telegram_id: Optional[int] = None
    client_phone: Optional[str] = None
    status: str = 'active'
    reminded: bool = False
    created_at: Optional[datetime] = None
    # Это поле не из БД, но мы используем его для удобства
    service_title: Optional[str] = None