import os
import re
import time
from openai import OpenAI
from classifier import classify_prompt

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

TASK_MODEL_MAP = {
    "CODE": "qwen3-32b",
    "MATH": "qwen3-32b",
    "CREATIVE": "llama-3.3-70b-versatile",
    "SUMMARY": "llama-3.1-8b-instant",
    "AGENTIC": "llama-3.3-70b-versatile",
    "TRANSLATION": "llama-3.3-70b-versatile",
    "SEC_LOGS": "llama-3.1-8b-instant",
    "DATA_ANALYSIS": "qwen3-32b",
    "REASONING_LOGIC": "qwen3-32b",
    "SYSTEM_ROLE": "llama-3.3-70b-versatile",
    "DESIGN_UX": "llama-3.3-70b-versatile",
    "BUSINESS_MARKETING": "llama-3.3-70b-versatile",
    "GENERAL_CONVO": "llama-3.1-8b-instant",
    "FACTUAL": "llama-3.3-70b-versatile",
}


def ask_groq(prompt, model_id, history_buffer):
    try:
        messages_payload = [
            {
                "role": "system",
                "content": "You are Eris, an advanced AI platform created and developed by Ibrahim Shahzad. If asked who made you, who developed you, or about your identity, you must explicitly state that you were built by Ibrahim Shahzad."
            }
        ]

        messages_payload.extend(history_buffer)
        messages_payload.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model_id,
            messages=messages_payload,
            temperature=0.4,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ROUTE_FAILED: {str(e)}"


def route(prompt, history_buffer):
    try:
        pipeline_start_time = time.time()

        CHARACTER_THRESHOLD = 15000
        if len(prompt) > CHARACTER_THRESHOLD:
            selected_model = "qwen3-32b"
            response_text = ask_groq(prompt, selected_model, history_buffer)

            history_buffer.append({"role": "user", "content": prompt})
            history_buffer.append(
                {"role": "assistant", "content": response_text})

            elapsed_time = round(time.time() - pipeline_start_time, 2)
            return {
                "task_type": "LARGE_DATA_DUMP",
                "model_used": f"{selected_model} (Time: {elapsed_time}s)",
                "response": response_text
            }

        split_segments = re.split(r'\b(?:and then|then|also)\b|[;\.]', prompt)
        sub_prompts = [seg.strip()
                       for seg in split_segments if len(seg.strip()) > 3]

        if not sub_prompts:
            sub_prompts = [prompt.strip()]

        final_responses = []
        executed_categories = []
        executed_models = []

        for i, sub_prompt in enumerate(sub_prompts):
            task_type = classify_prompt(sub_prompt)
            selected_model = TASK_MODEL_MAP.get(
                task_type, "llama-3.1-8b-instant")

            executed_categories.append(task_type)
            executed_models.append(selected_model)

            response_text = ask_groq(
                sub_prompt, selected_model, history_buffer)

            if "ROUTE_FAILED" in response_text:
                fallback_model = "llama-3.1-8b-instant" if selected_model != "llama-3.1-8b-instant" else "llama-3.3-70b-versatile"
                response_text = ask_groq(
                    sub_prompt, fallback_model, history_buffer)
                selected_model = fallback_model

            if len(sub_prompts) > 1:
                formatted_chunk = f"### Part {i+1} [{task_type}]\n*{sub_prompt}\n\n{response_text}"
                final_responses.append(formatted_chunk)
            else:
                final_responses.append(response_text)

        merged_response = "\n\n---\n\n".join(final_responses)

        history_buffer.append({"role": "user", "content": prompt})
        history_buffer.append(
            {"role": "assistant", "content": merged_response})

        elapsed_time = round(time.time() - pipeline_start_time, 2)
        combined_tasks = " + ".join(sorted(set(executed_categories)))
        combined_models = f"{' & '.join(sorted(set(executed_models)))} (Time: {elapsed_time}s)"

        return {
            "task_type": combined_tasks,
            "model_used": combined_models,
            "response": merged_response
        }

    except Exception as general_error:
        return {
            "task_type": "ERROR_DIAGNOSTIC",
            "model_used": "System Diagnostics Engine",
            "response": f"Core Route Pipeline crashed. Internal error detail: {str(general_error)}"
        }
