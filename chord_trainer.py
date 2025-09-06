import os
import tkinter as tk
from tkinter import messagebox
import json, random, threading
import numpy as np
import sounddevice as sd
import math

class ToolTip:
    """
    Very simple tooltip for any widget.
    Shows a small Toplevel after a delay when the mouse
    hovers over the widget.
    """
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text   = text
        self.delay  = delay
        self._id    = None
        self.tw     = None
        widget.bind("<Enter>",   self._schedule)
        widget.bind("<Leave>",   self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, event=None):
        self._unschedule()
        # after 'delay' ms, call self._show
        self._id = self.widget.after(self.delay, self._show)

    def _unschedule(self):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None

    def _show(self):
        # create tooltip window
        if self.tw:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 1
        self.tw = tw = tk.Toplevel(self.widget)
        # no window decorations
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1)
        label.pack(ipadx=4, ipady=2)

    def _hide(self, event=None):
        self._unschedule()
        if self.tw:
            self.tw.destroy()
            self.tw = None



class ChordRecognitionApp:
    
    def __init__(self, root):
        self.root = root
        self.root.title("Chord Recognition")
        self.root.geometry("800x600")

        self.settings_path = "user_settings.json"
        with open(self.settings_path) as sf:
            self.settings = json.load(sf)
        self.update_variables()
                        
        with open("default_settings.json") as sf:
            self.default_settings = json.load(sf)
        
        # load chords database
        with open(f"chord_databases/{self.chord_database_name}.json", "r") as f:
            self.chords = json.load(f)
            
        # where presets live
        self.presets_dir = "chord_presets"
        
        # state
        self.current_chord_idx = None
        self.chord_buttons     = []
        
        self.random_preset()
        
        # controls
        ctrl = tk.Frame(root); ctrl.pack(pady=10)
        tk.Button(ctrl, text="Next",   command=self.next_chord).pack(side="left", padx=5)
        tk.Button(ctrl, text="Replay", command=self.replay_chord).pack(side="left", padx=5)
        tk.Button(ctrl, text="Preset", command=self.show_preset_popup).pack(side="left", padx=5)
        tk.Button(ctrl, text="Settings", command=self.show_settings_popup).pack(side="left", padx=5)

        self.feedback_label = tk.Label(root, text="", font=("Arial",12))
        self.feedback_label.pack(pady=(0,20))
        
        self.chord_frame = tk.LabelFrame(root, text="Choose the chord",
                                          padx=10, pady=10, relief=tk.GROOVE, borderwidth=2)
        self.chord_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.chord_frame_init()
        
        self.var_types = {
                          "chord_database_name" : str,
                          "n_harmonics"         : int,
                          "fs"                  : int,
                          "duration"            : float,
                          "rolloff_coeff"       : float,
                          "decay_time"          : float,
                          "decay_exponent"      : float,
                          "f0"                  : float,
                          "B0"                  : float,
                          "beta"                : float,
                          "jitter"              : float,
                          "random_w"            : int,
                          "random_h"            : int,
                          "random_pitch"        : bool,
                          "pitch"               : float,
                          "min_pitch"           : float,
                          "max_pitch"           : float,
                         }



    def update_variables(self):
        self.tk_stringvars = {}
        for key, val in self.settings.items():
            setattr(self, key, val)
            self.tk_stringvars[key] = tk.StringVar(value=str(val))

    def chord_frame_init(self):
        for _,btn in self.chord_buttons:
            btn.destroy()
            
        self.chord_buttons.clear()
        self.center_label = tk.Label(self.chord_frame,
                                     text='Press "Next" to start.',
                                     font=("Helvetica", 16))
                                     
        self.center_label.place(relx=0.5, rely=0.5, anchor="center")
    
    def load_preset_file(self, filename):
        """Load an XML preset from self.presets_dir/filename."""
        path = os.path.join(self.presets_dir, filename)
        with open(path, "r") as f:
            lines = f.read().splitlines()

        # parse text into grid of short‐names
        self.grid_names = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(";") if p.strip()]
            self.grid_names.append(parts)

        # convert short‐names to chord indices
        self.grid_indices = []
        for row in self.grid_names:
            idx_row = []
            for short in row:
                i = next((j for j,c in enumerate(self.chords)
                          if c["short"] == short), None)
                if i is None:
                    raise ValueError(f"Unknown chord '{short}' in {filename}")
                idx_row.append(i)
            self.grid_indices.append(idx_row)

        # flat list for random selection if needed
        self.flat_indices = [i for row in self.grid_indices for i in row]

    def show_preset_popup(self):
        """Popup window to pick a preset file or random 3×3."""
        self.preset_popup = tk.Toplevel(self.root)
        self.preset_popup.title("Select Preset")
        self.preset_popup.grab_set()  # make it modal

        # first option: random 3×3
        btn = tk.Button(self.preset_popup, text="random",
                        command=lambda: self.apply_preset("random"))
        btn.pack(fill="x", padx=10, pady=5)

        # then show all XML files in the presets dir
        for fn in sorted(os.listdir(self.presets_dir)):
            if not fn.lower().endswith(".xml"):
                continue
            name = os.path.splitext(fn)[0]  # strip .xml
            btn = tk.Button(self.preset_popup, text=name,
                            command=lambda f=fn: self.apply_preset(f))
            btn.pack(fill="x", padx=10, pady=2)


###################   S E T T I N G S   P O P U P   ########################


    def show_settings_popup(self):
        
        # storage for menu buttons & sections
        self.menu_buttons = {}
        
        self.sections = [
            "Database",
            "Audio",
            "Tone",
            "Pitch"
        ]
        
        # Make a toplevel window
        self.settings_popup = tk.Toplevel(self.root)
        self.settings_popup.title("Settings")
        self.settings_popup.grab_set()  # make it modal
        self.settings_popup.resizable(False, False)
        self.settings_popup.geometry("600x600")

        # Configure grid on the popup so column 1 expands
        self.settings_popup.grid_rowconfigure(0, weight=1)
        self.settings_popup.grid_columnconfigure(1, weight=1)

        # left panel
        left_panel = tk.Frame(self.settings_popup, bg="#eee", width=148)
        left_panel.grid    (row=0, column=0, sticky="ns")
        left_panel.grid_propagate(False)
        
        # right panel (we’ll fill dynamically)
        right_panel = tk.Frame(self.settings_popup, bg="#ddd")
        right_panel.grid    (row=0, column=1, sticky="nsew")
        self._right_panel = right_panel
        
        # make the menu buttons
        for i, section in enumerate(self.sections):
            btn = tk.Button(
                left_panel,
                text=section,
                anchor="w",
                relief="raised",
                width=19,
                bg="#eee",
                command=lambda sec=section: self._on_menu_select(sec)
            )
            btn.grid(row=i, column=0, sticky="ew", padx=3, pady=3)
            self.menu_buttons[section] = btn       
        
        # push any extra space down
        left_panel.grid_rowconfigure(len(self.sections), weight=1)
        
        # show the first section by default
        self.section = self.sections[0]
        self._on_menu_select(self.sections[0])     
        
        # Save button at the bottom
        btn_save = tk.Button(self.settings_popup, text="Save", command=self._save_settings)
        btn_save.grid(row=1, column=0, columnspan=3, pady=(10,5))



    def _on_menu_select(self, section):
        
        # set the current section
        self.section = section
        
        # highlight the active menu button
        for sec, btn in self.menu_buttons.items():
            if sec == section:
                btn.config(relief="sunken", bg="#ccc")
            else:
                btn.config(relief="raised", bg="#eee")

        # clear right panel
        for child in self._right_panel.winfo_children():
            child.destroy()

        # rebuild right panel for the current section
        if section == "Database": 
            
            key = "chord_database_name"
            row = 0
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv
            
        elif section == "Audio":

            key = "fs"
            row = 0
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv
        
        elif section == "Tone":

            key = "n_harmonics"
            row = 0
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv
            
            key = "duration"
            row = 1
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "rolloff_coeff"
            row = 2
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "decay_time"
            row = 3
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "decay_exponent"
            row = 4
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "f0"
            row = 5
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "B0"
            row = 6
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "beta"
            row = 7
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "jitter"
            row = 8
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "random_w"
            row = 9
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "random_h"
            row = 10
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv
        
        elif section == "Pitch":
            
            key = "random_pitch"
            row = 0
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv

            key = "pitch"
            row = 1
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv
            
            key = "min_pitch"
            row = 2
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv 
            
            key = "max_pitch"
            row = 3
            val = self.settings[key]
            lbl = tk.Label(self._right_panel, text=key)
            lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
            sv = tk.StringVar(value=str(val))
            ent = tk.Entry(self._right_panel, textvariable=sv, width=30)
            ent.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            btn = tk.Button(
                self._right_panel,
                text="X",
                fg="red",
                width=2,
                command=lambda k=key, var=sv: self._reset_to_default(k, var)
            )
            btn.grid(row=row, column=2, padx=5, pady=5)
            self.tk_stringvars[key] = sv            



    def _reset_to_default(self, key, var):
        """
        Called when the user clicks the “X” on row ‘key’.
        Looks up the default in self.default_settings and writes it into var.
        """
        default_val = self.default_settings.get(key)
        if default_val is None:
            # you could pop up a warning here if you like
            return
        # convert to string for the Entry
        var.set(str(default_val))

    def _save_settings(self):
        new_settings = {}

        key = "chord_database_name"
        txt = self.tk_stringvars[key].get().strip()
        val = txt
        new_settings[key] = val

        key = "n_harmonics"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = int(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to int, storing as string."
            )
        new_settings[key] = val

        key = "fs"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = int(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to int, storing as string."
            )
        new_settings[key] = val

        key = "duration"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        key = "rolloff_coeff"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        key = "decay_time"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        key = "decay_exponent"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        key = "f0"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = int(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to int, storing as string."
            )
        new_settings[key] = val

        key = "B0"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        key = "beta"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        key = "jitter"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        key = "random_w"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = int(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to int, storing as string."
            )
        new_settings[key] = val

        key = "random_h"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = int(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to int, storing as string."
            )
        new_settings[key] = val
        
        key = "random_pitch"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to int, storing as string."
            )
        new_settings[key] = val

        key = "pitch"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to int, storing as string."
            )
        new_settings[key] = val
        
        key = "min_pitch"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        key = "max_pitch"
        txt = self.tk_stringvars[key].get().strip()
        try:
            val = float(txt)
        except Exception:
            val = txt
            messagebox.showwarning(
                "Type error",
                f"Could not convert {key!r} to float, storing as string."
            )
        new_settings[key] = val

        # --- Write back to disk ---
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(new_settings, f, indent=2)
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to write settings:\n{e}")
            return

        # --- Update in‐memory ---
        self.settings = new_settings
        self.update_variables()

        # Reload chord database
        with open(f"chord_databases/{self.chord_database_name}.json", "r") as f:
            self.chords = json.load(f)

        # Close popup and re‐init UI
        self.settings_popup.destroy()
        self.chord_frame_init()
        self.random_preset()


    def random_preset(self):
        
        # build a random 3×3 from ALL chords
        w = self.random_w
        h = self.random_h
        all_idxs = list(range(len(self.chords)))
        sel = random.sample(all_idxs, w*h)
        self.grid_indices = [sel[i*w:(i+1)*w] for i in range(h)]
        # for completeness, also build grid_names
        self.grid_names = [
            [self.chords[idx]["repr"] for idx in row]
            for row in self.grid_indices
        ]
        # flat for skipping logic
        self.flat_indices = [i for row in self.grid_indices for i in row]
    
    def apply_preset(self, choice):
        """Called when user clicks in the preset popup."""
        # remove popup
        if hasattr(self, "preset_popup"):
            self.preset_popup.destroy()

        if choice == "random":
            self.random_preset()
        else:
            # load that XML file
            self.load_preset_file(choice)

        # restart with the newly‐loaded preset
        self.chord_frame_init()

    def next_chord(self):
        # clear
        self.center_label.config(text="")
        for _,btn in self.chord_buttons:
            btn.destroy()
        self.chord_buttons.clear()

        # pick a new chord to play
        self.current_chord_idx = random.choice(self.flat_indices)
        if self.pitch:
            self.base_freq = random.uniform(self.min_pitch, self.max_pitch)
        else:
            self.base_freq = self.pitch
        
        # rebuild grid buttons
        for r,row in enumerate(self.grid_indices):
            for c,ch_idx in enumerate(row):
                short = self.chords[ch_idx]["repr"]
                btn = tk.Button(self.chord_frame, text=short, width=16,
                                command=lambda ci=ch_idx: self.check_answer(ci))
                btn.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
                
                # build tooltip texts
                ratios = self.chords[ch_idx]["ratios"]
                repres = self.chords[ch_idx]["repr"]
                name = self.chords[ch_idx]["name"]
                cents = "cents:"
                for rat in ratios:
                    cents += f" {math.log2(eval(rat)) * 1200:.2f},"
                tooltip_text = f"{name}\n{repres}\n{cents}\n"+", ".join(ratios)
                
                ToolTip(btn, text=tooltip_text, delay=1200)

                self.chord_buttons.append((ch_idx, btn))

        # make rows/cols expand evenly
        cols = max(len(r) for r in self.grid_indices)
        rows = len(self.grid_indices)
        for c in range(cols):
            self.chord_frame.grid_columnconfigure(c, weight=1)
        for r in range(rows):
            self.chord_frame.grid_rowconfigure(r, weight=1)

        # play the new chord
        ratios = self.chords[self.current_chord_idx]["ratios"]
        self.play_chord(ratios)

    def calc_B(self, f):
        return self.B0 * (f / self.f0)**self.beta

    def check_answer(self, guess_idx):
        for _,btn in self.chord_buttons:
            btn.config(state="disabled")

        correct = self.current_chord_idx
        name = self.chords[correct]["repr"]
        fg = "green" if guess_idx==correct else "red"
        self.feedback_label.config(text=name, fg=fg)

        for ci,btn in self.chord_buttons:
            if ci==correct:
                btn.config(fg="green")
            elif ci==guess_idx:
                btn.config(fg="red")

        self.root.after(1000, self.next_chord)

    def replay_chord(self):
        if self.current_chord_idx is not None:
            self.play_chord(self.chords[self.current_chord_idx]["ratios"])

    def play_chord(self, ratios):
        threading.Thread(target=self._play, args=(ratios,), daemon=True).start()

    def _play(self, ratios, blocksize=4096):
        """
        ratios    : list of frequency multipliers (e.g. ['1.0','1.5'] for a chord)
        blocksize : number of samples per callback
        """
        fs       = self.fs
        jitter   = self.jitter
        p        = self.rolloff_coeff
        tau0     = self.decay_time
        d        = self.decay_exponent
        duration = self.duration

        # 1) Build flat lists of all partials for all ratios
        f_list   = []
        amp_list = []
        tau_list = []

        for r in ratios:
            pitch = self.base_freq * eval(r)
            B     = self.calc_B(pitch)

            k = np.arange(1, self.n_harmonics + 1)      # shape (n_h,)
            f_k = pitch * k * np.sqrt(1 + B * k**2)     # frequencies

            if jitter > 0:
                f_k = f_k + np.random.uniform(-jitter, +jitter, size=f_k.shape)

            amp   = 1.0 / (k**p)                        # rolloff
            tauk  = tau0 / (k**d)                       # per–partial decay

            # extend our flat lists
            f_list .append(f_k)
            amp_list.append(amp)
            tau_list.append(tauk)

        # concatenate into single arrays of length P = total partials
        f_list   = np.concatenate(f_list)    # shape (P,)
        amp_list = np.concatenate(amp_list)  # shape (P,)
        tau_list = np.concatenate(tau_list)  # shape (P,)

        # pre‐compute a rough normalization constant so we don't clip.
        # We know maximum partial sum ≤ sum(amp_list), so scale by 0.3 / sum.
        norm = 0.3 / np.sum(amp_list)

        # 2) state
        phases = np.zeros_like(f_list)   # current phase of each partial
        t_cur  = 0.0                      # global time offset

        # 3) callback
        def callback(outdata, frames, time, status):
            nonlocal phases, t_cur
            if status:
                print("Stream status:", status)

            # time vector for this block: shape (frames,)
            t = np.arange(frames, dtype=np.float32) / fs   # [0, 1/fs, 2/fs, ...]
            # envelope: exp(-(t_cur + t) / tau_list[:,None]) → shape (P, frames)
            env = np.exp(-(t_cur + t)[None, :] / tau_list[:, None])
            # phase + 2π f t
            arg = phases[:, None] + 2 * np.pi * f_list[:, None] * t[None, :]
            sines = np.sin(arg)  # shape (P, frames)

            # sum partials, apply amp and envelope
            block = np.sum(amp_list[:, None] * env * sines, axis=0)

            # write to outdata (mono)
            outdata[:, 0] = norm * block

            # advance phases and time
            phases += 2 * np.pi * f_list * (frames / fs)
            # keep them in [0,2π) to avoid overflow
            phases %= 2 * np.pi
            t_cur  += frames / fs
        
        # 4) open stream
        with sd.OutputStream(
            samplerate=fs,
            blocksize=blocksize,
            channels=1,
            dtype='float32',
            callback=callback
        ):
            # just sleep while the stream runs
            sd.sleep(int(duration * 1000) + 100)  # +100 ms safety margin

if __name__ == "__main__":
    root = tk.Tk()
    app = ChordRecognitionApp(root)
    root.mainloop()