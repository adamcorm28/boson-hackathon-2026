"""Company layer: the gateway's view of Dunder Mifflin (issues, agents, costs).

`get_company()` returns a process-wide CompanyAPI, chosen by COMPANY_BACKEND:
"mock" (default, in-memory seed data) or "paperclip" (the real REST client).
"""

import os

from company.types import CompanyAPI

_instance: CompanyAPI | None = None


def get_company() -> CompanyAPI:
    global _instance
    if _instance is None:
        backend = os.getenv("COMPANY_BACKEND", "mock")
        if backend == "mock":
            from company.mock import MockCompany

            _instance = MockCompany()
        elif backend == "paperclip":
            from company.paperclip import PaperclipCompany  # added in task B8

            _instance = PaperclipCompany.from_env()
        else:
            raise ValueError(f"Unknown COMPANY_BACKEND {backend!r}; use 'mock' or 'paperclip'")
    return _instance
