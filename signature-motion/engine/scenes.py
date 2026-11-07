"""Public frame interface for an editor or render worker."""
from .scenes_a import redline, signal, type_impact
from .scenes_b import after_hours, flow_state, prism


SCENES = {
    "type-impact": type_impact,
    "redline": redline,
    "signal": signal,
    "flow-state": flow_state,
    "prism": prism,
    "after-hours": after_hours,
}


def render_frame(config: dict, frame_index: int):
    """Render one frame with no dependency on previously rendered frames.

    Call validation.validate_config before this function at the worker boundary.
    The exact output additionally depends on the installed Pillow/FreeType build
    and the local font bytes; pin those in production render workers.
    """
    frames = round(config["duration"] * config["fps"])
    if not isinstance(frame_index, int) or isinstance(frame_index, bool) or not 0 <= frame_index < frames:
        raise ValueError(f"frame_index must be an integer in [0, {frames})")
    return SCENES[config["template"]](config, frame_index).convert("RGB")
