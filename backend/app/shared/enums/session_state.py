from enum import Enum


class SessionState(str, Enum):
    Active = "Active"
    WaitingReview = "WaitingReview"
    Approved = "Approved"
    Closed = "Closed"
    Rejected = "Rejected"
