from enum import Enum


class ReviewDecision(str, Enum):
    Approved = "Approved"
    Rejected = "Rejected"
