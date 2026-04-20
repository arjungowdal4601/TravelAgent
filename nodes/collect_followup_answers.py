from langgraph.types import interrupt


def _clean_text(value, fallback: str = "") -> str:
    """Normalize text values received from state or interrupt payloads."""
    if not isinstance(value, str):
        return fallback
    cleaned = value.strip()
    return cleaned or fallback


def _clean_options(options) -> list[str]:
    """Clean select options while preserving order and uniqueness."""
    cleaned_options: list[str] = []
    for option in options or []:
        if not isinstance(option, str):
            continue
        cleaned_option = option.strip()
        if cleaned_option and cleaned_option not in cleaned_options:
            cleaned_options.append(cleaned_option)
    return cleaned_options


def _clean_multi_answer(answer_value) -> list[str]:
    """Normalize multi-select answers into a de-duplicated list of strings."""
    if isinstance(answer_value, str):
        candidates = [answer_value]
    elif isinstance(answer_value, list):
        candidates = answer_value
    else:
        candidates = []

    cleaned_answers: list[str] = []
    for answer in candidates:
        if not isinstance(answer, str):
            continue
        cleaned_answer = answer.strip()
        if cleaned_answer and cleaned_answer not in cleaned_answers:
            cleaned_answers.append(cleaned_answer)
    return cleaned_answers


def collect_followup_answers(state: dict) -> dict:
    """Pause for one follow-up answer and store it by question input type."""
    questions = state.get("followup_questions", [])
    if not isinstance(questions, list):
        raise ValueError("Follow-up questions must be a list.")

    current_index = int(state.get("current_followup_index") or 0)
    answers = list(state.get("followup_answers") or [])

    if current_index >= len(questions):
        return {
            "current_followup_index": current_index,
            "followup_answers": answers,
        }

    question_item = questions[current_index]
    if not isinstance(question_item, dict):
        raise ValueError("Each follow-up question must be a dictionary.")

    question = _clean_text(question_item.get("question"))
    if not question:
        raise ValueError("Each follow-up question must include a question.")

    input_type = _clean_text(question_item.get("input_type"), "single_select").lower()
    why_this_matters = _clean_text(question_item.get("why_this_matters", ""))

    if input_type in {"single_select", "multi_select"}:
        cleaned_options = _clean_options(question_item.get("options"))
        if len(cleaned_options) < 2:
            raise ValueError("Select-type follow-up questions must include at least 2 options.")

        answer = interrupt(
            {
                "type": "followup_question",
                "question": question,
                "input_type": input_type,
                "options": cleaned_options[:6],
                "why_this_matters": why_this_matters,
                "current_index": current_index,
                "total_questions": len(questions),
            }
        )

        if isinstance(answer, dict):
            answer_value = answer.get("answer")
        else:
            answer_value = answer

        if input_type == "multi_select":
            normalized_answer = _clean_multi_answer(answer_value)
            if not normalized_answer:
                normalized_answer = ["No specific preference."]
            answers.append(
                {
                    "question": question,
                    "input_type": input_type,
                    "options": cleaned_options[:6],
                    "answer": normalized_answer,
                    "why_this_matters": why_this_matters,
                }
            )
        else:
            answer_text = _clean_text(answer_value)
            if not answer_text:
                answer_text = "No specific preference."
            answers.append(
                {
                    "question": question,
                    "input_type": input_type,
                    "options": cleaned_options[:6],
                    "answer": answer_text,
                    "why_this_matters": why_this_matters,
                }
            )
    elif input_type == "text":
        placeholder = _clean_text(
            question_item.get("placeholder"),
            "Share your preference",
        )
        answer = interrupt(
            {
                "type": "followup_question",
                "question": question,
                "input_type": input_type,
                "placeholder": placeholder,
                "why_this_matters": why_this_matters,
                "current_index": current_index,
                "total_questions": len(questions),
            }
        )

        if isinstance(answer, dict):
            answer_text = _clean_text(answer.get("answer"))
        else:
            answer_text = _clean_text(answer)
        if not answer_text:
            answer_text = "No specific preference."

        answers.append(
            {
                "question": question,
                "input_type": input_type,
                "placeholder": placeholder,
                "answer": answer_text,
                "why_this_matters": why_this_matters,
            }
        )
    else:
        raise ValueError(f"Unsupported follow-up question input_type: {input_type}")

    return {
        "current_followup_index": current_index + 1,
        "followup_answers": answers,
    }
