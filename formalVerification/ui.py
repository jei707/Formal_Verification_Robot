import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests

API_URL = "http://127.0.0.1:5000/verify"

AVAILABLE_ACTIONS = [
    "poweron",
    "poweroff",
    "scanarea",
    "checkbattery",
    "moveforward",
    "turnleft",
    "turnright",
    "pickobject",
    "releaseobject",
    "stop"
]

drag_start_index = None  # for drag and drop reordering


def add_action():
    action = action_picker.get()
    if action:
        sequence_list.insert(tk.END, action)


def add_typed_action():
    action = manual_input.get().strip().lower()
    if action:
        sequence_list.insert(tk.END, action)
        manual_input.delete(0, tk.END)


def clear_sequence():
    sequence_list.delete(0, tk.END)


def undo_last():
    size = sequence_list.size()
    if size > 0:
        sequence_list.delete(size - 1)


def save_sequence():
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


def on_drag_start(event):
    global drag_start_index
    drag_start_index = sequence_list.nearest(event.y)


def on_drag_motion(event):
    global drag_start_index
    if drag_start_index is None:
        return
    new_index = sequence_list.nearest(event.y)
    if new_index != drag_start_index:
        text = sequence_list.get(drag_start_index)
        sequence_list.delete(drag_start_index)
        sequence_list.insert(new_index, text)
        drag_start_index = new_index


def send_sequence():
    actions = list(sequence_list.get(0, tk.END))

    if not actions:
        messagebox.showwarning("Warning", "Please add at least one action.")
        return

    try:
        response = requests.post(API_URL, json={"actions": actions})

        if response.status_code != 200:
            messagebox.showerror("Error", f"Server returned error:\n{response.text}")
            return

        data = response.json()

        # Clear previous table rows
        for row in table.get_children():
            table.delete(row)

        # Insert results with color
        for i, item in enumerate(data.get("validation", [])):
            result = item.get("result", "")
            reason = item.get("reason", "")
            battery = item.get("battery", "")
            action_name = item.get("action", "")

            color = "green" if result == "valid" else "red"
            table.insert(
                "",
                "end",
                values=(i + 1, action_name, result, reason, battery),
                tags=(color,)
            )

        table.tag_configure("green", foreground="green")
        table.tag_configure("red", foreground="red")

        # Update summary
        summary_label.config(text=data.get("summary", "No summary returned."))

        # Update final world state
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

    except requests.exceptions.ConnectionError:
        messagebox.showerror(
            "Connection Error",
            "Cannot connect to backend. Is the server running?"
        )
    except Exception as e:
        messagebox.showerror("Error", f"Unexpected error:\n{e}")


# ------------- GUI layout -------------
root = tk.Tk()
root.title("Formal Verification Engine")
root.geometry("900x700")

title = tk.Label(root, text="Formal Verification Engine", font=("Arial", 18))
title.pack(pady=10)

# Action selection frame
picker_frame = tk.LabelFrame(root, text="Select or Type Action", padx=10, pady=10)
picker_frame.pack(pady=10, fill="x")

# Dropdown
action_picker = ttk.Combobox(picker_frame, values=AVAILABLE_ACTIONS, state="readonly")
action_picker.grid(row=0, column=0, padx=5, pady=3)

add_btn = tk.Button(picker_frame, text="Add Selected", command=add_action)
add_btn.grid(row=0, column=1, padx=5, pady=3)

# Manual input
manual_input = tk.Entry(picker_frame, width=25)
manual_input.grid(row=1, column=0, padx=5, pady=3)

add_manual_btn = tk.Button(picker_frame, text="Add Typed Action", command=add_typed_action)
add_manual_btn.grid(row=1, column=1, padx=5, pady=3)

# Sequence control buttons
seq_btn_frame = tk.Frame(picker_frame)
seq_btn_frame.grid(row=2, column=0, columnspan=2, pady=8)

clear_btn = tk.Button(seq_btn_frame, text="Clear", command=clear_sequence)
clear_btn.pack(side="left", padx=5)

undo_btn = tk.Button(seq_btn_frame, text="Undo Last", command=undo_last)
undo_btn.pack(side="left", padx=5)

save_btn = tk.Button(seq_btn_frame, text="Save", command=save_sequence)
save_btn.pack(side="left", padx=5)

load_btn = tk.Button(seq_btn_frame, text="Load", command=load_sequence)
load_btn.pack(side="left", padx=5)

# Sequence list display
sequence_list = tk.Listbox(root, width=50, height=6)
sequence_list.pack(pady=10)
sequence_list.bind("<Button-1>", on_drag_start)
sequence_list.bind("<B1-Motion>", on_drag_motion)

# Verify button
btn = tk.Button(root, text="Verify Sequence", command=send_sequence)
btn.pack(pady=10)

# Results table
columns = ("step", "action", "result", "reason", "battery")
frame = tk.Frame(root)
frame.pack(fill="both", expand=True, padx=20, pady=20)

scrollbar = tk.Scrollbar(frame)
scrollbar.pack(side="right", fill="y")

table = ttk.Treeview(
    frame,
    columns=columns,
    show="headings",
    yscrollcommand=scrollbar.set
)

table.heading("step", text="Step")
table.heading("action", text="Action")
table.heading("result", text="Result")
table.heading("reason", text="Reason")
table.heading("battery", text="Battery (%)")

table.column("step", width=50, anchor="center")
table.column("action", width=120)
table.column("result", width=100)
table.column("reason", width=350)
table.column("battery", width=100, anchor="center")

table.pack(fill="both", expand=True)
scrollbar.config(command=table.yview)

# Summary, final state, battery labels
summary_label = tk.Label(root, text="No verification yet.", font=("Arial", 14))
summary_label.pack(pady=5)

final_state_label = tk.Label(root, text="Final world state: (not evaluated yet)", font=("Arial", 12))
final_state_label.pack(pady=3)

battery_label = tk.Label(root, text="Battery: N/A", font=("Arial", 12))
battery_label.pack(pady=3)

root.mainloop()
