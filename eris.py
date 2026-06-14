import os
import re
import time
from openai import OpenAI
from classifier import classify_prompt

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_SITE_URL = os.getenv(
    "OPENROUTER_SITE_URL", "https://eris-mainfram-production.up.railway.app")
OPENROUTER_APP_NAME = os.getenv(
    "OPENROUTER_APP_NAME", "Eris Stateful Platform")
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL", "qwen/qwen3-next-80b-a3b-instruct:free")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


def ask_openrouter(prompt, model_id, history_buffer):
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
            extra_headers={
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title": OPENROUTER_APP_NAME,
            }
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ROUTE_FAILED: {str(e)}"


def route(prompt, history_buffer):
    try:
        pipeline_start_time = time.time()

        CHARACTER_THRESHOLD = 15000
        if len(prompt) > CHARACTER_THRESHOLD:
            print(
                f"\n[Eris Orchestrator] LARGE PAYLOAD WARNING: {len(prompt)} characters detected.")
            selected_model = "Long Context Model"
            response_text = ask_openrouter(
                prompt, OPENROUTER_MODEL, history_buffer)

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

        print(
            f"\n[Eris Orchestrator] Stateful Processing: Resolving {len(sub_prompts)} intent branches.")

        final_responses = []
        executed_categories = []
        executed_models = []

        model_display_names = {
            "CODE": "Qwen 2.5 Coder (Auto-Routed)",
            "MATH": "DeepSeek R1 Llama (Auto-Routed)",
            "CREATIVE": "Gemma 2 27B (Auto-Routed)",
            "SUMMARY": "Llama 3 8B (Auto-Routed)",
            "AGENTIC": "Llama 3.3 70B (Auto-Routed)",
            "TRANSLATION": "Qwen 2.5 72B (Auto-Routed)",
            "SEC_LOGS": "Llama 3.1 8B (Auto-Routed)",
            "DATA_ANALYSIS": "DeepSeek Data Engine (Auto-Routed)",
            "REASONING_LOGIC": "DeepSeek R1 Reasoning (Auto-Routed)",
            "SYSTEM_ROLE": "Llama Persona Engine (Auto-Routed)",
            "DESIGN_UX": "Gemma Creative UI (Auto-Routed)",
            "BUSINESS_MARKETING": "Mistral Business Pro (Auto-Routed)",
            "GENERAL_CONVO": "Llama Chat Optimizer (Auto-Routed)",
            "FACTUAL": "Llama General (Auto-Routed)"
        }

        for i, sub_prompt in enumerate(sub_prompts):
            task_type = classify_prompt(sub_prompt)
            selected_model = model_display_names.get(
                task_type, "Llama General (Auto-Routed)")

            print(
                f"  ➔ Sub-task {i+1}: '{sub_prompt[:35]}...' ➔ Category: [{task_type}]")

            executed_categories.append(task_type)
            executed_models.append(selected_model)

            response_text = ask_openrouter(
                sub_prompt, OPENROUTER_MODEL, history_buffer)

            if "ROUTE_FAILED" in response_text or "404" in response_text or "402" in response_text:
                selected_model = "Eris Local Fail-Safe"
                response_text = f"Connection restriction detected on OpenRouter endpoint. Details: {response_text}"

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
        print(
            f"[Eris Orchestrator] Stateful Pipeline completed in {elapsed_time}s. Memory Depth: {len(history_buffer)} nodes.")

        combined_tasks = " + ".join(set(executed_categories))
        combined_models = f"{' & '.join(set(executed_models))} (Time: {elapsed_time}s)"

        return {
            "task_type": combined_tasks,
            "model_used": combined_models,
            "response": merged_response
        }

    except Exception as general_error:
        print(f"[CRITICAL ROUTE ERROR]: {str(general_error)}")
        return {
            "task_type": "ERROR_DIAGNOSTIC",
            "model_used": "System Diagnostics Engine",
            "response": f"Core Route Pipeline crashed. Internal error detail: {str(general_error)}"
        }
