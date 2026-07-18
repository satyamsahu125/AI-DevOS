from enum import Enum


class WorkflowState(str, Enum):
    Created = "Created"
    Running = "Running"
    WaitingForReview = "WaitingForReview"
    Approved = "Approved"
    Completed = "Completed"
