"""Process-wide gateway singletons. Routes read these at request time, so tests can swap them."""

from company import get_company
from company.types import CompanyAPI
from gateway.events import EventBus
from gateway.roles import Role, load_roles

bus: EventBus = EventBus()
roles: dict[str, Role] = load_roles()
company: CompanyAPI = get_company()
active_call = None  # CallSession | None, set by the WS route (A7)
