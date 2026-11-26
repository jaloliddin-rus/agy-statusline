#!/usr/bin/env python3
"""Custom single-line ANSI statusline script for Antigravity CLI."""

import json
import os
import re
import sys
import time

RESET = "\033[0m"
DIM = "\033[2m"
BOLD_CYAN = "\033[1;36m"
MAGENTA = "\033[35m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"

SEP = f"{DIM} | {RESET}"

EFFORT_WORDS = {
    "minimal",
    "low",
    "medium",
    "med",
    "high",
    "xhigh",
    "extra high",
    "max",
    "none",
    "off",
}


def color_ctx(pct: int) -> str:
    """Return ANSI color for context utilization percentage."""
    if pct < 50:
        return GREEN
    if pct < 80:
        return YELLOW
    return RED


def color_remaining(pct: int) -> str:
    """Return ANSI color for remaining quota percentage."""
    if pct > 50:
        return GREEN
    if pct > 20:
        return YELLOW
    return RED


def get_short_dir(data: dict) -> str:
    """Extract a short project-like directory name from payload."""
    ws = data.get("workspace")
    ws_dict = ws if isinstance(ws, dict) else {}

    raw_path = ws_dict.get("current_dir") or data.get("cwd") or ws_dict.get("project_dir")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return "?"

    stripped = raw_path.strip().rstrip("/\\")
    if not stripped:
        return "/" if raw_path.strip().startswith("/") else "?"

    home = os.path.expanduser("~").rstrip("/\\")
    if stripped == home:
        return "~"

    return os.path.basename(stripped) or stripped


def _split_model_and_effort(raw_name: str, explicit_effort: str = "") -> tuple[str, str]:
    """Split a model label into (base_model_name, normalized_effort)."""
    name = raw_name.strip() or "unknown"
    effort = explicit_effort.strip().lower()

    match = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", name)
    if match:
        base, paren = match.group(1), match.group(2)
        paren_lower = paren.strip().lower()
        if paren_lower in EFFORT_WORDS or (effort and paren_lower == effort):
            model_name = base.strip() or name
            effort_str = paren_lower
        else:
            model_name = name
            effort_str = effort
    else:
        model_name = name
        effort_str = effort

    if effort_str and model_name.lower().endswith(" " + effort_str):
        effort_str = ""

    return model_name, effort_str


def get_model_label(data: dict) -> tuple[str, str, str]:
    """Return (model_name, effort_str, combined_hint) from model payload."""
    model = data.get("model")
    if isinstance(model, dict):
        model_id = str(model.get("id") or "").strip()
        display_name = str(model.get("display_name") or "").strip()
        raw_name = display_name or model_id
        explicit_effort = str(model.get("effort") or "").strip().lower()
        raw_combined = f"{model_id} {display_name}".lower()
    elif isinstance(model, str):
        raw_name = model.strip()
        explicit_effort = ""
        raw_combined = raw_name.lower()
    else:
        raw_name = ""
        explicit_effort = ""
        raw_combined = ""

    model_name, effort_str = _split_model_and_effort(raw_name, explicit_effort)
    return model_name, effort_str, raw_combined


def _normalize_model_slug(name: str) -> str:
    """Normalize a model name or ID for fuzzy comparison."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _format_model_id(raw_id: str) -> str:
    """Format a model slug such as 'gemini-4-neon-high' into a display name."""
    cleaned = raw_id.strip()
    if not cleaned:
        return "unknown"
    if " " in cleaned:
        return cleaned

    parts = [p for p in re.split(r"[-_]+", cleaned) if p]
    if not parts:
        return cleaned

    effort = ""
    if len(parts) > 1 and parts[-1].lower() in EFFORT_WORDS:
        effort = parts.pop().lower()

    formatted: list[str] = []
    for tok in parts:
        if tok.lower() == "gpt":
            formatted.append("GPT")
        elif tok[0].isdigit():
            formatted.append(tok)
        else:
            formatted.append(tok.capitalize())

    base = " ".join(formatted)
    return f"{base} ({effort})" if effort else base


def _load_orchestrator_config(data: dict) -> tuple[str, str]:
    """Return (planner_model, executor_model) from payload or agy settings."""
    orch = data.get("orchestrator")
    orch_dict = orch if isinstance(orch, dict) else {}
    planner = str(orch_dict.get("planner") or "").strip()
    executor = str(orch_dict.get("executor") or "").strip()
    if planner and executor:
        return planner, executor

    try:
        settings_path = os.path.join(
            os.path.expanduser("~"), ".gemini", "antigravity-cli", "settings.json"
        )
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        if isinstance(settings, dict):
            cfg_orch = settings.get("orchestrator")
            if isinstance(cfg_orch, dict):
                if not planner:
                    planner = str(cfg_orch.get("planner") or "").strip()
                if not executor:
                    executor = str(cfg_orch.get("executor") or "").strip()
    except Exception:
        pass

    return planner, executor


def _find_transcript_path(data: dict, ctx_pct: int | None) -> str | None:
    """Locate the active session transcript.jsonl path, if available."""
    raw_tp = data.get("transcript_path")
    if isinstance(raw_tp, str) and raw_tp.strip():
        tp = os.path.expanduser(raw_tp.strip())
        agy_marker = f"{os.sep}.gemini{os.sep}antigravity{os.sep}"
        cli_marker = f"{os.sep}.gemini{os.sep}antigravity-cli{os.sep}"
        candidates = [tp]
        if agy_marker in tp:
            candidates.append(tp.replace(agy_marker, cli_marker, 1))
        for cand in candidates:
            try:
                if os.path.isfile(cand):
                    return cand
            except OSError:
                pass

    gemini_dir = os.path.join(os.path.expanduser("~"), ".gemini")
    brain_dirs = (
        os.path.join(gemini_dir, "antigravity-cli", "brain"),
        os.path.join(gemini_dir, "antigravity", "brain"),
    )
    session_obj = data.get("session")
    raw_sid = (
        data.get("session_id")
        or data.get("conversation_id")
        or (session_obj.get("id") if isinstance(session_obj, dict) else None)
    )
    if isinstance(raw_sid, str) and raw_sid.strip():
        sid = raw_sid.strip()
        for bdir in brain_dirs:
            candidate = os.path.join(bdir, sid, ".system_generated", "logs", "transcript.jsonl")
            try:
                if os.path.isfile(candidate):
                    return candidate
            except OSError:
                pass
        return None

    best_path: str | None = None
    best_mtime = -1.0
    for bdir in brain_dirs:
        try:
            with os.scandir(bdir) as entries:
                for entry in entries:
                    if not entry.is_dir():
                        continue
                    candidate = os.path.join(
                        entry.path, ".system_generated", "logs", "transcript.jsonl"
                    )
                    try:
                        st = os.stat(candidate)
                    except OSError:
                        continue
                    if st.st_mtime > best_mtime:
                        best_mtime = st.st_mtime
                        best_path = candidate
        except OSError:
            continue

    if best_path is None:
        return None
    if (ctx_pct is None or ctx_pct == 0) and (time.time() - best_mtime > 10.0):
        return None
    return best_path


def _read_tail_lines(path: str, max_bytes: int = 262144) -> list[str]:
    """Read up to max_bytes from the end of a file and split into complete lines."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            offset = max(0, size - max_bytes)
            f.seek(offset, os.SEEK_SET)
            raw = f.read()
    except OSError:
        return []

    lines = raw.decode("utf-8", errors="replace").splitlines()
    if offset > 0 and lines:
        lines = lines[1:]
    return lines


def _resolve_model_candidate(
    raw_model: str,
    role_hint: str,
    planner_cfg: str,
    executor_cfg: str,
    planner_slug: str,
    executor_slug: str,
) -> tuple[str, str, str]:
    """Map a raw model ID or display name to (role, model_name, effort_str)."""
    slug = _normalize_model_slug(raw_model)
    if planner_slug and slug == planner_slug and slug != executor_slug:
        return ("plan", *_split_model_and_effort(planner_cfg))
    if executor_slug and slug == executor_slug and slug != planner_slug:
        return ("exec", *_split_model_and_effort(executor_cfg))
    if planner_slug and slug == planner_slug:
        return (role_hint or "plan", *_split_model_and_effort(planner_cfg))
    return (role_hint, *_split_model_and_effort(_format_model_id(raw_model)))


def get_active_orchestrator_model(
    data: dict, model_hint: str, ctx_pct: int | None
) -> tuple[str, str, str] | None:
    """Resolve active (role, model_name, effort_str) when using Orchestrator mode."""
    if "orchestrator" not in model_hint:
        return None

    planner_cfg, executor_cfg = _load_orchestrator_config(data)
    planner_slug = _normalize_model_slug(planner_cfg)
    executor_slug = _normalize_model_slug(executor_cfg)

    model_obj = data.get("model")
    direct_val = (
        data.get("active_model")
        or data.get("current_model")
        or (model_obj.get("active_model") if isinstance(model_obj, dict) else None)
    )
    if isinstance(direct_val, dict):
        d_id = str(direct_val.get("id") or "").strip()
        d_name = str(direct_val.get("display_name") or "").strip()
        d_effort = str(direct_val.get("effort") or "").strip().lower()
        role_tag = str(direct_val.get("role") or "").strip().lower()
        role_hint = "plan" if "plan" in role_tag else "exec" if "exec" in role_tag else ""
        candidate = (
            d_id
            if d_id and _normalize_model_slug(d_id) in (planner_slug, executor_slug)
            else (d_name or d_id)
        )
        if candidate:
            role, m_name, m_eff = _resolve_model_candidate(
                candidate, role_hint, planner_cfg, executor_cfg, planner_slug, executor_slug
            )
            if d_effort and not m_eff and not m_name.lower().endswith(" " + d_effort):
                m_eff = d_effort
            return role, m_name, m_eff
    elif isinstance(direct_val, str) and direct_val.strip():
        return _resolve_model_candidate(
            direct_val.strip(), "", planner_cfg, executor_cfg, planner_slug, executor_slug
        )

    transcript_path = _find_transcript_path(data, ctx_pct)
    if not transcript_path:
        return None

    pending_role = ""
    for line in reversed(_read_tail_lines(transcript_path)):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue

        entry_type = entry.get("type")
        entry_source = entry.get("source")

        if entry_type == "USER_INPUT":
            if planner_cfg:
                return ("plan", *_split_model_and_effort(planner_cfg))
            if not pending_role:
                pending_role = "plan"
            continue

        if entry_source == "SYSTEM" and entry_type == "SYSTEM_MESSAGE":
            content = str(entry.get("content") or "")
            if "Plan mode is off" in content or "runs on the execution model" in content:
                if executor_cfg:
                    return ("exec", *_split_model_and_effort(executor_cfg))
                if not pending_role:
                    pending_role = "exec"
                continue
            if "[plan review]" in content or "Plan mode is on" in content:
                if planner_cfg:
                    return ("plan", *_split_model_and_effort(planner_cfg))
                if not pending_role:
                    pending_role = "plan"
                continue

        if entry_source == "MODEL":
            raw_model = entry.get("model")
            if isinstance(raw_model, str) and raw_model.strip():
                return _resolve_model_candidate(
                    raw_model.strip(),
                    pending_role,
                    planner_cfg,
                    executor_cfg,
                    planner_slug,
                    executor_slug,
                )

    return None


def get_ctx_pct(data: dict) -> int | None:
    """Extract clamped integer context utilization percentage, or None if unavailable."""
    cw = data.get("context_window")
    if not isinstance(cw, dict):
        return None

    used: float | None = None
    raw_used = cw.get("used_percentage")
    if raw_used is not None:
        try:
            used = float(raw_used)
        except (TypeError, ValueError):
            used = None

    if used is None and cw.get("remaining_percentage") is not None:
        try:
            used = 100.0 - float(cw["remaining_percentage"])
        except (TypeError, ValueError):
            used = None

    if used is None and cw.get("context_window_size") is not None:
        try:
            size = float(cw["context_window_size"])
        except (TypeError, ValueError):
            size = 0.0
        cu = cw.get("current_usage")
        if size > 0 and isinstance(cu, dict):
            token_keys = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
            total = 0.0
            found = False
            for key in token_keys:
                val = cu.get(key)
                if val is not None:
                    try:
                        total += float(val)
                        found = True
                    except (TypeError, ValueError):
                        pass
            if found:
                used = (total / size) * 100.0

    if used is None:
        return None

    return round(max(0.0, min(100.0, used)))


def _extract_pct(entry: object) -> int | None:
    """Convert a quota bucket entry into a clamped remaining percentage."""
    if not isinstance(entry, dict) or entry.get("disabled", False):
        return None
    raw_frac = entry.get("remaining_fraction")
    if raw_frac is None:
        return None
    try:
        val = float(raw_frac)
    except (TypeError, ValueError):
        return None
    pct = val * 100.0 if val <= 1.0 else val
    return round(max(0.0, min(100.0, pct)))


THIRD_PARTY_MODEL_KEYWORDS = (
    "claude",
    "sonnet",
    "opus",
    "haiku",
    "anthropic",
    "gpt",
    "openai",
    "codex",
)


def _is_third_party_model(model_hint: str) -> bool:
    """Return True if model_hint identifies a third-party (3p) model pool."""
    hint = model_hint.lower()
    if any(kw in hint for kw in THIRD_PARTY_MODEL_KEYWORDS):
        return True
    return bool(re.search(r"(?:^|[^a-z0-9])(?:3p|o[134])(?:$|[^a-z0-9])", hint))


def get_quota_pcts(data: dict, model_hint: str) -> tuple[int | None, int | None]:
    """Extract (5hr_remaining_pct, 7d_remaining_pct) matching the active model pool."""
    quota = data.get("quota")
    if not isinstance(quota, dict) or not quota:
        return None, None

    preferred_prefix = "3p" if _is_third_party_model(model_hint) else "gemini"
    has_preferred_pool = any(
        isinstance(k, str) and k.lower().startswith(f"{preferred_prefix}-")
        for k in quota
    )

    def find_bucket(suffixes: tuple[str, ...]) -> int | None:
        if has_preferred_pool:
            for suffix in suffixes:
                target = f"{preferred_prefix}-{suffix}"
                for key, entry in quota.items():
                    if isinstance(key, str) and key.lower() == target:
                        return _extract_pct(entry)
            return None

        for suffix in suffixes:
            for key, entry in quota.items():
                if isinstance(key, str):
                    kl = key.lower()
                    if kl.endswith(f"-{suffix}") or kl == suffix:
                        pct = _extract_pct(entry)
                        if pct is not None:
                            return pct
        return None

    five_hr = find_bucket(("5h", "5hr", "rolling"))
    seven_day = find_bucket(("weekly", "7d", "week"))
    return five_hr, seven_day


def format_statusline(data: dict) -> str:
    """Format the full ANSI-colored statusline string from parsed JSON payload."""
    short_dir = get_short_dir(data)
    model_name, effort_str, model_hint = get_model_label(data)
    ctx_pct = get_ctx_pct(data)

    active = get_active_orchestrator_model(data, model_hint, ctx_pct)
    if active is not None:
        role, disp_name, disp_effort = active
        prefix = f"{DIM}orch/{role}:{RESET} " if role else f"{DIM}orch:{RESET} "
        quota_hint = disp_name.lower()
    else:
        disp_name, disp_effort = model_name, effort_str
        prefix = ""
        quota_hint = model_hint

    hr5_pct, d7_pct = get_quota_pcts(data, quota_hint)

    dir_seg = f"{BOLD_CYAN}{short_dir}{RESET}"
    model_seg = f"{prefix}{MAGENTA}{disp_name}{RESET}"
    if disp_effort:
        model_seg = f"{model_seg} {DIM}{disp_effort}{RESET}"

    ctx_val = f"{color_ctx(ctx_pct)}{ctx_pct}%{RESET}" if ctx_pct is not None else f"{DIM}--{RESET}"
    ctx_seg = f"{DIM}ctx:{RESET} {ctx_val}"

    hr5_val = (
        f"{color_remaining(hr5_pct)}{hr5_pct}%{RESET}"
        if hr5_pct is not None
        else f"{DIM}--{RESET}"
    )
    hr5_seg = f"{DIM}5hr:{RESET} {hr5_val}"

    d7_val = (
        f"{color_remaining(d7_pct)}{d7_pct}%{RESET}"
        if d7_pct is not None
        else f"{DIM}--{RESET}"
    )
    d7_seg = f"{DIM}7d:{RESET} {d7_val}"

    return SEP.join([dir_seg, model_seg, ctx_seg, hr5_seg, d7_seg])


def main() -> None:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        return
    data = json.loads(raw)
    if not isinstance(data, dict):
        return
    print(format_statusline(data))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
