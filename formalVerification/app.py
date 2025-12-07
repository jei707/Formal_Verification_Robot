from flask import Flask, request, jsonify
from flask_cors import CORS
from pyswip import Prolog

app = Flask(__name__)
CORS(app)

prolog = Prolog()
prolog.consult("rules.pl")


def reset_world_state():
    """Reset Prolog world to initial state before each verification."""
    # Clear any previous world facts
    list(prolog.query("retractall(world(_))"))
    # Initial world facts - adjust these to match your rules.pl
    list(prolog.query("assertz(world(powered_off))"))
    list(prolog.query("assertz(world(battery_full))"))
    list(prolog.query("assertz(world(object_detected))"))


def get_missing_preconditions(action_atom):
    """Ask Prolog which preconditions are missing for a given action."""
    query = (
        f"findall(Cond, "
        f"   (precondition('{action_atom}', Cond), \\+ world(Cond)), "
        f"   Missing)"
    )
    res = list(prolog.query(query))
    if not res:
        return []
    missing = res[0]["Missing"]
    # Convert bytes/atoms to strings
    out = []
    for m in missing:
        if isinstance(m, bytes):
            out.append(m.decode("utf-8"))
        else:
            out.append(str(m))
    return out


def get_final_world_state():
    """Return current world/1 facts as a list of strings."""
    res = list(prolog.query("findall(S, world(S), States)."))
    if not res:
        return []
    states = res[0]["States"]
    out = []
    for s in states:
        if isinstance(s, bytes):
            out.append(s.decode("utf-8"))
        else:
            out.append(str(s))
    return out


@app.route("/", methods=["GET"])
def home():
    return "Formal Verification Server is running"


@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json()

    if "actions" not in data:
        return jsonify({"error": "Missing 'actions' in request"}), 400

    actions = data["actions"]
    if not isinstance(actions, list):
        return jsonify({"error": "Actions must be a list"}), 400

    # Reset simulated world before running sequence
    reset_world_state()

    results = []
    all_valid = True

    battery_level = 100  # numeric battery percentage
    battery_history = []

    for action in actions:
        if not isinstance(action, str):
            result = "invalid_format"
            reason = "Action value must be a string."
            results.append({
                "action": str(action),
                "result": result,
                "reason": reason,
                "battery": battery_level
            })
            all_valid = False
            battery_history.append(battery_level)
            continue

        action_atom = action.lower().strip()
        query = f"validate('{action_atom}', Result)."

        try:
            res_list = list(prolog.query(query))

            if res_list:
                result = res_list[0]["Result"]
                if isinstance(result, bytes):
                    result = result.decode("utf-8")
            else:
                result = "invalid_action"
        except Exception:
            result = "error_processing"

        # Build reasoning text
        if result == "valid":
            reason = "All preconditions satisfied."
        elif result == "invalid_action":
            reason = "Action is not defined in the rule base."
        elif result == "invalid_format":
            reason = "Action value must be a string."
        elif result == "error_processing":
            reason = "Internal error while querying Prolog."
        elif result == "precondition_failed":
            missing = get_missing_preconditions(action_atom)
            if missing:
                reason = "Missing preconditions: " + ", ".join(missing)
            else:
                reason = "One or more preconditions are not satisfied."
        else:
            reason = "Unknown result."

        # Only drain battery for valid actions
        if result == "valid":
            if action_atom in ["moveforward", "turnleft", "turnright"]:
                battery_level = max(0, battery_level - 20)
            elif action_atom in ["scanarea", "pickobject", "releaseobject"]:
                battery_level = max(0, battery_level - 10)
            # poweron, poweroff, checkbattery, stop -> no drain

        battery_history.append(battery_level)

        results.append({
            "action": action_atom,
            "result": result,
            "reason": reason,
            "battery": battery_level
        })

        if result != "valid":
            all_valid = False

    summary = "VALID SEQUENCE" if all_valid else "INVALID SEQUENCE"
    final_state = get_final_world_state()

    return jsonify({
        "validation": results,
        "summary": summary,
        "final_state": final_state,
        "final_battery": battery_level,
        "battery_history": battery_history
    }), 200


if __name__ == "__main__":
    app.run(debug=True)
