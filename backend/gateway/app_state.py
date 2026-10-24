"""Process-wide gateway singletons. Routes read these at request time, so tests can swap them."""

import os

from company import get_company
from company.types import CompanyAPI
from gateway import upstream
from gateway.events import EventBus
from gateway.injector import NotificationQueue
from gateway.memory import CallMemory
from gateway.roles import Role, load_roles

bus: EventBus = EventBus()
roles: dict[str, Role] = load_roles()
company: CompanyAPI = get_company()
queue: NotificationQueue = NotificationQueue()
memory: CallMemory = CallMemory()
injection_mode: str = os.getenv("INJECTION_MODE", "user_message")
connect_upstream = upstream.connect_boson
active_call = None  # CallSession | None, set by the WS route
