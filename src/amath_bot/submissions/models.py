from pydantic import BaseModel, ConfigDict


class SubmissionMedia(BaseModel):
    model_config = ConfigDict(frozen=True)

    position: int
    telegram_file_id: str
    mime_type: str
    media_kind: str


class Attempt(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    assignment_id: int
    status: str
    media: tuple[SubmissionMedia, ...]

    @property
    def media_count(self) -> int:
        return len(self.media)

