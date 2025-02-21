from diffsync import DiffSyncModel


class ProjectModel(DiffSyncModel):
    _modelname = "project"
    _identifiers = ("id",)
    _attributes = (
        "name",
        "description",
    )

    id: str
    name: str
    description: str
