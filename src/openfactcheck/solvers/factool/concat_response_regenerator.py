from openfactcheck import FactCheckerState, StandardTaskSolver, Solver

@Solver.register("concat_response_generator", "claim_info", "output")
class ConcatResponseRegenerator(StandardTaskSolver):
    """
    A solver to concatenate the edited claims into a single document.
    """
    def __init__(self, args):
        super().__init__(args)

    def __call__(self, state: FactCheckerState, *args, **kwargs):
        claim_info = state.get(self.input_name)

        edited_claims = [v["edited_claims"] for _, v in claim_info.items()]
        revised_document = " ".join(edited_claims).strip()
        state.set(self.output_name, revised_document)
        return True, state
