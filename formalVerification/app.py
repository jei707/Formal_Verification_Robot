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
    # Initial world facts
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

@app.route("/fsm", methods=["POST"])
def get_fsm():
    """Get FSM visualization data for an action sequence."""
    data = request.get_json()
    
    # Handle both string and list format
    if isinstance(data.get("actions"), str):
        actions_raw = data["actions"]
        actions = [a.strip() for a in actions_raw.strip("[]").split(",")]
    elif isinstance(data.get("actions"), list):
        actions = [str(a).strip().lower() for a in data["actions"]]
    else:
        return jsonify({"error": "Actions must be a string or list"}), 400
    
    # Reset world state
    reset_world_state()
    
    # Reuse verification logic but return only FSM data
    fsm_nodes = []
    fsm_edges = []
    current_state = get_current_world_state()
    state_id_map = {}
    node_counter = 0
    
    # Create initial state node
    initial_label = state_to_label(current_state)
    state_id_map[frozenset(current_state)] = node_counter
    fsm_nodes.append({
        "id": node_counter,
        "label": f"S{node_counter}: {initial_label}",
        "state": sorted(list(current_state)),
        "step": 0,
        "type": "initial"
    })
    node_counter += 1
    
    for step, action in enumerate(actions, 1):
        action_atom = action.strip().lower()
        from_state_id = state_id_map.get(frozenset(current_state))
        
        # Check if action exists
        action_check = list(prolog.query(f"action('{action_atom}')."))
        if not action_check:
            continue
        
        # Get all preconditions
        precondition_query = list(prolog.query(f"precondition('{action_atom}', Cond)."))
        preconditions = []
        for item in precondition_query:
            cond = item["Cond"]
            if isinstance(cond, bytes):
                preconditions.append(cond.decode("utf-8"))
            else:
                preconditions.append(str(cond))
        
        # Validate using Prolog (which applies state changes)
        query = f"validate('{action_atom}', Result)."
        try:
            res_list = list(prolog.query(query))
            if res_list:
                result = res_list[0]["Result"]
                if isinstance(result, bytes):
                    result = result.decode("utf-8")
                is_valid = (result == "valid")
            else:
                is_valid = False
        except Exception:
            is_valid = False
        
        # Get new state from Prolog
        new_state = get_current_world_state()
        
        # Create or get state node
        state_key = frozenset(new_state)
        if state_key not in state_id_map:
            state_id_map[state_key] = node_counter
            state_label = state_to_label(new_state)
            fsm_nodes.append({
                "id": node_counter,
                "label": f"S{node_counter}: {state_label}",
                "state": sorted(list(new_state)),
                "step": step,
                "type": "valid" if is_valid else "invalid"
            })
            node_counter += 1
        
        to_state_id = state_id_map[state_key]
        
        # Create edge
        fsm_edges.append({
            "from": from_state_id,
            "to": to_state_id,
            "label": action_atom,
            "action": action_atom,
            "step": step,
            "valid": is_valid,
            "precondition": ", ".join(preconditions) if preconditions else "N/A"
        })
        
        current_state = new_state
    
    return jsonify({
        "nodes": fsm_nodes,
        "edges": fsm_edges
    })

def get_initial_world_state():
    """Get initial world state as a set of conditions."""
    world_query = list(prolog.query("world(Cond)."))
    state = set()
    for item in world_query:
        cond = item["Cond"]
        if isinstance(cond, bytes):
            state.add(cond.decode("utf-8"))
        else:
            state.add(str(cond))
    return state

def get_current_world_state():
    """Get current Prolog world state as a set."""
    return get_initial_world_state()  # Same function, but gets current state from Prolog

def state_to_label(state_set):
    """Convert state set to a readable label."""
    if not state_set:
        return "Initial"
    # Sort for consistent labeling
    sorted_states = sorted(state_set)
    return ", ".join(sorted_states)

def auto_expand_sequence(actions, manual_objects=None, robot_start_pos=(1.0, 1.0)):
    """Automatically add moveforward actions to reach objects.
    
    Args:
        actions: List of action strings
        manual_objects: List of (x, y) tuples for manually placed objects
        robot_start_pos: Starting position of robot (x, y)
    """
    expanded = []
    i = 0
    robot_x, robot_y = robot_start_pos
    
    while i < len(actions):
        expanded.append(actions[i])
        current = actions[i].strip().lower()
        
        # Update robot position based on actions
        if current == "moveforward":
            robot_y += 1.5  # Move forward increases Y by 1.5
        elif current == "moveleft":
            robot_x -= 1.5  # Move left decreases X by 1.5
        elif current == "moveright":
            robot_x += 1.5  # Move right increases X by 1.5
        
        # Check if next action is pickobject
        if i < len(actions) - 1:
            next_action = actions[i + 1].strip().lower()
            
            if next_action == "pickobject":
                # Check if we have manual objects to reach
                if manual_objects:
                    # Find nearest manual object
                    nearest_obj = None
                    min_dist = float('inf')
                    for obj_x, obj_y in manual_objects:
                        dist = ((obj_x - robot_x)**2 + (obj_y - robot_y)**2)**0.5
                        if dist < min_dist:
                            min_dist = dist
                            nearest_obj = (obj_x, obj_y)
                    
                    if nearest_obj:
                        obj_x, obj_y = nearest_obj
                        # Calculate movement needed in both X and Y directions
                        dist_x = obj_x - robot_x
                        dist_y = obj_y - robot_y
                        
                        # Move in X direction first (left/right)
                        if abs(dist_x) > 0.5:
                            if dist_x > 0:  # Need to move right
                                steps_x = max(1, int((dist_x - 1.0) / 1.5) + 1)
                                for _ in range(min(steps_x, 5)):  # Max 5 steps
                                    expanded.append("moveright")
                                    robot_x += 1.5
                                    if abs(obj_x - robot_x) <= 1.0:
                                        break
                            else:  # Need to move left
                                steps_x = max(1, int((abs(dist_x) - 1.0) / 1.5) + 1)
                                for _ in range(min(steps_x, 5)):  # Max 5 steps
                                    expanded.append("moveleft")
                                    robot_x -= 1.5
                                    if abs(obj_x - robot_x) <= 1.0:
                                        break
                        
                        # Then move in Y direction (forward)
                        if dist_y > 0.5:  # Need to move forward
                            steps_y = max(1, int((dist_y - 1.0) / 1.5) + 1)
                            for _ in range(min(steps_y, 5)):  # Max 5 steps
                                expanded.append("moveforward")
                                robot_y += 1.5
                                if abs(obj_y - robot_y) <= 1.0:
                                    break
                elif current == "scanarea":
                    # Original behavior: add movement after scanarea if no manual objects
                    expanded.append("moveforward")
                    expanded.append("moveforward")
        
        i += 1
    return expanded

@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json()
    
    # Handle both string format "[A, B, C]" and list format
    if isinstance(data.get("actions"), str):
        actions_raw = data["actions"]
        actions = [a.strip() for a in actions_raw.strip("[]").split(",")]
    elif isinstance(data.get("actions"), list):
        actions = [str(a).strip().lower() for a in data["actions"]]
    else:
        return jsonify({"error": "Actions must be a string or list"}), 400

    # Get manual objects from request (if provided)
    manual_objects = data.get("manual_objects", [])
    
    # Auto-expand sequence: add movement to reach objects
    auto_expand = data.get("auto_expand", True)  # Default to True
    if auto_expand:
        actions = auto_expand_sequence(actions, manual_objects=manual_objects)

    # Reset world state before verification
    reset_world_state()

    results = []
    all_valid = True
    
    # Battery tracking
    battery_level = 100
    battery_history = []
    
    # FSM tracking
    fsm_nodes = []
    fsm_edges = []
    current_state = get_current_world_state()  # Start with initial Prolog world state
    state_id_map = {}  # Map state sets to node IDs
    node_counter = 0
    
    # Create initial state node
    initial_label = state_to_label(current_state)
    state_id_map[frozenset(current_state)] = node_counter
    fsm_nodes.append({
        "id": node_counter,
        "label": f"S{node_counter}: {initial_label}",
        "state": sorted(list(current_state)),
        "step": 0,
        "type": "initial"
    })
    node_counter += 1

    for step, action in enumerate(actions, 1):
        action_atom = action.strip().lower()
        from_state_id = state_id_map.get(frozenset(current_state))
        
        # Store state BEFORE action (for from_state in results)
        from_state_before = get_current_world_state()  # Get from Prolog
        from_state_list = sorted(list(from_state_before))
        
        # Check if action exists
        action_check = list(prolog.query(f"action('{action_atom}')."))
        
        if not action_check:
            # Invalid action - state doesn't change
            results.append({
                "action": action_atom,
                "result": "invalid_action",
                "precondition": "N/A",
                "precondition_met": False,
                "explanation": f"'{action_atom}' is not a recognized action. Valid actions are: scanarea, moveforward, pickobject.",
                "from_state": from_state_list,
                "to_state": from_state_list  # State doesn't change
            })
            all_valid = False
            continue
        
        # Get all preconditions for this action
        precondition_query = list(prolog.query(f"precondition('{action_atom}', Cond)."))
        preconditions = []
        for item in precondition_query:
            cond = item["Cond"]
            if isinstance(cond, bytes):
                preconditions.append(cond.decode("utf-8"))
            else:
                preconditions.append(str(cond))
        
        # Validate using Prolog (which applies state changes dynamically)
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
        
        # Check which preconditions are met
        current_prolog_state = get_current_world_state()
        missing_preconditions = get_missing_preconditions(action_atom)
        all_preconditions_met = len(missing_preconditions) == 0
        
        # Build explanation
        if result == "valid":
            if preconditions:
                explanation = f"Action '{action_atom}' is valid. All preconditions satisfied: {', '.join(preconditions)}."
            else:
                explanation = f"Action '{action_atom}' is valid."
        elif result == "precondition_failed":
            if missing_preconditions:
                explanation = f"Action '{action_atom}' failed. Missing preconditions: {', '.join(missing_preconditions)}."
            else:
                explanation = f"Action '{action_atom}' failed: One or more preconditions are not satisfied."
        elif result == "invalid_action":
            explanation = f"'{action_atom}' is not a recognized action."
        else:
            explanation = f"Action '{action_atom}' resulted in error: {result}."
        
        # Get state after action (from Prolog)
        new_state = get_current_world_state()
        
        # Battery tracking
        if result == "valid":
            if action_atom in ["moveforward", "moveleft", "moveright", "turnleft", "turnright"]:
                battery_level = max(0, battery_level - 20)
            elif action_atom in ["scanarea", "pickobject", "releaseobject"]:
                battery_level = max(0, battery_level - 10)
            # poweron, poweroff, checkbattery, stop -> no drain
        
        battery_history.append(battery_level)
        
        # Update current_state for FSM tracking (from Prolog)
        current_state = new_state
        
        # Create or get state node
        state_key = frozenset(new_state)
        if state_key not in state_id_map:
            state_id_map[state_key] = node_counter
            state_label = state_to_label(new_state)
            fsm_nodes.append({
                "id": node_counter,
                "label": f"S{node_counter}: {state_label}",
                "state": sorted(list(new_state)),
                "step": step,
                "type": "valid" if result == "valid" else "invalid"
            })
            node_counter += 1
        
        to_state_id = state_id_map[state_key]
        
        # Create edge
        fsm_edges.append({
            "from": from_state_id,
            "to": to_state_id,
            "label": action_atom,
            "action": action_atom,
            "step": step,
            "valid": result == "valid",
            "precondition": ", ".join(preconditions) if preconditions else "N/A"
        })
        
        # Store state after transition for result
        to_state_list = sorted(list(new_state))
        
        results.append({
            "action": action_atom,
            "result": result,
            "precondition": ", ".join(preconditions) if preconditions else "N/A",
            "precondition_met": all_preconditions_met,
            "explanation": explanation,
            "from_state": from_state_list,
            "to_state": to_state_list,
            "battery": battery_level
        })

        if result != "valid":
            all_valid = False
            
    summary = "VALID SEQUENCE" if all_valid else "INVALID SEQUENCE"
    summary_details = f"All {len(actions)} actions are valid." if all_valid else f"Found {sum(1 for r in results if r['result'] != 'valid')} invalid action(s) in the sequence."
    final_state = get_final_world_state()

    return jsonify({
        "validation": results, 
        "summary": summary,
        "summary_details": summary_details,
        "final_state": final_state,
        "final_battery": battery_level,
        "battery_history": battery_history,
        "fsm": {
            "nodes": fsm_nodes,
            "edges": fsm_edges
        }
    })

if __name__ == "__main__":
    print("=" * 50)
    print("Formal Verification Server Starting...")
    print("=" * 50)
    print("Server running on: http://127.0.0.1:5000")
    print("API endpoint: http://127.0.0.1:5000/verify")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    try:
        app.run(host='127.0.0.1', port=5000, debug=False)
    except Exception as e:
        print(f"Error starting server: {e}")
