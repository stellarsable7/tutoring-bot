from pydantic import BaseModel, ConfigDict, HttpUrl


class DiscoveredDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_id: int
    category_id: int
    subject_id: int
    document_type_id: int
    year: int | None
    document_name: str
    file_name: str
    detail_url: HttpUrl
    download_url: HttpUrl
    assignable: bool = False


class DiscoveredPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_document: DiscoveredDocument
    solution_document: DiscoveredDocument


class DiscoveryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    pairs: tuple[DiscoveredPair, ...]
    unpaired: tuple[DiscoveredDocument, ...]
    page: int
    pages: int
    total: int
