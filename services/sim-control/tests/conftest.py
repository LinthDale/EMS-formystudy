"""Use the canonical BFF sources in checkout tests; Docker already copies them."""
import sys
try:
    from bff.simulator_control import contracts, body_limit
except ModuleNotFoundError as error:
    if error.name != "bff":
        raise
else:
    sys.modules["sim_control.contracts"] = contracts
    sys.modules["sim_control.body_limit"] = body_limit
