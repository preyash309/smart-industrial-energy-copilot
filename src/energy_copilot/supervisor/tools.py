"""Public service interface. Only opaque identities and trusted plan-mode enums."""
from typing import Protocol

class SupervisorTools(Protocol):
    def call(self,tool:str,arguments:dict):...
