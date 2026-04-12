"""
Context Builder — assembles the master briefing document for LLM analysis.

The briefing has four layers:
1. STATIC PROJECT BRIEF — written once by the user, never changes
2. CUMULATIVE SUMMARY — Claude-generated rolling summary of all prior findings
3. TODAY'S INPUTS — all raw content from today's entry
4. INSTRUCTIONS — what Claude should produce

This keeps context well within the 200K token window of modern LLMs.
"""

from models.project import Project
from models.daily_entry import DailyEntry
from models.context_store import ContextStore
from typing import Optional

SYSTEM_PROMPT = """You are a senior management consultant and organizational analyst embedded in an audit engagement.
Your role is to analyze daily field inputs from a Forward Deployment Engineer (FDE) conducting an organizational audit,
and produce structured, insightful daily reports.

You reason carefully about patterns, gaps, and organizational dynamics. You are direct, precise, and practical.
You do not produce filler — every sentence in your output should contain signal.

You will always output a valid JSON object with the exact schema specified in the user's message.
Do not add any text before or after the JSON. Output only the JSON."""


def build_analysis_prompt(
    project: Project,
    entry: DailyEntry,
    context_store: ContextStore,
    extra_user_prompt: Optional[str] = None
) -> tuple[str, str]:
    """
    Returns (system_prompt, user_message) ready to pass to LLMService.complete().
    """

    brief = project.brief

    # ── LAYER 1: Static project brief ─────────────────────────────────────────
    project_brief_section = f"""
═══════════════════════════════════════════════════
SECTION 1 — PROJECT BRIEF (permanent context)
═══════════════════════════════════════════════════

Engagement: {brief.engagement_name}
Client: {brief.client_name}
FDE (analyst): {brief.fde_name}
Total engagement length: {brief.week_count} weeks
Current position: Week {project.current_week}, Day {project.current_day}

ENGAGEMENT GOAL:
{brief.engagement_goal}

DELIVERABLE:
{brief.deliverable_description}

ORGANIZATIONAL STRUCTURE:
{brief.org_structure or 'Not yet documented.'}

CORE HYPOTHESIS BEING TESTED:
{brief.core_hypothesis or 'Not yet defined.'}

KEY CONTACTS:
{_format_contacts(brief.key_contacts)}

ADDITIONAL CONTEXT THE FDE HAS PROVIDED:
{brief.custom_context or 'None.'}
"""

    # ── LAYER 2: Cumulative summary ────────────────────────────────────────────
    cumulative_section = f"""
═══════════════════════════════════════════════════
SECTION 2 — CUMULATIVE FINDINGS TO DATE (prior sessions)
═══════════════════════════════════════════════════

SUMMARY OF ALL PRIOR WORK ({context_store.total_days_analyzed} days analyzed so far):
{context_store.cumulative_summary or 'This is Day 1 — no prior analysis exists.'}

KEY FINDINGS SO FAR:
{_format_list(context_store.key_findings, empty='None yet.')}

CONFIRMED GAPS/PROBLEMS IDENTIFIED:
{_format_list(context_store.confirmed_gaps, empty='None confirmed yet.')}

OPEN QUESTIONS STILL TO INVESTIGATE:
{_format_list(context_store.open_questions, empty='None yet.')}

STAKEHOLDER INSIGHTS ACCUMULATED:
{_format_dict(context_store.stakeholder_insights, empty='None yet.')}

YESTERDAY'S PLAN (what the FDE was supposed to do today):
{context_store.last_plan or 'No prior plan — this is the first session.'}
"""

    # ── LAYER 3: Today's inputs ────────────────────────────────────────────────
    todays_inputs_section = f"""
═══════════════════════════════════════════════════
SECTION 3 — TODAY'S INPUTS (raw field data)
Date: {entry.entry_date.strftime('%A, %d %B %Y')} | Week {entry.week_number}, Day {entry.day_number}
═══════════════════════════════════════════════════

FDE'S TYPED FINDINGS FOR TODAY:
{entry.typed_findings or '(none provided)'}

FDE'S OWN ANNOTATIONS AND HUNCHES:
{entry.user_annotations or '(none provided)'}

REVIEW OF YESTERDAY'S PLAN — HOW DID TODAY ACTUALLY GO:
{entry.previous_plan_review or '(not reviewed)'}

{_format_audio_transcripts(entry.audio_recordings)}

{_format_documents(entry.uploaded_documents)}

{f"ADDITIONAL PROMPT FROM FDE:{chr(10)}{extra_user_prompt}" if extra_user_prompt else ""}
"""

    # ── LAYER 4: Output instructions ──────────────────────────────────────────
    output_instructions = """
═══════════════════════════════════════════════════
SECTION 4 — REQUIRED OUTPUT
═══════════════════════════════════════════════════

Analyze all sections above and return a JSON object with EXACTLY this schema:

{
  "executive_summary": "3-5 sentence narrative of what happened today and what it means",

  "key_findings_today": [
    "Finding 1 — be specific, name people/processes/systems where relevant",
    "Finding 2",
    ...
  ],

  "patterns_emerging": "Narrative paragraph about cross-day patterns you are now seeing. What recurring theme or structural issue keeps appearing?",

  "hypothesis_update": "How does today's evidence support, weaken, or complicate the core hypothesis? Be direct.",

  "stakeholder_notes": "Specific observations about individuals encountered today — their motivations, communication style, what they revealed, what they withheld.",

  "risks_and_flags": [
    "Risk or flag 1 — something needing attention or follow-up",
    ...
  ],

  "progress_summary": "2-3 paragraph narrative of where the overall engagement stands. How far through the work? What's still unknown? What's the confidence level on current findings?",

  "tomorrow_plan": "A specific narrative plan for tomorrow — who to talk to, what to ask, what to observe, what to validate. Be specific to this engagement context.",

  "tomorrow_priorities": [
    "Priority 1 (specific action)",
    "Priority 2",
    "Priority 3"
  ],

  "updated_cumulative_summary": "A dense, comprehensive paragraph (max 600 words) summarizing EVERYTHING discovered across all days including today. This replaces the prior cumulative summary — write it to be maximally useful as context for the next session.",

  "updated_key_findings": [
    "Updated master list of all key findings across all days"
  ],

  "updated_confirmed_gaps": [
    "Updated list of confirmed gaps and structural problems found"
  ],

  "updated_open_questions": [
    "Updated list of questions still needing investigation"
  ],

  "updated_stakeholder_insights": {
    "Person Name": "Current accumulated understanding of this person",
    ...
  }
}

Rules:
- Output ONLY valid JSON. No markdown, no preamble, no explanation.
- All strings should be substantive — no placeholder text.
- Base everything on the actual content in Sections 1–3.
- If an input section is empty, work with what you have and note the gap.
"""

    user_message = project_brief_section + cumulative_section + todays_inputs_section + output_instructions

    return SYSTEM_PROMPT, user_message


def _format_contacts(contacts: list) -> str:
    if not contacts:
        return "Not yet documented."
    lines = []
    for c in contacts:
        line = f"  • {c.get('name', 'Unknown')} — {c.get('role', '')} ({c.get('department', '')})"
        if c.get('notes'):
            line += f"\n    Notes: {c['notes']}"
        lines.append(line)
    return "\n".join(lines)


def _format_list(items: list, empty: str = "None.") -> str:
    if not items:
        return empty
    return "\n".join(f"  • {item}" for item in items)


def _format_dict(d: dict, empty: str = "None.") -> str:
    if not d:
        return empty
    lines = []
    for name, insight in d.items():
        lines.append(f"  {name}: {insight}")
    return "\n".join(lines)


def _format_audio_transcripts(recordings: list) -> str:
    if not recordings:
        return ""
    sections = ["INTERVIEW / MEETING TRANSCRIPTS:"]
    for i, rec in enumerate(recordings, 1):
        label = f"Recording {i}"
        if rec.interviewee_name:
            label = f"Interview with {rec.interviewee_name}"
            if rec.interviewee_role:
                label += f" ({rec.interviewee_role})"
        sections.append(f"\n[{label}]")
        if rec.notes:
            sections.append(f"FDE notes on this recording: {rec.notes}")
        if rec.transcript:
            source = f"[Transcribed via {rec.transcript_source or 'unknown'}]"
            sections.append(f"{source}\n{rec.transcript}")
        else:
            sections.append("[No transcript available for this recording]")
    return "\n".join(sections)


def _format_documents(documents: list) -> str:
    if not documents:
        return ""
    sections = ["UPLOADED DOCUMENTS:"]
    for i, doc in enumerate(documents, 1):
        sections.append(f"\n[Document {i}: {doc.original_filename}]")
        if doc.user_annotation:
            sections.append(f"FDE annotation: {doc.user_annotation}")
        if doc.extracted_text:
            sections.append(f"Document content:\n{doc.extracted_text[:3000]}{'...[truncated]' if len(doc.extracted_text) > 3000 else ''}")
        else:
            sections.append("[Document content not extracted]")
    return "\n".join(sections)
