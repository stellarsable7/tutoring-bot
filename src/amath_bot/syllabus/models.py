from pydantic import BaseModel, ConfigDict


class Objective(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    domain: str
    topic: str
    description: str


class Syllabus(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    objectives: tuple[Objective, ...]
