import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import requests
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch, FancyArrowPatch
from matplotlib.animation import FuncAnimation
import networkx as nx
import numpy as np
import threading
import time

API_URL = "http://127.0.0.1:5000/verify"

AVAILABLE_ACTIONS = [
    "poweron",
    "poweroff",
    "scanarea",
    "checkbattery",
    "moveforward",
    "moveleft",
    "moveright",
    "turnleft",
    "turnright",
    "pickobject",
    "releaseobject",
    "stop"
]

# Global animation state
animation_data = None
current_animation_step = 0
is_animating = False
animation_thread = None

# Global manually placed objects (x, y coordinates)
manual_objects = []

def draw_warehouse_base(ax, grid_width, grid_height):
    """Draw the base warehouse layout."""
    # Draw warehouse floor
    ax.set_xlim(0, grid_width)
    ax.set_ylim(0, grid_height)
    ax.set_aspect('equal')
    
    # Draw grid
    for x in range(grid_width + 1):
        ax.axvline(x, color='#e0e0e0', linewidth=0.5, alpha=0.5)
    for y in range(grid_height + 1):
        ax.axhline(y, color='#e0e0e0', linewidth=0.5, alpha=0.5)
    
    # Draw warehouse floor (light gray)
    floor = Rectangle((0, 0), grid_width, grid_height, 
                     facecolor='#f5f5f5', edgecolor='#bdbdbd', linewidth=2)
    ax.add_patch(floor)
    
    # Draw shelves/obstacles on sides
    for y in range(0, grid_height, 2):
        shelf_left = Rectangle((0, y), 0.3, 0.8, facecolor='#757575', edgecolor='#424242')
        shelf_right = Rectangle((grid_width-0.3, y), 0.3, 0.8, facecolor='#757575', edgecolor='#424242')
        ax.add_patch(shelf_left)
        ax.add_patch(shelf_right)

def visualize_warehouse_frame(validation_data, ax, canvas, frame_step=None):
    """Visualize robot movement in a warehouse floor plan - single frame."""
    if not validation_data:
        return
    
    ax.clear()
    
    # Warehouse grid dimensions
    grid_width = 10
    grid_height = 8
    
    # Draw base warehouse
    draw_warehouse_base(ax, grid_width, grid_height)
    
    # Initialize robot position (start at bottom-left)
    robot_x = 1.0
    robot_y = 1.0
    robot_path = [(robot_x, robot_y)]
    
    # Track objects and their positions
    objects = []
    scanned_areas = []
    picked_objects = []
    target_object = None  # Track the object we're moving toward
    
    # Add manually placed objects
    for obj_x, obj_y in manual_objects:
        # Check if this manual object hasn't been picked
        obj_picked = any(abs(px - obj_x) < 0.5 and abs(py - obj_y) < 0.5 for px, py in picked_objects)
        if not obj_picked:
            objects.append((obj_x, obj_y, "manual"))
    
    # Determine how many steps to show
    max_step = len(validation_data) if frame_step is None else min(frame_step + 1, len(validation_data))
    
    # Check if we need to target a manual object (if pickobject is coming and we have manual objects)
    # Manual objects take priority over detected objects
    if manual_objects and max_step > 0:
        # Look ahead to see if pickobject is in the sequence
        has_pickobject = any(item.get("action", "").lower() == "pickobject" for item in validation_data[:max_step])
        if has_pickobject:
            # Find the nearest manual object to the starting position
            nearest_obj = None
            min_dist = float('inf')
            for obj_x, obj_y in manual_objects:
                # Check if this object hasn't been picked
                obj_picked = any(abs(px - obj_x) < 0.5 and abs(py - obj_y) < 0.5 for px, py in picked_objects)
                if not obj_picked:
                    dist = ((obj_x - robot_x)**2 + (obj_y - robot_y)**2)**0.5
                    if dist < min_dist:
                        min_dist = dist
                        nearest_obj = (obj_x, obj_y)
            if nearest_obj:
                target_object = nearest_obj  # Set manual object as target (overrides any detected object)
    
    # Process each action to build the path up to current frame
    for i in range(max_step):
        item = validation_data[i]
        action = item.get("action", "")
        result = item.get("result", "")
        is_valid = result == "valid"
        
        # Get state information
        to_state = item.get("to_state", [])
        to_state_str = str(to_state).lower()
        
        # If we don't have a target yet and pickobject is coming, check for manual objects
        if not target_object and i < max_step - 1:
            next_item = validation_data[min(i + 1, max_step - 1)]
            next_action = next_item.get("action", "")
            if next_action == "pickobject":
                # Find nearest manual object that hasn't been picked
                nearest_obj = None
                min_dist = float('inf')
                for obj_x, obj_y in manual_objects:
                    # Check if this object hasn't been picked
                    obj_picked = any(abs(px - obj_x) < 0.5 and abs(py - obj_y) < 0.5 for px, py in picked_objects)
                    if not obj_picked:
                        dist = ((obj_x - robot_x)**2 + (obj_y - robot_y)**2)**0.5
                        if dist < min_dist:
                            min_dist = dist
                            nearest_obj = (obj_x, obj_y)
                if nearest_obj:
                    target_object = nearest_obj
        
        if action == "scanarea" and is_valid:
            # Scanning - mark the area
            scanned_areas.append((robot_x, robot_y))
            # After scanning, if object_detected is in state, place an object ahead
            # BUT only if we don't already have manual objects (manual objects take priority)
            from_state = item.get("from_state", [])
            from_state_str = str(from_state).lower()
            if "object_detected" in to_state_str or "object_detected" in from_state_str:
                # Only create detected object if we don't have manual objects
                # Manual objects should be used as targets instead
                if not manual_objects:
                    # Place object 2-3 cells ahead in the path (upward)
                    obj_x = robot_x  # Same X position
                    obj_y = min(robot_y + 2.5, grid_height - 1.5)  # Ahead (upward)
                    # Check if object already exists at this position
                    obj_exists = any(abs(o[0] - obj_x) < 0.5 and abs(o[1] - obj_y) < 0.5 for o in objects)
                    if not obj_exists:
                        objects.append((obj_x, obj_y, "detected"))
                        # Set this as the target object to move toward (only if no manual objects)
                        if not target_object:
                            target_object = (obj_x, obj_y)
                        
                        # Check if next action is pickobject - if so, auto-move to object immediately
                        if i < max_step - 1:
                            next_item = validation_data[min(i + 1, max_step - 1)]
                            next_action = next_item.get("action", "")
                            if next_action == "pickobject" and target_object == (obj_x, obj_y):
                                # Calculate steps needed to reach object
                                dist_y = target_object[1] - robot_y
                                if dist_y > 0:
                                    steps_needed = max(1, int((dist_y - 0.5) / 1.5))
                                    # Automatically move robot toward object (show intermediate steps)
                                    for step in range(min(steps_needed, 5)):  # Max 5 auto-moves
                                        if robot_y < target_object[1] - 0.5:
                                            robot_y = min(robot_y + 1.5, target_object[1] - 0.3, grid_height - 1.5)
                                            robot_path.append((robot_x, robot_y))
                                            # Check if we've reached it
                                            new_dist = ((target_object[0] - robot_x)**2 + (target_object[1] - robot_y)**2)**0.5
                                            if new_dist < 1.0:
                                                target_object = None
                                                break
        
        elif action == "moveforward" and is_valid:
            # Move forward (upward in our grid)
            robot_y = min(robot_y + 1.5, grid_height - 1.5)
            robot_path.append((robot_x, robot_y))
            # Check if we've reached the target object
            if target_object:
                dist_to_target = ((target_object[0] - robot_x)**2 + (target_object[1] - robot_y)**2)**0.5
                if dist_to_target < 1.0:
                    target_object = None  # Reached the object
        
        elif action == "moveleft" and is_valid:
            # Move left (decrease X)
            robot_x = max(robot_x - 1.5, 0.5)
            robot_path.append((robot_x, robot_y))
            # Check if we've reached the target object
            if target_object:
                dist_to_target = ((target_object[0] - robot_x)**2 + (target_object[1] - robot_y)**2)**0.5
                if dist_to_target < 1.0:
                    target_object = None  # Reached the object
        
        elif action == "moveright" and is_valid:
            # Move right (increase X)
            robot_x = min(robot_x + 1.5, grid_width - 0.5)
            robot_path.append((robot_x, robot_y))
            # Check if we've reached the target object
            if target_object:
                dist_to_target = ((target_object[0] - robot_x)**2 + (target_object[1] - robot_y)**2)**0.5
                if dist_to_target < 1.0:
                    target_object = None  # Reached the object
        
        # Auto-move toward target object (detected or manual) if next action is pickobject
        # This happens after processing the current action, regardless of what it was
        if target_object and i < max_step - 1:
            next_item = validation_data[min(i + 1, max_step - 1)]
            next_action = next_item.get("action", "")
            if next_action == "pickobject":
                dist_x = target_object[0] - robot_x
                dist_y = target_object[1] - robot_y
                dist = (dist_x**2 + dist_y**2)**0.5
                
                # If we're not close enough, automatically move toward it
                # Move multiple steps if needed (similar to detected objects after scanning)
                if dist > 1.0 and dist_y > 0:  # Object is ahead
                    # Calculate how many steps we need
                    steps_needed = max(1, int((dist_y - 0.5) / 1.5))
                    # Automatically move robot toward object (show intermediate steps)
                    for step in range(min(steps_needed, 5)):  # Max 5 auto-moves
                        if robot_y < target_object[1] - 0.5:
                            robot_y = min(robot_y + 1.5, target_object[1] - 0.3, grid_height - 1.5)
                            robot_path.append((robot_x, robot_y))
                            # Check if we've reached it
                            new_dist = ((target_object[0] - robot_x)**2 + (target_object[1] - robot_y)**2)**0.5
                            if new_dist < 1.0:
                                target_object = None  # Reached the object
                                break
        
        elif action == "pickobject" and is_valid:
            # Picking object - only pick if object_detected was removed from state
            # This means the object was actually successfully picked
            from_state = item.get("from_state", [])
            from_state_str = str(from_state).lower()
            to_state_str = str(to_state).lower()
            
            # Check if object_detected was in from_state but not in to_state (was removed)
            had_object = "object_detected" in from_state_str
            object_removed = "object_detected" not in to_state_str and had_object
            
            if object_removed:
                # Find nearest object to robot and mark as picked
                nearest_obj = None
                min_dist = float('inf')
                for idx, obj in enumerate(objects):
                    dist = ((obj[0] - robot_x)**2 + (obj[1] - robot_y)**2)**0.5
                    if dist < min_dist and dist < 1.5:
                        min_dist = dist
                        nearest_obj = (idx, obj)
                
                if nearest_obj:
                    idx, obj = nearest_obj
                    picked_objects.append((obj[0], obj[1]))
                    objects.pop(idx)
    
    # Draw scanned areas (yellow highlight)
    for sx, sy in scanned_areas:
        scan_area = Circle((sx, sy), 0.4, facecolor='yellow', 
                          edgecolor='orange', linewidth=2, alpha=0.4)
        ax.add_patch(scan_area)
        ax.text(sx, sy, 'SCAN', ha='center', va='center', 
               fontsize=7, fontweight='bold', color='darkorange')
    
    # Draw objects (boxes)
    for obj_x, obj_y, status in objects:
        if status == "detected" or status == "manual":
            # Manual objects are orange, detected objects are green
            if status == "manual":
                obj_box = Rectangle((obj_x - 0.3, obj_y - 0.3), 0.6, 0.6,
                                  facecolor='#FF9800', edgecolor='#F57C00', linewidth=2)
            else:
                obj_box = Rectangle((obj_x - 0.3, obj_y - 0.3), 0.6, 0.6,
                                  facecolor='#4CAF50', edgecolor='#2d8659', linewidth=2)
            ax.add_patch(obj_box)
            ax.text(obj_x, obj_y, '📦', ha='center', va='center', fontsize=12)
    
    # Draw picked objects (marked as collected)
    for px, py in picked_objects:
        picked_mark = Circle((px, py), 0.2, facecolor='#2196F3', 
                           edgecolor='#1976D2', linewidth=2, alpha=0.6)
        ax.add_patch(picked_mark)
        ax.text(px, py, '✓', ha='center', va='center', 
               fontsize=10, fontweight='bold', color='white')
    
    # Draw robot path
    if len(robot_path) > 1:
        path_x = [p[0] for p in robot_path]
        path_y = [p[1] for p in robot_path]
        ax.plot(path_x, path_y, 'b--', linewidth=2, alpha=0.5, label='Robot Path')
    
    # Draw robot at current position
    robot = Circle((robot_x, robot_y), 0.35, facecolor='#f44336', 
                  edgecolor='#c62828', linewidth=3)
    ax.add_patch(robot)
    ax.text(robot_x, robot_y, '🤖', ha='center', va='center', fontsize=14)
    
    # Draw start position marker
    start_x, start_y = robot_path[0]
    start_mark = Circle((start_x, start_y), 0.15, facecolor='#4CAF50', 
                       edgecolor='#2d8659', linewidth=2)
    ax.add_patch(start_mark)
    ax.text(start_x, start_y - 0.6, 'START', ha='center', va='top', 
           fontsize=8, fontweight='bold', color='#2d8659')
    
    # Add action labels along the path with step numbers
    step_num = 1
    for i in range(max_step):
        item = validation_data[i]
        action = item.get("action", "")
        result = item.get("result", "")
        if result == "valid":
            # Calculate position for this step
            temp_x, temp_y = 1.0, 1.0
            for j in range(i + 1):
                if j < len(validation_data):
                    temp_item = validation_data[j]
                    temp_action = temp_item.get("action", "")
                    temp_result = temp_item.get("result", "")
                    if temp_action == "moveforward" and temp_result == "valid":
                        temp_y = min(temp_y + 1.5, grid_height - 1.5)
            
            x, y = temp_x, temp_y
            
            # Place label offset from path to avoid overlap
            offset_x = 0.4 if step_num % 2 == 0 else -0.4
            label_x = x + offset_x
            label_y = y + 0.4
            
            # Draw step number circle
            step_circle = Circle((x, y), 0.25, facecolor='white', 
                               edgecolor='#2196F3', linewidth=2)
            ax.add_patch(step_circle)
            ax.text(x, y, str(step_num), ha='center', va='center', 
                   fontsize=8, fontweight='bold', color='#2196F3')
            
            # Draw action label
            ax.text(label_x, label_y, action, 
                   fontsize=7, bbox=dict(boxstyle='round,pad=0.3',
                                       facecolor='lightblue', alpha=0.9,
                                       edgecolor='#2196F3'),
                   ha='center', va='bottom', fontweight='bold')
            step_num += 1
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#f44336', edgecolor='#c62828', label='Robot'),
        Patch(facecolor='#4CAF50', edgecolor='#2d8659', label='Detected Object'),
        Patch(facecolor='#FF9800', edgecolor='#F57C00', label='Manual Object'),
        Patch(facecolor='yellow', edgecolor='orange', alpha=0.4, label='Scanned Area'),
        Patch(facecolor='#2196F3', edgecolor='#1976D2', alpha=0.6, label='Picked Object'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=8)
    
    title_text = "Warehouse Robot Movement Visualization"
    if frame_step is not None:
        title_text += f" - Step {frame_step + 1}/{len(validation_data)}"
    ax.set_title(title_text, fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Warehouse Floor Plan", fontsize=10)
    ax.grid(True, alpha=0.3)
    canvas.draw()

def visualize_warehouse(validation_data, fsm_data, ax, canvas):
    """Visualize robot movement in a warehouse floor plan - full view."""
    visualize_warehouse_frame(validation_data, ax, canvas, frame_step=None)
    
    # Warehouse grid dimensions
    grid_width = 10
    grid_height = 8
    cell_size = 1.0
    
    # Initialize robot position (start at bottom-left)
    robot_x = 1.0
    robot_y = 1.0
    robot_path = [(robot_x, robot_y)]
    
    # Track objects and their positions
    objects = []
    scanned_areas = []
    picked_objects = []
    
    # Process each action to build the path
    for i, item in enumerate(validation_data):
        action = item.get("action", "")
        result = item.get("result", "")
        is_valid = result == "valid"
        
        # Get state information
        to_state = item.get("to_state", [])
        to_state_str = str(to_state).lower()
        
        if action == "scanarea" and is_valid:
            # Scanning - mark the area
            scanned_areas.append((robot_x, robot_y))
            # After scanning, check if object_detected was added to state
            if "object_detected" in to_state_str:
                # Place object 2-3 cells ahead in the path
                obj_x = min(robot_x + 2.5, grid_width - 1.5)
                obj_y = robot_y
                # Check if object already exists at this position
                obj_exists = any(abs(o[0] - obj_x) < 0.5 and abs(o[1] - obj_y) < 0.5 for o in objects)
                if not obj_exists:
                    objects.append((obj_x, obj_y, "detected"))
        
        elif action == "moveforward" and is_valid:
            # Move forward (upward in our grid)
            robot_y = min(robot_y + 1.5, grid_height - 1.5)
            robot_path.append((robot_x, robot_y))
            # Check if we're near an object after moving
            for obj in objects:
                if abs(obj[0] - robot_x) < 1.0 and abs(obj[1] - robot_y) < 1.0:
                    # Robot is now at object location
                    break
        
        elif action == "pickobject" and is_valid:
            # Picking object - only pick if object_detected was removed from state
            # This means the object was actually successfully picked
            from_state = item.get("from_state", [])
            from_state_str = str(from_state).lower()
            to_state_str = str(to_state).lower()
            
            # Check if object_detected was in from_state but not in to_state (was removed)
            had_object = "object_detected" in from_state_str
            object_removed = "object_detected" not in to_state_str and had_object
            
            if object_removed:
                # Find nearest object to robot and mark as picked
                nearest_obj = None
                min_dist = float('inf')
                for idx, obj in enumerate(objects):
                    dist = ((obj[0] - robot_x)**2 + (obj[1] - robot_y)**2)**0.5
                    if dist < min_dist and dist < 1.5:
                        min_dist = dist
                        nearest_obj = (idx, obj)
                
                if nearest_obj:
                    idx, obj = nearest_obj
                    picked_objects.append((obj[0], obj[1]))
                    objects.pop(idx)
    
    # Draw warehouse floor
    ax.set_xlim(0, grid_width)
    ax.set_ylim(0, grid_height)
    ax.set_aspect('equal')
    
    # Draw grid
    for x in range(grid_width + 1):
        ax.axvline(x, color='#e0e0e0', linewidth=0.5, alpha=0.5)
    for y in range(grid_height + 1):
        ax.axhline(y, color='#e0e0e0', linewidth=0.5, alpha=0.5)
    
    # Draw warehouse floor (light gray)
    floor = Rectangle((0, 0), grid_width, grid_height, 
                     facecolor='#f5f5f5', edgecolor='#bdbdbd', linewidth=2)
    ax.add_patch(floor)
    
    # Draw shelves/obstacles on sides
    for y in range(0, grid_height, 2):
        shelf_left = Rectangle((0, y), 0.3, 0.8, facecolor='#757575', edgecolor='#424242')
        shelf_right = Rectangle((grid_width-0.3, y), 0.3, 0.8, facecolor='#757575', edgecolor='#424242')
        ax.add_patch(shelf_left)
        ax.add_patch(shelf_right)
    
    # Draw scanned areas (yellow highlight)
    for sx, sy in scanned_areas:
        scan_area = Circle((sx, sy), 0.4, facecolor='yellow', 
                          edgecolor='orange', linewidth=2, alpha=0.4)
        ax.add_patch(scan_area)
        ax.text(sx, sy, 'SCAN', ha='center', va='center', 
               fontsize=7, fontweight='bold', color='darkorange')
    
    # Draw objects (boxes)
    for obj_x, obj_y, status in objects:
        if status == "detected" or status == "manual":
            # Manual objects are orange, detected objects are green
            if status == "manual":
                obj_box = Rectangle((obj_x - 0.3, obj_y - 0.3), 0.6, 0.6,
                                  facecolor='#FF9800', edgecolor='#F57C00', linewidth=2)
            else:
                obj_box = Rectangle((obj_x - 0.3, obj_y - 0.3), 0.6, 0.6,
                                  facecolor='#4CAF50', edgecolor='#2d8659', linewidth=2)
            ax.add_patch(obj_box)
            ax.text(obj_x, obj_y, '📦', ha='center', va='center', fontsize=12)
    
    # Draw picked objects (marked as collected)
    for px, py in picked_objects:
        picked_mark = Circle((px, py), 0.2, facecolor='#2196F3', 
                           edgecolor='#1976D2', linewidth=2, alpha=0.6)
        ax.add_patch(picked_mark)
        ax.text(px, py, '✓', ha='center', va='center', 
               fontsize=10, fontweight='bold', color='white')
    
    # Draw robot path
    if len(robot_path) > 1:
        path_x = [p[0] for p in robot_path]
        path_y = [p[1] for p in robot_path]
        ax.plot(path_x, path_y, 'b--', linewidth=2, alpha=0.5, label='Robot Path')
    
    # Draw robot at current position
    robot = Circle((robot_x, robot_y), 0.35, facecolor='#f44336', 
                  edgecolor='#c62828', linewidth=3)
    ax.add_patch(robot)
    ax.text(robot_x, robot_y, '🤖', ha='center', va='center', fontsize=14)
    
    # Draw start position marker
    start_x, start_y = robot_path[0]
    start_mark = Circle((start_x, start_y), 0.15, facecolor='#4CAF50', 
                       edgecolor='#2d8659', linewidth=2)
    ax.add_patch(start_mark)
    ax.text(start_x, start_y - 0.6, 'START', ha='center', va='top', 
           fontsize=8, fontweight='bold', color='#2d8659')
    
    # Add action labels along the path with step numbers
    step_num = 1
    action_positions = []
    for i, item in enumerate(validation_data):
        action = item.get("action", "")
        result = item.get("result", "")
        if result == "valid":
            # Get position for this action
            if i < len(robot_path):
                x, y = robot_path[min(i, len(robot_path)-1)]
            else:
                x, y = robot_path[-1] if robot_path else (robot_x, robot_y)
            
            # Place label offset from path to avoid overlap
            offset_x = 0.4 if step_num % 2 == 0 else -0.4
            label_x = x + offset_x
            label_y = y + 0.4
            
            # Draw step number circle
            step_circle = Circle((x, y), 0.25, facecolor='white', 
                               edgecolor='#2196F3', linewidth=2)
            ax.add_patch(step_circle)
            ax.text(x, y, str(step_num), ha='center', va='center', 
                   fontsize=8, fontweight='bold', color='#2196F3')
            
            # Draw action label
            ax.text(label_x, label_y, action, 
                   fontsize=7, bbox=dict(boxstyle='round,pad=0.3',
                                       facecolor='lightblue', alpha=0.9,
                                       edgecolor='#2196F3'),
                   ha='center', va='bottom', fontweight='bold')
            step_num += 1
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#f44336', edgecolor='#c62828', label='Robot'),
        Patch(facecolor='#4CAF50', edgecolor='#2d8659', label='Detected Object'),
        Patch(facecolor='#FF9800', edgecolor='#F57C00', label='Manual Object'),
        Patch(facecolor='yellow', edgecolor='orange', alpha=0.4, label='Scanned Area'),
        Patch(facecolor='#2196F3', edgecolor='#1976D2', alpha=0.6, label='Picked Object'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=8)
    
    ax.set_title("Warehouse Robot Movement Visualization", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Warehouse Floor Plan", fontsize=10)
    ax.grid(True, alpha=0.3)
    canvas.draw()

def animate_step():
    """Animate one step forward."""
    global current_animation_step, animation_data
    if animation_data and current_animation_step < len(animation_data) - 1:
        current_animation_step += 1
        visualize_warehouse_frame(animation_data, fsm_ax, fsm_canvas, current_animation_step)

def animate_back():
    """Animate one step backward."""
    global current_animation_step, animation_data
    if animation_data and current_animation_step > 0:
        current_animation_step -= 1
        visualize_warehouse_frame(animation_data, fsm_ax, fsm_canvas, current_animation_step)

def reset_animation():
    """Reset animation to start."""
    global current_animation_step, is_animating
    current_animation_step = 0
    is_animating = False
    if animation_data:
        visualize_warehouse_frame(animation_data, fsm_ax, fsm_canvas, 0)
    if 'play_btn' in globals():
        play_btn.config(text="▶ Play")

def toggle_animation():
    """Toggle animation play/pause."""
    global is_animating, animation_thread, animation_data, current_animation_step
    
    if not animation_data:
        return
    
    if is_animating:
        # Pause
        is_animating = False
        play_btn.config(text="▶ Play")
    else:
        # Play
        is_animating = True
        play_btn.config(text="⏸ Pause")
        
        def animation_loop():
            global current_animation_step, is_animating
            while is_animating and current_animation_step < len(animation_data) - 1:
                current_animation_step += 1
                step = current_animation_step
                root.after(0, lambda s=step: visualize_warehouse_frame(animation_data, fsm_ax, fsm_canvas, s))
                time.sleep(1.0)  # 1 second per step
            is_animating = False
            root.after(0, lambda: play_btn.config(text="▶ Play"))
        
        animation_thread = threading.Thread(target=animation_loop, daemon=True)
        animation_thread.start()

def visualize_fsm(fsm_data, ax, canvas):
    """Visualize FSM using matplotlib and networkx (fallback option)."""
    if not fsm_data or "nodes" not in fsm_data or "edges" not in fsm_data:
        return
    
    # Clear previous plot
    ax.clear()
    
    # Create directed graph
    G = nx.DiGraph()
    
    # Add nodes
    node_colors = []
    node_labels = {}
    
    for node in fsm_data["nodes"]:
        node_id = node["id"]
        label = node["label"]
        node_type = node.get("type", "valid")
        
        G.add_node(node_id)
        node_labels[node_id] = label
        
        # Color based on type
        if node_type == "initial":
            node_colors.append("#4CAF50")  # Green
        elif node_type == "valid":
            node_colors.append("#2196F3")  # Blue
        else:
            node_colors.append("#f44336")  # Red
    
    # Add edges
    edge_colors = []
    edge_labels = {}
    
    for edge in fsm_data["edges"]:
        from_node = edge["from"]
        to_node = edge["to"]
        action = edge["label"]
        is_valid = edge.get("valid", True)
        
        G.add_edge(from_node, to_node)
        edge_labels[(from_node, to_node)] = action
        
        # Color based on validity
        if is_valid:
            edge_colors.append("#2d8659")  # Green
        else:
            edge_colors.append("#dc2626")  # Red
    
    # Use hierarchical layout for better visualization
    try:
        pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
    except:
        pos = nx.circular_layout(G)
    
    # Draw nodes
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors, 
                           node_size=2000, alpha=0.9, node_shape='o')
    
    # Draw edges
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color=edge_colors, 
                          arrows=True, arrowsize=20, width=2, alpha=0.6,
                          arrowstyle='->', connectionstyle='arc3,rad=0.1')
    
    # Draw labels
    nx.draw_networkx_labels(G, pos, ax=ax, labels=node_labels, 
                           font_size=8, font_weight='bold')
    
    # Draw edge labels
    nx.draw_networkx_edge_labels(G, pos, ax=ax, edge_labels=edge_labels,
                                 font_size=7, bbox=dict(boxstyle='round,pad=0.3',
                                                       facecolor='white', alpha=0.7))
    
    ax.set_title("Finite State Machine Visualization", fontsize=12, fontweight='bold', pad=10)
    ax.axis('off')
    canvas.draw()

def add_action():
    """Add selected action from dropdown to sequence."""
    action = action_picker.get()
    if action:
        sequence_list.insert(tk.END, action)

def add_typed_action():
    """Add manually typed action to sequence."""
    action = manual_input.get().strip().lower()
    if action:
        sequence_list.insert(tk.END, action)
        manual_input.delete(0, tk.END)

def clear_sequence():
    """Clear the action sequence."""
    sequence_list.delete(0, tk.END)

def undo_last():
    """Remove last action from sequence."""
    size = sequence_list.size()
    if size > 0:
        sequence_list.delete(size - 1)

def save_sequence():
    """Save action sequence to file."""
    actions = list(sequence_list.get(0, tk.END))
    if not actions:
        messagebox.showinfo("Info", "No actions to save.")
        return

    filename = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not filename:
        return

    try:
        with open(filename, "w", encoding="utf-8") as f:
            for act in actions:
                f.write(act + "\n")
        messagebox.showinfo("Saved", f"Sequence saved to:\n{filename}")
    except Exception as e:
        messagebox.showerror("Error", f"Could not save file:\n{e}")

def load_sequence():
    """Load action sequence from file."""
    filename = filedialog.askopenfilename(
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if not filename:
        return

    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        clear_sequence()
        for act in lines:
            sequence_list.insert(tk.END, act)
    except Exception as e:
        messagebox.showerror("Error", f"Could not load file:\n{e}")

def add_manual_object():
    """Add a manually placed object to the warehouse."""
    dialog = tk.Toplevel(root)
    dialog.title("Add Object")
    dialog.geometry("300x150")
    dialog.transient(root)
    dialog.grab_set()
    
    tk.Label(dialog, text="Object Position (X, Y):", font=("Arial", 10)).pack(pady=10)
    
    coord_frame = tk.Frame(dialog)
    coord_frame.pack(pady=5)
    
    tk.Label(coord_frame, text="X:").grid(row=0, column=0, padx=5)
    x_entry = tk.Entry(coord_frame, width=10)
    x_entry.grid(row=0, column=1, padx=5)
    x_entry.insert(0, "5.0")
    
    tk.Label(coord_frame, text="Y:").grid(row=0, column=2, padx=5)
    y_entry = tk.Entry(coord_frame, width=10)
    y_entry.grid(row=0, column=3, padx=5)
    y_entry.insert(0, "4.0")
    
    def confirm_add():
        try:
            x = float(x_entry.get())
            y = float(y_entry.get())
            # Validate coordinates
            if 0 <= x <= 10 and 0 <= y <= 8:
                manual_objects.append((x, y))
                update_obj_count()
                dialog.destroy()
                # Refresh visualization - show manual objects even without validation data
                if animation_data:
                    visualize_warehouse_frame(animation_data, fsm_ax, fsm_canvas, current_animation_step)
                else:
                    show_initial_warehouse()  # Show initial warehouse with manual objects
                
                messagebox.showinfo("Success", f"Object added at ({x}, {y})\nTotal objects: {len(manual_objects)}")
            else:
                messagebox.showerror("Error", "Coordinates must be:\nX: 0-10\nY: 0-8")
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for X and Y")
    
    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=10)
    
    tk.Button(btn_frame, text="Add", command=confirm_add, 
             bg="#4CAF50", fg="white", padx=15, pady=5).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Cancel", command=dialog.destroy,
             padx=15, pady=5).pack(side="left", padx=5)

def update_obj_count():
    """Update the object count label."""
    if 'obj_count_label' in globals():
        obj_count_label.config(text=f"Objects: {len(manual_objects)}")

def clear_manual_objects():
    """Clear all manually placed objects."""
    global manual_objects
    if manual_objects:
        if messagebox.askyesno("Confirm", f"Remove {len(manual_objects)} manually placed object(s)?"):
            manual_objects.clear()
            update_obj_count()
            # Refresh visualization
            if animation_data:
                visualize_warehouse_frame(animation_data, fsm_ax, fsm_canvas, current_animation_step)
            else:
                show_initial_warehouse()
            messagebox.showinfo("Success", "All manual objects removed")
    else:
        messagebox.showinfo("Info", "No manual objects to remove")

def send_sequence():
    # Get actions from listbox if it exists, otherwise from text input
    if 'sequence_list' in globals() and sequence_list.size() > 0:
        actions = list(sequence_list.get(0, tk.END))
    else:
        sequence = text_input.get("1.0", tk.END).strip()
        if not sequence:
            messagebox.showwarning("Warning", "Please enter an action sequence.")
            return
        # Try to parse as list format
        if sequence.startswith("[") and sequence.endswith("]"):
            actions = [a.strip() for a in sequence.strip("[]").split(",")]
        else:
            actions = [sequence]
    
    if not actions:
        messagebox.showwarning("Warning", "Please add at least one action.")
        return

    try:
        # Send manual objects to backend so it can calculate movement
        request_data = {
            "actions": actions,
            "manual_objects": manual_objects  # Send manual object positions
        }
        response = requests.post(API_URL, json=request_data)
        data = response.json()

        # Clear table first
        for row in table.get_children():
            table.delete(row)

        # Clear explanation area
        explanation_text.config(state=tk.NORMAL)
        explanation_text.delete("1.0", tk.END)
        explanation_text.config(state=tk.DISABLED)

        # Fill table with enhanced information
        for i, item in enumerate(data["validation"]):
            result = item["result"]
            status = "✓ Valid" if result == "valid" else "✗ Invalid"
            
            # Determine color based on result
            if result == "valid":
                color = "valid"
            elif result == "precondition_failed":
                color = "warning"
            else:
                color = "error"
            
            # Get precondition status
            precondition = item.get("precondition", "N/A")
            prec_status = "✓" if item.get("precondition_met", False) else "✗"
            
            table.insert("", "end", values=(
                i+1, 
                item["action"], 
                precondition,
                prec_status,
                status
            ), tags=(color,))

        # Configure tag colors
        table.tag_configure("valid", foreground="#2d8659", background="#e8f5e9")
        table.tag_configure("warning", foreground="#d97706", background="#fff7ed")
        table.tag_configure("error", foreground="#dc2626", background="#fee2e2")

        # Update explanation when row is selected
        def on_select(event):
            selection = table.selection()
            if selection:
                item = table.item(selection[0])
                index = int(item['values'][0]) - 1
                if 0 <= index < len(data["validation"]):
                    explanation = data["validation"][index].get("explanation", "No explanation available.")
                    explanation_text.config(state=tk.NORMAL)
                    explanation_text.delete("1.0", tk.END)
                    explanation_text.insert("1.0", f"Step {index + 1}: {explanation}")
                    explanation_text.config(state=tk.DISABLED)

        table.bind("<<TreeviewSelect>>", on_select)

        # Show first item's explanation by default
        if data["validation"]:
            explanation_text.config(state=tk.NORMAL)
            explanation_text.insert("1.0", f"Step 1: {data['validation'][0].get('explanation', 'No explanation available.')}")
            explanation_text.config(state=tk.DISABLED)
            # Select first row
            first_item = table.get_children()[0]
            table.selection_set(first_item)
            table.focus(first_item)

        # Update summary
        summary_text = data.get("summary", "")
        summary_details = data.get("summary_details", "")
        summary_label.config(
            text=f"{summary_text}\n{summary_details}",
            fg="#2d8659" if "VALID" in summary_text else "#dc2626"
        )
        
        # Update final state
        final_state = data.get("final_state", [])
        if final_state:
            final_state_label.config(
                text="Final world state: " + ", ".join(final_state)
            )
        else:
            final_state_label.config(text="Final world state: (none)")
        
        # Update battery
        final_batt = data.get("final_battery", None)
        if final_batt is not None:
            battery_label.config(text=f"Battery: {final_batt}%")
        else:
            battery_label.config(text="Battery: N/A")
        
        # Visualize warehouse movement if data is available
        if "fsm" in data and "validation" in data:
            global animation_data, current_animation_step, is_animating
            animation_data = data["validation"]
            current_animation_step = 0
            is_animating = False
            visualize_warehouse_frame(animation_data, fsm_ax, fsm_canvas, 0)
            update_obj_count()
            # Enable animation controls
            if 'play_btn' in globals():
                play_btn.config(state='normal')
                step_forward_btn.config(state='normal')
                step_back_btn.config(state='normal')
                reset_btn.config(state='normal')

    except requests.exceptions.ConnectionError:
        messagebox.showerror(
            "Connection Error",
            "Cannot connect to backend server.\n\n"
            "Please make sure:\n"
            "1. The backend server (app.py) is running\n"
            "2. It's running on http://127.0.0.1:5000\n"
            "3. No firewall is blocking the connection\n\n"
            "To start the backend, run:\n"
            "python app.py"
        )
    except Exception as e:
        messagebox.showerror("Error", f"Could not connect to backend:\n{e}")


root = tk.Tk()
root.title("Formal Verification Engine")
root.geometry("1400x900")

# Main container with padding
main_frame = tk.Frame(root, padx=20, pady=15)
main_frame.pack(fill="both", expand=True)

# Title
title = tk.Label(main_frame, text="Formal Verification Engine", font=("Arial", 20, "bold"))
title.pack(pady=(0, 15))

# Input section
input_frame = tk.LabelFrame(main_frame, text="Action Sequence Input", font=("Arial", 11, "bold"), padx=10, pady=10)
input_frame.pack(fill="x", pady=(0, 15))

# Action picker frame
picker_frame = tk.Frame(input_frame)
picker_frame.pack(fill="x", pady=(0, 5))

# Dropdown for action selection
action_picker = ttk.Combobox(picker_frame, values=AVAILABLE_ACTIONS, state="readonly", width=20)
action_picker.pack(side="left", padx=5)

add_btn = tk.Button(picker_frame, text="Add Selected", command=add_action, 
                   font=("Arial", 9), bg="#2196F3", fg="white", padx=10, pady=2)
add_btn.pack(side="left", padx=5)

# Manual input
manual_input = tk.Entry(picker_frame, width=25)
manual_input.pack(side="left", padx=5)

add_manual_btn = tk.Button(picker_frame, text="Add Typed", command=add_typed_action,
                           font=("Arial", 9), bg="#2196F3", fg="white", padx=10, pady=2)
add_manual_btn.pack(side="left", padx=5)

# Sequence control buttons
seq_btn_frame = tk.Frame(picker_frame)
seq_btn_frame.pack(side="left", padx=10)

clear_btn = tk.Button(seq_btn_frame, text="Clear", command=clear_sequence,
                      font=("Arial", 9), padx=8, pady=2)
clear_btn.pack(side="left", padx=2)

undo_btn = tk.Button(seq_btn_frame, text="Undo", command=undo_last,
                     font=("Arial", 9), padx=8, pady=2)
undo_btn.pack(side="left", padx=2)

save_btn = tk.Button(seq_btn_frame, text="Save", command=save_sequence,
                     font=("Arial", 9), padx=8, pady=2)
save_btn.pack(side="left", padx=2)

load_btn = tk.Button(seq_btn_frame, text="Load", command=load_sequence,
                     font=("Arial", 9), padx=8, pady=2)
load_btn.pack(side="left", padx=2)

# Sequence list display
sequence_list = tk.Listbox(input_frame, width=80, height=4, font=("Consolas", 10))
sequence_list.pack(fill="x", pady=(5, 5))

# Text input (for backward compatibility)
text_input = tk.Text(input_frame, height=2, width=80, font=("Consolas", 10))
text_input.pack(fill="x", pady=(5, 5))
text_input.insert("1.0", "[poweron, scanarea, moveforward, pickobject]")

btn = tk.Button(input_frame, text="Verify Sequence", command=send_sequence, 
                font=("Arial", 11, "bold"), bg="#4CAF50", fg="white", 
                padx=20, pady=5, cursor="hand2")
btn.pack(pady=5)

# Results section with two columns (top row)
results_frame = tk.Frame(main_frame)
results_frame.pack(fill="both", expand=True, pady=(0, 15))

# Left side: Table
table_frame = tk.LabelFrame(results_frame, text="Verification Results", font=("Arial", 11, "bold"), padx=10, pady=10)
table_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

# Table with scrollbar
columns = ("step", "action", "precondition", "prec_status", "status")
table = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)

# Configure column headings
table.heading("step", text="Step")
table.heading("action", text="Action")
table.heading("precondition", text="Precondition")
table.heading("prec_status", text="Prec. Met")
table.heading("status", text="Status")

# Configure column widths
table.column("step", width=60, anchor="center")
table.column("action", width=150, anchor="w")
table.column("precondition", width=150, anchor="w")
table.column("prec_status", width=80, anchor="center")
table.column("status", width=100, anchor="center")

# Scrollbar for table
table_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
table.configure(yscrollcommand=table_scrollbar.set)

table.pack(side="left", fill="both", expand=True)
table_scrollbar.pack(side="right", fill="y")

# Right side: Explanation
explanation_frame = tk.LabelFrame(results_frame, text="Explanation", font=("Arial", 11, "bold"), padx=10, pady=10)
explanation_frame.pack(side="right", fill="both", expand=True)

explanation_text = scrolledtext.ScrolledText(
    explanation_frame, 
    height=10, 
    width=40, 
    font=("Arial", 10),
    wrap=tk.WORD,
    state=tk.DISABLED,
    bg="#f9f9f9"
)
explanation_text.pack(fill="both", expand=True)

# Warehouse Visualization section (bottom row)
fsm_frame = tk.LabelFrame(main_frame, text="Warehouse Robot Movement Visualization", font=("Arial", 11, "bold"), padx=10, pady=10)
fsm_frame.pack(fill="both", expand=True, pady=(0, 15))

# Object placement controls frame
obj_controls_frame = tk.Frame(fsm_frame)
obj_controls_frame.pack(fill="x", pady=(0, 5))

tk.Label(obj_controls_frame, text="Manual Objects:", font=("Arial", 9)).pack(side="left", padx=5)

add_obj_btn = tk.Button(obj_controls_frame, text="➕ Add Object", command=add_manual_object,
                        font=("Arial", 9), bg="#FF9800", fg="white", padx=10, pady=2)
add_obj_btn.pack(side="left", padx=5)

clear_obj_btn = tk.Button(obj_controls_frame, text="🗑️ Clear Objects", command=clear_manual_objects,
                          font=("Arial", 9), bg="#f44336", fg="white", padx=10, pady=2)
clear_obj_btn.pack(side="left", padx=5)

obj_count_label = tk.Label(obj_controls_frame, text="Objects: 0", font=("Arial", 9))
obj_count_label.pack(side="left", padx=10)

# Animation controls frame
anim_controls_frame = tk.Frame(fsm_frame)
anim_controls_frame.pack(fill="x", pady=(0, 5))

# Animation control buttons
play_btn = tk.Button(anim_controls_frame, text="▶ Play", command=toggle_animation,
                    font=("Arial", 9), bg="#4CAF50", fg="white", 
                    padx=15, pady=3, state='disabled', cursor="hand2")
play_btn.pack(side="left", padx=5)

step_back_btn = tk.Button(anim_controls_frame, text="⏮ Step Back", command=animate_back,
                         font=("Arial", 9), bg="#2196F3", fg="white",
                         padx=15, pady=3, state='disabled', cursor="hand2")
step_back_btn.pack(side="left", padx=5)

step_forward_btn = tk.Button(anim_controls_frame, text="Step Forward ⏭", command=animate_step,
                            font=("Arial", 9), bg="#2196F3", fg="white",
                            padx=15, pady=3, state='disabled', cursor="hand2")
step_forward_btn.pack(side="left", padx=5)

reset_btn = tk.Button(anim_controls_frame, text="⏹ Reset", command=reset_animation,
                     font=("Arial", 9), bg="#f44336", fg="white",
                     padx=15, pady=3, state='disabled', cursor="hand2")
reset_btn.pack(side="left", padx=5)

def show_initial_warehouse():
    """Show initial warehouse state with manual objects."""
    fsm_ax.clear()
    
    # Warehouse grid dimensions
    grid_width = 10
    grid_height = 8
    
    # Draw base warehouse
    draw_warehouse_base(fsm_ax, grid_width, grid_height)
    
    # Draw robot at starting position
    robot_x, robot_y = 1.0, 1.0
    robot = Circle((robot_x, robot_y), 0.35, facecolor='#f44336', 
                  edgecolor='#c62828', linewidth=3)
    fsm_ax.add_patch(robot)
    fsm_ax.text(robot_x, robot_y, '🤖', ha='center', va='center', fontsize=14)
    
    # Draw start marker
    start_mark = Circle((robot_x, robot_y), 0.15, facecolor='#4CAF50', 
                       edgecolor='#2d8659', linewidth=2)
    fsm_ax.add_patch(start_mark)
    fsm_ax.text(robot_x, robot_y - 0.6, 'START', ha='center', va='top', 
               fontsize=8, fontweight='bold', color='#2d8659')
    
    # Draw manual objects if any
    for obj_x, obj_y in manual_objects:
        obj_box = Rectangle((obj_x - 0.3, obj_y - 0.3), 0.6, 0.6,
                          facecolor='#FF9800', edgecolor='#F57C00', linewidth=2)
        fsm_ax.add_patch(obj_box)
        fsm_ax.text(obj_x, obj_y, '📦', ha='center', va='center', fontsize=12)
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#f44336', edgecolor='#c62828', label='Robot (Start)'),
    ]
    if manual_objects:
        legend_elements.append(Patch(facecolor='#FF9800', edgecolor='#F57C00', label='Manual Object'))
    fsm_ax.legend(handles=legend_elements, loc='upper right', fontsize=8)
    
    title_text = "Warehouse - Initial State"
    if manual_objects:
        title_text += f" ({len(manual_objects)} object(s))"
    fsm_ax.set_title(title_text, fontsize=14, fontweight='bold', pad=15)
    fsm_ax.grid(True, alpha=0.3)
    fsm_canvas.draw()

# Create matplotlib figure
fig, fsm_ax = plt.subplots(figsize=(12, 6), facecolor='white')

# Embed matplotlib in tkinter
fsm_canvas = FigureCanvasTkAgg(fig, fsm_frame)
fsm_canvas.get_tk_widget().pack(fill="both", expand=True)

# Add navigation toolbar for zoom and pan
toolbar = NavigationToolbar2Tk(fsm_canvas, fsm_frame)
toolbar.update()
toolbar.pack(side="bottom", fill="x")

# Initialize object count and show initial warehouse
update_obj_count()
show_initial_warehouse()  # Show warehouse immediately on startup

# Summary and status labels
summary_label = tk.Label(main_frame, text="No verification yet.", font=("Arial", 12, "bold"), pady=5)
summary_label.pack()

final_state_label = tk.Label(main_frame, text="Final world state: (not evaluated yet)", 
                            font=("Arial", 11), pady=3)
final_state_label.pack()

battery_label = tk.Label(main_frame, text="Battery: N/A", font=("Arial", 11), pady=3)
battery_label.pack()

root.mainloop()
