

from abc import ABC, abstractmethod

class BaseAsset(ABC):
    def __init__(self, customer_id: str):
        self.customer_id = customer_id

    @abstractmethod
    def register_variables(self, m):
        ...

    @abstractmethod
    def register_constraints(self, m):
        ...
