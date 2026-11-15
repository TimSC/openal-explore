"""Editable EFX parameters: label, minimum, maximum, default, step."""

EFFECTS = {
    "ECHO": {
        "delay": ("Delay (s)", 0.0, 0.207, 0.1, 0.005),
        "lr_delay": ("Left/right delay (s)", 0.0, 0.404, 0.1, 0.005),
        "damping": ("Damping", 0.0, 0.99, 0.5, 0.05),
        "feedback": ("Feedback", 0.0, 1.0, 0.5, 0.05),
        "spread": ("Stereo spread", -1.0, 1.0, -1.0, 0.1),
    },
    "CHORUS": {
        "rate": ("Rate (Hz)", 0.0, 10.0, 1.1, 0.1),
        "depth": ("Depth", 0.0, 1.0, 0.1, 0.05),
        "feedback": ("Feedback", -1.0, 1.0, 0.25, 0.05),
        "delay": ("Delay (s)", 0.0, 0.016, 0.016, 0.001),
    },
    "FLANGER": {
        "rate": ("Rate (Hz)", 0.0, 10.0, 0.27, 0.05),
        "depth": ("Depth", 0.0, 1.0, 1.0, 0.05),
        "feedback": ("Feedback", -1.0, 1.0, -0.5, 0.05),
        "delay": ("Delay (s)", 0.0, 0.004, 0.002, 0.0005),
    },
    "DISTORTION": {
        "edge": ("Edge", 0.0, 1.0, 0.2, 0.05),
        "gain": ("Effect gain", 0.01, 1.0, 0.05, 0.01),
        "lowpass_cutoff": ("Low-pass cutoff (Hz)", 80.0, 24000.0, 8000.0, 100.0),
        "eq_center": ("EQ centre (Hz)", 80.0, 24000.0, 3600.0, 100.0),
        "eq_bandwidth": ("EQ bandwidth (Hz)", 80.0, 24000.0, 3600.0, 100.0),
    },
    "EQUALIZER": {
        "low_gain": ("Low gain", 0.126, 7.943, 1.0, 0.1),
        "low_cutoff": ("Low cutoff (Hz)", 50.0, 800.0, 200.0, 10.0),
        "mid1_gain": ("Mid 1 gain", 0.126, 7.943, 1.0, 0.1),
        "mid1_center": ("Mid 1 centre (Hz)", 200.0, 3000.0, 500.0, 50.0),
        "mid1_width": ("Mid 1 width", 0.01, 1.0, 1.0, 0.05),
        "mid2_gain": ("Mid 2 gain", 0.126, 7.943, 1.0, 0.1),
        "mid2_center": ("Mid 2 centre (Hz)", 1000.0, 8000.0, 3000.0, 100.0),
        "mid2_width": ("Mid 2 width", 0.01, 1.0, 1.0, 0.05),
        "high_gain": ("High gain", 0.126, 7.943, 1.0, 0.1),
        "high_cutoff": ("High cutoff (Hz)", 4000.0, 16000.0, 6000.0, 100.0),
    },
}

ZONE_PRESETS = {
    "cave": {"wet": 0.55, "decay": 4.0, "gain_hf": 0.45, "diffusion": 1.0},
    "hall": {"wet": 0.35, "decay": 2.4, "gain_hf": 0.8, "diffusion": 0.9},
    "outdoor": {"wet": 0.02, "decay": 0.3, "gain_hf": 1.0, "diffusion": 0.3},
}
