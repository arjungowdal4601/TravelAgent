from langgraph.types import interrupt


def collect_followup_answers(state: dict) -> dict:
    """Pause for one MCQ follow-up answer and store it."""
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

    question = str(question_item.get("question") or "").strip()
    options = question_item.get("options")
    if not question or not isinstance(options, list):
        raise ValueError("Each follow-up question must include a question and options.")

    cleaned_options = []
    for option in options:
        if not isinstance(option, str):
            continue
        cleaned_option = option.strip()
        if cleaned_option:
            cleaned_options.append(cleaned_option)

    if len(cleaned_options) < 3:
        raise ValueError("Each MCQ follow-up question must include at least 3 options.")

    answer = interrupt(
        {
            "type": "followup_question",
            "question": question,
            "options": cleaned_options[:4],
            "current_index": current_index,
            "total_questions": len(questions),
        }
    )

    if isinstance(answer, dict):
        answer_text = str(answer.get("answer") or "").strip()
    else:
        answer_text = str(answer or "").strip()

    if not answer_text:
        answer_text = "No specific preference."

    answers.append(
        {
            "question": question,
            "options": cleaned_options[:4],
            "answer": answer_text,
        }
    )

    return {
        "current_followup_index": current_index + 1,
        "followup_answers": answers,
    }
