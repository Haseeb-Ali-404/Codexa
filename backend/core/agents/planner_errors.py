class PlannerStageError(Exception):
    def __init__(self, stage: int, errors: list[str]):
        self.stage = stage
        self.errors = errors
        super().__init__(f"Stage {stage} failed after max retries: {errors}")


class PlannerCycleError(Exception):
    def __init__(self, cycle_path: list[str]):
        self.cycle_path = cycle_path
        super().__init__(f"Circular dependency detected: {' -> '.join(cycle_path)}")