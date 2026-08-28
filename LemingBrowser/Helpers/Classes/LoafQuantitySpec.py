#*************** Depracated Class Because Now everything is in tram files *********************
from dataclasses import dataclass

@dataclass(frozen=True)
class LoafQuantitySpec:
    expression: str
    dimension: int

    # 1D
    column: str | None = None

    # 2D
    x_column: str | None = None
    y_column: str | None = None

    @property
    def title(self) -> str:
        if self.dimension == 1:
            return str(self.column)

        return f"{self.y_column} versus {self.x_column}"